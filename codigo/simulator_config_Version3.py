from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml


@dataclass
class SerialPortConfig:
    device: str
    baudrate: int = 9600
    parity: str = "N"
    stopbits: int = 1
    bytesize: int = 8
    timeout_s: float = 0.2


@dataclass
class InverterConfig:
    slave_id: int
    p_nom_kw: float
    s_nom_kva: float
    tau_p_s: float = 1.0
    tau_q_s: float = 1.0


@dataclass
class MeterConfig:
    slave_id: int = 100
    base_address: int = 0x0099
    quantity_u16: int = 28


@dataclass
class SimulationConfig:
    mode: str = "full"              # "loopback" ou "full"
    tick_s: float = 0.01
    control_cycle_s: float = 2.0
    v_ll_v: float = 380.0
    load_profile_csv: Optional[str] = None
    load_p_kw: float = 50.0
    load_q_kvar: float = 0.0
    u_profile_csv: Optional[str] = None
    u_default: float = 1.0
    enable_logs: bool = True

    # ZIP (ANEEL)
    zip_p_Z: float = 0.50
    zip_p_I: float = 0.00
    zip_p_P: float = 0.50
    zip_q_Z: float = 0.00
    zip_q_I: float = 0.00
    zip_q_P: float = 1.00

    # Thévenin
    thevenin_vth_ll_v: float = 380.0
    thevenin_r_ohm: float = 0.00283
    thevenin_x_ohm: float = 0.01416

    # Medição MT
    v_mt_ll_v: float = 13800.0
    rtp: float = 120.0
    rtc: float = 200.0

    # Eventos
    events_file: Optional[str] = None
    events_poll_s: float = 2.0

    # Loopback: valores fixos para o medidor no modo loopback (SECUNDÁRIO)
    loopback_pf: float = 0.92
    loopback_v_mt_ln_v: float = 66.4     # V_sec fase-neutro TP (13800/√3/120)
    loopback_i_mt_a: float = 2.5         # I_sec TC (A)


@dataclass
class ComConfig:
    name: str
    serial: SerialPortConfig
    inverters: List[InverterConfig] = field(default_factory=list)
    meter: Optional[MeterConfig] = None


@dataclass
class AppConfig:
    simulation: SimulationConfig
    com1: ComConfig
    com2: ComConfig


def _require(d: Dict[str, Any], key: str) -> Any:
    if key not in d:
        raise ValueError(f"Missing key '{key}' in config")
    return d[key]


def load_config(path: str | Path) -> AppConfig:
    path = Path(path)
    data = yaml.safe_load(path.read_text(encoding="utf-8"))

    sim = data.get("simulation", {})
    simulation = SimulationConfig(
        mode=str(sim.get("mode", "full")),
        tick_s=float(sim.get("tick_s", 0.01)),
        control_cycle_s=float(sim.get("control_cycle_s", 2.0)),
        v_ll_v=float(sim.get("v_ll_v", 380.0)),
        load_profile_csv=sim.get("load_profile_csv"),
        load_p_kw=float(sim.get("load_p_kw", 50.0)),
        load_q_kvar=float(sim.get("load_q_kvar", 0.0)),
        u_profile_csv=sim.get("u_profile_csv"),
        u_default=float(sim.get("u_default", 1.0)),
        enable_logs=bool(sim.get("enable_logs", True)),
        # ZIP
        zip_p_Z=float(sim.get("zip_p_Z", 0.50)),
        zip_p_I=float(sim.get("zip_p_I", 0.00)),
        zip_p_P=float(sim.get("zip_p_P", 0.50)),
        zip_q_Z=float(sim.get("zip_q_Z", 0.00)),
        zip_q_I=float(sim.get("zip_q_I", 0.00)),
        zip_q_P=float(sim.get("zip_q_P", 1.00)),
        # Thévenin
        thevenin_vth_ll_v=float(sim.get("thevenin_vth_ll_v", 380.0)),
        thevenin_r_ohm=float(sim.get("thevenin_r_ohm", 0.00283)),
        thevenin_x_ohm=float(sim.get("thevenin_x_ohm", 0.01416)),
        # MT
        v_mt_ll_v=float(sim.get("v_mt_ll_v", 13800.0)),
        rtp=float(sim.get("rtp", 120.0)),
        rtc=float(sim.get("rtc", 200.0)),
        # Events
        events_file=sim.get("events_file"),
        events_poll_s=float(sim.get("events_poll_s", 2.0)),
        # Loopback
        loopback_pf=float(sim.get("loopback_pf", 0.92)),
        loopback_v_mt_ln_v=float(sim.get("loopback_v_mt_ln_v", 7967.0)),
        loopback_i_mt_a=float(sim.get("loopback_i_mt_a", 5.0)),
    )

    def parse_serial(sd: Dict[str, Any]) -> SerialPortConfig:
        return SerialPortConfig(
            device=str(_require(sd, "device")),
            baudrate=int(sd.get("baudrate", 9600)),
            parity=str(sd.get("parity", "N")),
            stopbits=int(sd.get("stopbits", 1)),
            bytesize=int(sd.get("bytesize", 8)),
            timeout_s=float(sd.get("timeout_s", 0.2)),
        )

    def parse_inverters(lst: List[Dict[str, Any]]) -> List[InverterConfig]:
        out: List[InverterConfig] = []
        for x in lst:
            out.append(
                InverterConfig(
                    slave_id=int(_require(x, "slave_id")),
                    p_nom_kw=float(_require(x, "p_nom_kw")),
                    s_nom_kva=float(x.get("s_nom_kva", x.get("p_nom_kw"))),
                    tau_p_s=float(x.get("tau_p_s", 1.0)),
                    tau_q_s=float(x.get("tau_q_s", 1.0)),
                )
            )
        return out

    def parse_com(cd: Dict[str, Any], name: str) -> ComConfig:
        serial = parse_serial(_require(cd, "serial"))
        inv = parse_inverters(cd.get("inverters", []))
        meter_cfg = None
        if "meter" in cd and cd["meter"] is not None:
            m = cd["meter"]
            meter_cfg = MeterConfig(
                slave_id=int(m.get("slave_id", 100)),
                base_address=int(m.get("base_address", 0x0099)),
                quantity_u16=int(m.get("quantity_u16", 28)),
            )
        return ComConfig(name=name, serial=serial, inverters=inv, meter=meter_cfg)

    com1 = parse_com(_require(data, "com1"), "COM1")
    com2 = parse_com(_require(data, "com2"), "COM2")

    return AppConfig(simulation=simulation, com1=com1, com2=com2)
