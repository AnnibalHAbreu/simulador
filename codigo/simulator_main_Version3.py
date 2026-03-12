from __future__ import annotations

import argparse
import asyncio
import logging
import time

from simulator.config import load_config
from simulator.modbus_server import ModbusRtuPortServer, PortLayout
from simulator.profiles import LoadProfile, StepProfile
from simulator.simulation import (
    InverterState,
    MeterState,
    PlantSimulation,
    TheveninModel,
    ZipLoadModel,
)

log = logging.getLogger("simulator.main")


def setup_logging(enable: bool):
    logging.basicConfig(
        level=logging.INFO if enable else logging.WARNING,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


async def simulation_loop(sim: PlantSimulation):
    """Loop de simulação a cada tick_s (10 ms). Detecta overrun."""
    tick = sim.tick_s
    next_t = time.monotonic()
    overrun_threshold = 3 * tick

    while True:
        now = time.monotonic()
        if now < next_t:
            await asyncio.sleep(next_t - now)
        else:
            lag = now - next_t
            if lag > overrun_threshold:
                skipped = int(lag / tick)
                log.warning(
                    "Overrun detectado: atraso=%.1f ms, descartando %d ticks",
                    lag * 1000.0, skipped
                )
                sim.t_s += skipped * tick
                next_t = now

        sim.step()
        next_t += tick


async def loopback_idle(sim: PlantSimulation):
    """No modo loopback, apenas mantém o event loop vivo. Sem simulação."""
    log.info("Modo LOOPBACK: simulação desligada, apenas servidores Modbus ativos.")
    while True:
        await asyncio.sleep(10.0)


async def main_async(config_path: str):
    cfg = load_config(config_path)
    setup_logging(cfg.simulation.enable_logs)

    mode = cfg.simulation.mode
    if mode not in ("loopback", "full"):
        raise ValueError(f"Modo inválido: '{mode}'. Use 'loopback' ou 'full'.")

    # Perfis (ignorados no modo loopback, mas carregados se existirem)
    u_profile = (
        StepProfile.from_csv(cfg.simulation.u_profile_csv, "time_s", "u")
        if cfg.simulation.u_profile_csv and mode == "full" else None
    )
    load_profile = (
        LoadProfile.from_csv(cfg.simulation.load_profile_csv)
        if cfg.simulation.load_profile_csv and mode == "full" else None
    )

    # Inversores
    all_inverters = []
    for ic in (cfg.com1.inverters + cfg.com2.inverters):
        all_inverters.append(
            InverterState(
                slave_id=ic.slave_id,
                p_nom_kw=ic.p_nom_kw,
                s_nom_kva=ic.s_nom_kva,
                tau_p_s=ic.tau_p_s,
                tau_q_s=ic.tau_q_s,
            )
        )

    # Medidor
    meter = MeterState(slave_id=cfg.com1.meter.slave_id) if cfg.com1.meter else None

    # Thévenin e ZIP (só usados no modo full, mas instanciados sempre)
    thevenin = TheveninModel(
        vth_ll_v=cfg.simulation.thevenin_vth_ll_v,
        r_ohm=cfg.simulation.thevenin_r_ohm,
        x_ohm=cfg.simulation.thevenin_x_ohm,
    )
    zip_load = ZipLoadModel(
        a_Z=cfg.simulation.zip_p_Z,
        a_I=cfg.simulation.zip_p_I,
        a_P=cfg.simulation.zip_p_P,
        b_Z=cfg.simulation.zip_q_Z,
        b_I=cfg.simulation.zip_q_I,
        b_P=cfg.simulation.zip_q_P,
    )

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
        thevenin=thevenin,
        zip_load=zip_load,
        v_mt_ll_v=cfg.simulation.v_mt_ll_v,
        rtp=cfg.simulation.rtp,
        rtc=cfg.simulation.rtc,
        events_file=cfg.simulation.events_file,
        events_poll_s=cfg.simulation.events_poll_s,
        mode=mode,
        loopback_pf=cfg.simulation.loopback_pf,
        loopback_v_mt_ln_v=cfg.simulation.loopback_v_mt_ln_v,
        loopback_i_mt_a=cfg.simulation.loopback_i_mt_a,
    )

    if mode == "loopback":
        log.info(
            "=== ETAPA 1: LOOPBACK — teste de comunicação Modbus ===\n"
            "  Medidor: PF=%.2f, V=%.1f V, I=%.2f A (fixos)\n"
            "  Inversores: aceitam FC16, logam setpoints recebidos\n"
            "  Simulação física: DESLIGADA",
            cfg.simulation.loopback_pf,
            cfg.simulation.loopback_v_mt_ln_v,
            cfg.simulation.loopback_i_mt_a,
        )
    else:
        log.info(
            "=== ETAPA 2: FULL — simulação completa ===\n"
            "  tick=%.0f ms, inversores=%d\n"
            "  Thévenin R=%.5f X=%.5f ohm\n"
            "  ZIP P: Z=%.0f%% I=%.0f%% P=%.0f%%\n"
            "  ZIP Q: Z=%.0f%% I=%.0f%% P=%.0f%%",
            cfg.simulation.tick_s * 1000, len(all_inverters),
            cfg.simulation.thevenin_r_ohm, cfg.simulation.thevenin_x_ohm,
            cfg.simulation.zip_p_Z * 100, cfg.simulation.zip_p_I * 100, cfg.simulation.zip_p_P * 100,
            cfg.simulation.zip_q_Z * 100, cfg.simulation.zip_q_I * 100, cfg.simulation.zip_q_P * 100,
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

    # Escolher task de simulação conforme modo
    sim_task = loopback_idle(sim) if mode == "loopback" else simulation_loop(sim)

    await asyncio.gather(
        sim_task,
        srv1.run(cfg.simulation.tick_s),
        srv2.run(cfg.simulation.tick_s),
    )


def main():
    ap = argparse.ArgumentParser(description="Simulador de Usina FV - Version 3")
    ap.add_argument("--config", default="configs/config.yaml")
    args = ap.parse_args()
    asyncio.run(main_async(args.config))


if __name__ == "__main__":
    main()
