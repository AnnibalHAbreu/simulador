from __future__ import annotations

import argparse
import asyncio
import logging
import time

from simulator.config import load_config
from simulator.modbus_server import ModbusRtuPortServer, PortLayout
from simulator.profiles import LoadProfile, StepProfile
from simulator.simulation import InverterState, MeterState, PlantSimulation


def setup_logging(enable: bool):
    logging.basicConfig(
        level=logging.INFO if enable else logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


async def simulation_loop(sim: PlantSimulation):
    tick = sim.tick_s
    next_t = time.monotonic()
    while True:
        now = time.monotonic()
        if now < next_t:
            await asyncio.sleep(next_t - now)
        sim.step()
        next_t += tick


async def main_async(config_path: str):
    cfg = load_config(config_path)
    setup_logging(cfg.simulation.enable_logs)

    u_profile = StepProfile.from_csv(cfg.simulation.u_profile_csv, "time_s", "u") if cfg.simulation.u_profile_csv else None
    load_profile = LoadProfile.from_csv(cfg.simulation.load_profile_csv) if cfg.simulation.load_profile_csv else None

    all_inverters = []
    for ic in (cfg.com1.inverters + cfg.com2.inverters):
        all_inverters.append(
            InverterState(
                slave_id=ic.slave_id,
                p_nom_kw=ic.p_nom_kw,
                s_nom_kva=ic.s_nom_kva,
                alpha=ic.alpha,
                beta=ic.beta,
            )
        )

    meter = MeterState(slave_id=cfg.com1.meter.slave_id) if cfg.com1.meter else None

    sim = PlantSimulation(
        inverters=all_inverters,
        meter=meter,
        tick_s=cfg.simulation.tick_s,
        v_ll_v=cfg.simulation.v_ll_v,
        load_p_kw=cfg.simulation.load_p_kw,
        load_q_kvar=cfg.simulation.load_q_kvar,
        u_default=cfg.simulation.u_default,
        u_profile=u_profile,
        load_profile=load_profile,
    )

    srv1 = ModbusRtuPortServer(
        "COM1",
        PortLayout(
            serial_device=cfg.com1.serial.device,
            baudrate=cfg.com1.serial.baudrate,
            parity=cfg.com1.serial.parity,
            stopbits=cfg.com1.serial.stopbits,
            bytesize=cfg.com1.serial.bytesize,
            timeout_s=cfg.com1.serial.timeout_s,
            inverter_slave_ids=tuple(i.slave_id for i in cfg.com1.inverters),
            meter_slave_id=(cfg.com1.meter.slave_id if cfg.com1.meter else None),
            meter_base_addr=(cfg.com1.meter.base_address if cfg.com1.meter else 0x0099),
            meter_quantity_u16=(cfg.com1.meter.quantity_u16 if cfg.com1.meter else 28),
        ),
        sim,
    )

    srv2 = ModbusRtuPortServer(
        "COM2",
        PortLayout(
            serial_device=cfg.com2.serial.device,
            baudrate=cfg.com2.serial.baudrate,
            parity=cfg.com2.serial.parity,
            stopbits=cfg.com2.serial.stopbits,
            bytesize=cfg.com2.serial.bytesize,
            timeout_s=cfg.com2.serial.timeout_s,
            inverter_slave_ids=tuple(i.slave_id for i in cfg.com2.inverters),
            meter_slave_id=None,
        ),
        sim,
    )

    await asyncio.gather(
        simulation_loop(sim),
        srv1.run(cfg.simulation.tick_s),
        srv2.run(cfg.simulation.tick_s),
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="configs/config.yaml")
    args = ap.parse_args()
    asyncio.run(main_async(args.config))


if __name__ == "__main__":
    main()