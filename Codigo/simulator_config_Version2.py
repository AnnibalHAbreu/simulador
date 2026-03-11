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
    alpha: float = 0.2
    beta: float = 0.2


@dataclass
class MeterConfig:
    slave_id: int = 100
    base_address: int = 0x0099
    quantity_u16: int = 28  # consolidado: 28 registradores (28 x U16)


@dataclass
class SimulationConfig:
    tick_s: float = 2.0  # consolidado: passo do simulador = 2 s
    v_ll_v: float = 380.0
    load_profile_csv: Optional[str] = None  # time_s,P_load_kW,Q_load_kVAr
    load_p_kw: float = 50.0
    load_q_kvar: float = 0.0
    u_profile_csv: Optional[str] = None  # time_s,u
    u_default: float = 1.0
    enable_logs: bool = True


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
        tick_s=float(sim.get("tick_s", 2.0)),
        v_ll_v=float(sim.get("v_ll_v", 380.0)),
        load_profile_csv=sim.get("load_profile_csv"),
        load_p_kw=float(sim.get("load_p_kw", 50.0)),
        load_q_kvar=float(sim.get("load_q_kvar", 0.0)),
        u_profile_csv=sim.get("u_profile_csv"),
        u_default=float(sim.get("u_default", 1.0)),
        enable_logs=bool(sim.get("enable_logs", True)),
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
                    alpha=float(x.get("alpha", 0.2)),
                    beta=float(x.get("beta", 0.2)),
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