from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from typing import Dict, Optional, Tuple

from pymodbus.datastore import ModbusSlaveContext, ModbusServerContext
from pymodbus.datastore.store import ModbusSequentialDataBlock
from pymodbus.server.async_io import StartAsyncSerialServer

from simulator.simulation import MeterState, PlantSimulation

log = logging.getLogger("simulator.modbus")


class WritableDataBlock(ModbusSequentialDataBlock):
    def __init__(self, address: int, values, on_write=None):
        super().__init__(address, values)
        self.on_write = on_write

    def setValues(self, address, values):
        super().setValues(address, values)
        if self.on_write:
            self.on_write(address, values)


def _u16(v: int) -> int:
    return int(v) & 0xFFFF


def encode_pf_u16(pf: float) -> int:
    # implementa somente PF positivo (magnitude). Se quiser sinal por Q, dá para estender.
    pf = max(-1.0, min(1.0, pf))
    if pf >= 0:
        return _u16(int(round(pf * 16384.0)))
    mag = abs(pf)
    raw = int(round(mag * 16384.0))
    return _u16(65535 - raw)


def encode_i_u16(i_a: float) -> int:
    return _u16(int(round(i_a * 256.0)))


def encode_v_u16(v_v: float) -> int:
    return _u16(int(round(v_v * 128.0)))


@dataclass
class PortLayout:
    serial_device: str
    baudrate: int
    parity: str
    stopbits: int
    bytesize: int
    timeout_s: float
    inverter_slave_ids: Tuple[int, ...]
    meter_slave_id: Optional[int] = None
    meter_base_addr: int = 0x0099
    meter_quantity_u16: int = 28


class ModbusRtuPortServer:
    def __init__(self, name: str, layout: PortLayout, sim: PlantSimulation):
        self.name = name
        self.layout = layout
        self.sim = sim
        self.context = self._build_context()

    def _build_inverter_slave(self, slave_id: int) -> ModbusSlaveContext:
        size = 400
        init = [0] * size

        def on_write(addr: int, values):
            # FC16 pode escrever múltiplos; aplica 1 registrador por acesso (primeiro valor)
            if not values:
                return
            v0 = int(values[0])

            if addr == 256:
                self.sim.set_inverter_setpoint_pct(slave_id, float(v0))
            elif addr == 257:
                self.sim.set_inverter_pf_raw(slave_id, int(v0))

        hr = WritableDataBlock(0, init, on_write=on_write)
        return ModbusSlaveContext(
            hr=hr,
            di=ModbusSequentialDataBlock(0, [0] * size),
            co=ModbusSequentialDataBlock(0, [0] * size),
            ir=ModbusSequentialDataBlock(0, [0] * size),
            zero_mode=True,
        )

    def _build_meter_slave(self, slave_id: int) -> ModbusSlaveContext:
        size = max(2048, self.layout.meter_base_addr + self.layout.meter_quantity_u16 + 32)
        hr = ModbusSequentialDataBlock(0, [0] * size)
        return ModbusSlaveContext(
            hr=hr,
            di=ModbusSequentialDataBlock(0, [0] * size),
            co=ModbusSequentialDataBlock(0, [0] * size),
            ir=ModbusSequentialDataBlock(0, [0] * size),
            zero_mode=True,
        )

    def _build_context(self) -> ModbusServerContext:
        slaves: Dict[int, ModbusSlaveContext] = {}
        for sid in self.layout.inverter_slave_ids:
            slaves[sid] = self._build_inverter_slave(sid)

        if self.layout.meter_slave_id is not None:
            slaves[self.layout.meter_slave_id] = self._build_meter_slave(self.layout.meter_slave_id)

        return ModbusServerContext(slaves=slaves, single=False)

    def _update_meter_registers(self):
        if self.layout.meter_slave_id is None or self.sim.meter is None:
            return

        meter: MeterState = self.sim.meter
        slave = self.context.slaves[self.layout.meter_slave_id]
        base = self.layout.meter_base_addr

        # primeiros 14 conforme especificação; restante até 28 = 0
        regs = [0] * self.layout.meter_quantity_u16

        # offsets 0..13
        regs[0] = encode_pf_u16(meter.pfa)
        regs[1] = encode_pf_u16(meter.pfb)
        regs[2] = encode_pf_u16(meter.pfc)
        # 3..6 reserved
        regs[7] = encode_i_u16(meter.ia_a)
        regs[8] = encode_i_u16(meter.ib_a)
        regs[9] = encode_i_u16(meter.ic_a)
        # 10 reserved
        regs[11] = encode_v_u16(meter.ua_v)
        regs[12] = encode_v_u16(meter.ub_v)
        regs[13] = encode_v_u16(meter.uc_v)

        slave.setValues(3, base, regs)

    async def run(self, tick_s: float):
        async def updater():
            # atualiza registradores com frequência maior que tick (mas leve)
            while True:
                self._update_meter_registers()
                await asyncio.sleep(min(0.5, max(0.05, tick_s / 4)))

        asyncio.create_task(updater())

        log.info("Starting Modbus RTU server %s on %s", self.name, self.layout.serial_device)
        await StartAsyncSerialServer(
            context=self.context,
            port=self.layout.serial_device,
            baudrate=self.layout.baudrate,
            parity=self.layout.parity,
            stopbits=self.layout.stopbits,
            bytesize=self.layout.bytesize,
            timeout=self.layout.timeout_s,
        )