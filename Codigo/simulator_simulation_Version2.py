from __future__ import annotations

from dataclasses import dataclass
from math import acos, sqrt, tan
from typing import Dict, List, Optional, Tuple

from simulator.profiles import LoadProfile, StepProfile


def sat(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


@dataclass
class InverterState:
    slave_id: int
    p_nom_kw: float
    s_nom_kva: float
    alpha: float
    beta: float

    # setpoints (via Modbus)
    p_ref_pct: float = 0.0  # 0..100
    pf_cmd_raw: int = 100  # 1..20 or 80..100; invalid => 100

    # internal states
    p_kw: float = 0.0
    q_kvar: float = 0.0

    # availability
    u: float = 1.0

    # events
    comms_drop: bool = False
    frozen_s: float = 0.0


@dataclass
class MeterState:
    slave_id: int
    # outputs (for registers)
    pfa: float = 1.0
    pfb: float = 1.0
    pfc: float = 1.0
    ia_a: float = 0.0
    ib_a: float = 0.0
    ic_a: float = 0.0
    ua_v: float = 0.0
    ub_v: float = 0.0
    uc_v: float = 0.0

    # internal (optional)
    p_pcc_kw: float = 0.0
    q_pcc_kvar: float = 0.0
    v_ll_v: float = 380.0


class PlantSimulation:
    def __init__(
        self,
        inverters: List[InverterState],
        meter: Optional[MeterState],
        tick_s: float,
        v_ll_v: float,
        load_p_kw: float,
        load_q_kvar: float,
        u_default: float = 1.0,
        u_profile: Optional[StepProfile] = None,
        load_profile: Optional[LoadProfile] = None,
    ):
        self.inverters: Dict[int, InverterState] = {inv.slave_id: inv for inv in inverters}
        self.meter = meter
        self.tick_s = tick_s
        self.v_ll_v = v_ll_v

        self.load_p_kw_default = load_p_kw
        self.load_q_kvar_default = load_q_kvar
        self.u_default = u_default

        self.u_profile = u_profile
        self.load_profile = load_profile

        self.t_s = 0.0

    def set_inverter_setpoint_pct(self, slave_id: int, pct: float) -> None:
        self.inverters[slave_id].p_ref_pct = sat(pct, 0.0, 100.0)

    def set_inverter_pf_raw(self, slave_id: int, raw: int) -> None:
        self.inverters[slave_id].pf_cmd_raw = int(raw)

    def _decode_pf(self, raw: int) -> Tuple[float, int]:
        """
        Retorna (pf_magnitude, sign_q)
        sign_q: +1 => leading (injeta Q), -1 => lagging (consome Q), 0 => unitário
        """
        if 1 <= raw <= 20:
            pf = 1.0 - raw * 0.01
            return sat(pf, 0.8, 0.99), -1
        if 80 <= raw <= 100:
            pf = raw / 100.0
            if raw == 100:
                return 1.0, 0
            return sat(pf, 0.8, 1.0), +1
        return 1.0, 0

    def step(self) -> None:
        self.t_s += self.tick_s
        t_int = int(self.t_s)

        # profiles
        u = self.u_profile.value(t_int, self.u_default) if self.u_profile else self.u_default
        u = sat(u, 0.0, 1.0)

        load_p_kw, load_q_kvar = (
            self.load_profile.value(t_int, self.load_p_kw_default, self.load_q_kvar_default)
            if self.load_profile
            else (self.load_p_kw_default, self.load_q_kvar_default)
        )

        # update inverters
        for inv in self.inverters.values():
            inv.u = u

            if inv.frozen_s > 0:
                inv.frozen_s = max(0.0, inv.frozen_s - self.tick_s)
                continue

            p_avail = inv.u * inv.p_nom_kw
            p_ref = (inv.p_ref_pct / 100.0) * inv.p_nom_kw

            inv.p_kw = sat(inv.p_kw + inv.alpha * (p_ref - inv.p_kw), 0.0, p_avail)

            pf_mag, sign_q = self._decode_pf(inv.pf_cmd_raw)
            if pf_mag >= 0.999 or sign_q == 0:
                q_ref = 0.0
            else:
                q_ref = float(sign_q) * inv.p_kw * tan(acos(pf_mag))

            q_lim = sqrt(max(0.0, inv.s_nom_kva * inv.s_nom_kva - inv.p_kw * inv.p_kw))
            inv.q_kvar = sat(inv.q_kvar + inv.beta * (q_ref - inv.q_kvar), -q_lim, +q_lim)

        # pcc
        p_gen = sum(inv.p_kw for inv in self.inverters.values())
        q_gen = sum(inv.q_kvar for inv in self.inverters.values())

        p_pcc = load_p_kw - p_gen
        q_pcc = load_q_kvar - q_gen
        s_pcc = sqrt(p_pcc * p_pcc + q_pcc * q_pcc)

        # meter balanced 3-phase
        if self.meter:
            self.meter.p_pcc_kw = p_pcc
            self.meter.q_pcc_kvar = q_pcc
            self.meter.v_ll_v = self.v_ll_v

            v_ln = self.v_ll_v / sqrt(3.0) if self.v_ll_v > 0 else 0.0
            i_total = (s_pcc * 1000.0) / (sqrt(3.0) * self.v_ll_v) if self.v_ll_v > 0 else 0.0

            pf_mag = abs(p_pcc) / s_pcc if s_pcc > 1e-9 else 1.0
            # aqui PF é magnitude; sinal (cap/ind) pode ser inferido de Q se você quiser
            self.meter.pfa = pf_mag
            self.meter.pfb = pf_mag
            self.meter.pfc = pf_mag

            self.meter.ia_a = i_total
            self.meter.ib_a = i_total
            self.meter.ic_a = i_total

            self.meter.ua_v = v_ln
            self.meter.ub_v = v_ln
            self.meter.uc_v = v_ln