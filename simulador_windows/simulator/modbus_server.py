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


# ---------------------------------------------------------------------------
# DataBlock com callback de escrita (FC16)
# ---------------------------------------------------------------------------

class WritableDataBlock(ModbusSequentialDataBlock):
    """Holding Register com callback acionado em cada escrita FC16."""

    def __init__(self, address: int, values, on_write=None):
        super().__init__(address, values)
        self.on_write = on_write

    def setValues(self, address, values):  # noqa: N802
        super().setValues(address, values)
        if self.on_write and values:
            self.on_write(address, values)


# ---------------------------------------------------------------------------
# Codificadores U16 para registradores do medidor
# ---------------------------------------------------------------------------

def _u16(v: int) -> int:
    return int(v) & 0xFFFF


def encode_pf_u16(pf: float) -> int:
    """
    Codifica FP com sinal em U16.
      Positivo [0, 1]  → 0 .. 16384
      Negativo [-1, 0) → 49151 .. 65535  (complemento: 65535 − |pf|×16384)
    O PLC decodifica:
      pf = valor/16384           se valor ≤ 16384
      pf = −(65535−valor)/16384  se valor ≥ 49151
    """
    pf = max(-1.0, min(1.0, pf))
    if pf >= 0.0:
        return _u16(int(round(pf * 16384.0)))
    raw = int(round(abs(pf) * 16384.0))
    return _u16(65535 - raw)


def encode_i_u16(i_a: float) -> int:
    """Corrente (A) com resolução 1/256 A. reg × (1/256) = I_sec (A)."""
    return _u16(int(round(i_a * 256.0)))


def encode_v_u16(v_v: float) -> int:
    """Tensão (V) com resolução 1/128 V. reg × (1/128) = V_sec (V)."""
    return _u16(int(round(v_v * 128.0)))


# ---------------------------------------------------------------------------
# Configuração de uma porta serial Modbus RTU
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Servidor Modbus RTU para uma porta serial
# ---------------------------------------------------------------------------

class ModbusRtuPortServer:
    """
    Instancia um servidor Modbus RTU em uma porta serial.
    Cada porta pode ter N inversores (FC16) e opcionalmente 1 medidor (FC03).
    """

    def __init__(self, name: str, layout: PortLayout, sim: PlantSimulation):
        self.name = name
        self.layout = layout
        self.sim = sim
        self.context = self._build_context()

    # -----------------------------------------------------------------------
    # Construção do datastore
    # -----------------------------------------------------------------------

    def _build_inverter_slave(self, slave_id: int) -> ModbusSlaveContext:
        """
        Holding Registers do inversor:
          HR 256 → setpoint %P  (escrito pelo PLC via FC16)
          HR 257 → PF raw       (escrito pelo PLC via FC16)
        """
        size = 400
        init = [0] * size

        def on_write(addr: int, values):
            if not values:
                return
            v0 = int(values[0])
            if addr == 256:
                self.sim.set_inverter_setpoint_pct(slave_id, float(v0))
            elif addr == 257:
                self.sim.set_inverter_pf_raw(slave_id, v0)

        hr = WritableDataBlock(0, init, on_write=on_write)
        return ModbusSlaveContext(
            hr=hr,
            di=ModbusSequentialDataBlock(0, [0] * size),
            co=ModbusSequentialDataBlock(0, [0] * size),
            ir=ModbusSequentialDataBlock(0, [0] * size),
            zero_mode=True,
        )

    def _build_meter_slave(self, slave_id: int) -> ModbusSlaveContext:
        """
        Holding Registers do medidor.
        Lidos pelo PLC via FC03 a partir de 0x0099 (qty=28).
        """
        size = max(
            2048,
            self.layout.meter_base_addr + self.layout.meter_quantity_u16 + 32,
        )
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
            slaves[self.layout.meter_slave_id] = self._build_meter_slave(
                self.layout.meter_slave_id
            )
        self._meter_slave = (
            slaves.get(self.layout.meter_slave_id)
            if self.layout.meter_slave_id is not None
            else None
        )
        return ModbusServerContext(slaves=slaves, single=False)

    # -----------------------------------------------------------------------
    # Atualização periódica dos registradores do medidor
    # -----------------------------------------------------------------------

    def _update_meter_registers(self) -> None:
        if self.layout.meter_slave_id is None or self.sim.meter is None:
            return

        meter: MeterState = self.sim.meter
        slave = self._meter_slave
        if slave is None:
            return
        base = self.layout.meter_base_addr
        qty = self.layout.meter_quantity_u16

        # Monta bloco de qty registradores (todos inicializados em 0)
        regs = [0] * qty

        # Mapeamento conforme especificação (offsets relativos a base):
        #   0x0099 +  0 → PF fase A
        #   0x0099 +  1 → PF fase B
        #   0x0099 +  2 → PF fase C
        #   0x0099 + 3..6 → reservado
        #   0x0099 +  7 → Ia (A sec × 256)
        #   0x0099 +  8 → Ib
        #   0x0099 +  9 → Ic
        #   0x0099 + 10 → reservado
        #   0x0099 + 11 → Ua (V sec × 128)
        #   0x0099 + 12 → Ub
        #   0x0099 + 13 → Uc
        #   0x0099 + 14..27 → reservado = 0
        if qty > 0:
            regs[0] = encode_pf_u16(meter.pfa)
        if qty > 1:
            regs[1] = encode_pf_u16(meter.pfb)
        if qty > 2:
            regs[2] = encode_pf_u16(meter.pfc)
        if qty > 7:
            regs[7] = encode_i_u16(meter.ia_a)
        if qty > 8:
            regs[8] = encode_i_u16(meter.ib_a)
        if qty > 9:
            regs[9] = encode_i_u16(meter.ic_a)
        if qty > 11:
            regs[11] = encode_v_u16(meter.ua_v)
        if qty > 12:
            regs[12] = encode_v_u16(meter.ub_v)
        if qty > 13:
            regs[13] = encode_v_u16(meter.uc_v)

        slave.setValues(3, base, regs)

    # -----------------------------------------------------------------------
    # Task assíncrona: atualiza medidor a ~100 ms e inicia o servidor
    # -----------------------------------------------------------------------

    async def run(self, tick_s: float) -> None:
        update_interval = 0.1  # 100 ms (10× o tick de 10 ms)

        async def _meter_updater():
            while True:
                self._update_meter_registers()
                await asyncio.sleep(update_interval)

        asyncio.create_task(_meter_updater())

        log.info(
            "Iniciando servidor Modbus RTU '%s' em %s (baud=%d)",
            self.name,
            self.layout.serial_device,
            self.layout.baudrate,
        )

        await StartAsyncSerialServer(
            context=self.context,
            port=self.layout.serial_device,
            baudrate=self.layout.baudrate,
            parity=self.layout.parity,
            stopbits=self.layout.stopbits,
            bytesize=self.layout.bytesize,
            timeout=self.layout.timeout_s,
        )
