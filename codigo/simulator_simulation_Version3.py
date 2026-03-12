from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from math import acos, sqrt, tan
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from simulator.profiles import LoadProfile, StepProfile

log = logging.getLogger("simulator.simulation")


def sat(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


# ---------------------------------------------------------------------------
# Equivalente de Thévenin (por fase, monofásico equivalente)
# ---------------------------------------------------------------------------
@dataclass
class TheveninModel:
    """
    Rede upstream: Vth + Zth por fase (referido ao BT).
    Aproximação linearizada:
        V_pcc_fase ≈ Vth_fase - (R·P_fase + X·Q_fase) / Vth_fase
    """
    vth_ll_v: float = 380.0
    r_ohm: float = 0.00283
    x_ohm: float = 0.01416

    def v_pcc_ll(self, p_pcc_kw: float, q_pcc_kvar: float) -> float:
        """Tensão LL no PCC. P/Q trifásicos, convenção: >0 = importação."""
        vth_fase = self.vth_ll_v / sqrt(3.0)
        if vth_fase < 1.0:
            return 0.0
        p_fase_w = p_pcc_kw * 1000.0 / 3.0
        q_fase_var = q_pcc_kvar * 1000.0 / 3.0
        delta_v = (self.r_ohm * p_fase_w + self.x_ohm * q_fase_var) / vth_fase
        v_pcc_fase = vth_fase - delta_v
        return max(0.0, v_pcc_fase * sqrt(3.0))


# ---------------------------------------------------------------------------
# Modelo de carga ZIP (premissa ANEEL)
# ---------------------------------------------------------------------------
@dataclass
class ZipLoadModel:
    """
    ANEEL (perdas técnicas alimentadores):
      Ativo:   50% Z + 50% P
      Reativo: 100% P
    """
    a_Z: float = 0.50
    a_I: float = 0.00
    a_P: float = 0.50
    b_Z: float = 0.00
    b_I: float = 0.00
    b_P: float = 1.00

    def evaluate(self, p0_kw: float, q0_kvar: float,
                 v_ll_v: float, v0_ll_v: float) -> Tuple[float, float]:
        if v0_ll_v < 1.0:
            return p0_kw, q0_kvar
        vr = v_ll_v / v0_ll_v
        vr2 = vr * vr
        p = p0_kw * (self.a_Z * vr2 + self.a_I * vr + self.a_P)
        q = q0_kvar * (self.b_Z * vr2 + self.b_I * vr + self.b_P)
        return p, q


# ---------------------------------------------------------------------------
# Cache de eventos
# ---------------------------------------------------------------------------
@dataclass
class EventsCache:
    drop_comms: Set[int] = None
    freeze_s: Dict[int, float] = None
    force_u: Dict[int, float] = None

    def __post_init__(self):
        if self.drop_comms is None:
            self.drop_comms = set()
        if self.freeze_s is None:
            self.freeze_s = {}
        if self.force_u is None:
            self.force_u = {}


# ---------------------------------------------------------------------------
# Estado do inversor
# ---------------------------------------------------------------------------
@dataclass
class InverterState:
    slave_id: int
    p_nom_kw: float
    s_nom_kva: float
    tau_p_s: float
    tau_q_s: float

    # setpoints (escritos pelo callback Modbus)
    p_ref_pct: float = 0.0
    pf_cmd_raw: int = 100

    # estados internos
    p_kw: float = 0.0
    q_kvar: float = 0.0

    # disponibilidade
    u: float = 1.0

    # eventos
    comms_drop: bool = False
    frozen_s: float = 0.0


# ---------------------------------------------------------------------------
# Estado do medidor
# ---------------------------------------------------------------------------
@dataclass
class MeterState:
    slave_id: int
    # saídas para registradores (grandezas primárias MT)
    pfa: float = 1.0
    pfb: float = 1.0
    pfc: float = 1.0
    ia_a: float = 0.0
    ib_a: float = 0.0
    ic_a: float = 0.0
    ua_v: float = 0.0
    ub_v: float = 0.0
    uc_v: float = 0.0

    # internos
    p_pcc_kw: float = 0.0
    q_pcc_kvar: float = 0.0
    v_pcc_ll_v: float = 380.0


# ---------------------------------------------------------------------------
# Simulação da planta
# ---------------------------------------------------------------------------
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
        thevenin: Optional[TheveninModel] = None,
        zip_load: Optional[ZipLoadModel] = None,
        v_mt_ll_v: float = 13800.0,
        rtp: float = 120.0,
        rtc: float = 200.0,
        events_file: Optional[str] = None,
        events_poll_s: float = 2.0,
        mode: str = "full",
        loopback_pf: float = 0.92,
        loopback_v_mt_ln_v: float = 7967.0,
        loopback_i_mt_a: float = 5.0,
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
        self.thevenin = thevenin or TheveninModel(vth_ll_v=v_ll_v)
        self.zip_load = zip_load or ZipLoadModel()

        self.v_mt_ll_v = v_mt_ll_v
        self.rtp = rtp
        self.rtc = rtc

        self.events_file = events_file
        self.events_poll_s = events_poll_s
        self._events_last_poll_t: float = -1.0
        self._events_cache = EventsCache()

        self.mode = mode
        self.loopback_pf = loopback_pf
        self.loopback_v_mt_ln_v = loopback_v_mt_ln_v
        self.loopback_i_mt_a = loopback_i_mt_a

        self.t_s: float = 0.0
        self.v_pcc_ll_v: float = v_ll_v

        # Em modo loopback, preencher medidor com valores fixos imediatamente
        if self.mode == "loopback" and self.meter:
            self._init_loopback_meter()

    # --- loopback ---

    def _init_loopback_meter(self) -> None:
        """Preenche o medidor com valores fixos e conhecidos para teste Modbus."""
        m = self.meter
        m.pfa = self.loopback_pf
        m.pfb = self.loopback_pf
        m.pfc = self.loopback_pf
        m.ia_a = self.loopback_i_mt_a
        m.ib_a = self.loopback_i_mt_a
        m.ic_a = self.loopback_i_mt_a
        m.ua_v = self.loopback_v_mt_ln_v
        m.ub_v = self.loopback_v_mt_ln_v
        m.uc_v = self.loopback_v_mt_ln_v
        log.info(
            "Modo LOOPBACK: medidor fixo PF=%.2f, V=%.1f V, I=%.2f A",
            self.loopback_pf, self.loopback_v_mt_ln_v, self.loopback_i_mt_a,
        )

    # --- setpoints (chamados pelo callback Modbus) ---

    def set_inverter_setpoint_pct(self, slave_id: int, pct: float) -> None:
        inv = self.inverters[slave_id]
        inv.p_ref_pct = sat(pct, 0.0, 100.0)
        if self.mode == "loopback":
            log.info("LOOPBACK RX: inv %d → setpoint P = %.1f %%", slave_id, inv.p_ref_pct)

    def set_inverter_pf_raw(self, slave_id: int, raw: int) -> None:
        inv = self.inverters[slave_id]
        inv.pf_cmd_raw = int(raw)
        if self.mode == "loopback":
            log.info("LOOPBACK RX: inv %d → PF raw = %d", slave_id, inv.pf_cmd_raw)

    # --- decodificação PF ---

    @staticmethod
    def _decode_pf(raw: int) -> Tuple[float, int]:
        """(pf_magnitude, sign_q): +1=leading, -1=lagging, 0=unitário."""
        if 1 <= raw <= 20:
            pf = 1.0 - raw * 0.01
            return sat(pf, 0.8, 0.99), -1
        if 80 <= raw <= 100:
            pf = raw / 100.0
            if raw == 100:
                return 1.0, 0
            return sat(pf, 0.8, 1.0), +1
        return 1.0, 0

    # --- eventos ---

    def _poll_events(self) -> None:
        if not self.events_file:
            return
        if self.t_s - self._events_last_poll_t < self.events_poll_s:
            return
        self._events_last_poll_t = self.t_s

        path = Path(self.events_file)
        if not path.exists():
            self._events_cache = EventsCache()
            return
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError) as e:
            log.warning("Erro ao ler events file: %s", e)
            return

        self._events_cache = EventsCache(
            drop_comms=set(data.get("drop_comms", [])),
            freeze_s={int(k): float(v) for k, v in data.get("freeze_s", {}).items()},
            force_u={int(k): float(v) for k, v in data.get("force_u", {}).items()},
        )

        for sid, secs in self._events_cache.freeze_s.items():
            if sid in self.inverters:
                self.inverters[sid].frozen_s = max(self.inverters[sid].frozen_s, secs)

    # --- passo de simulação ---

    def step(self) -> None:
        # Em modo loopback, apenas avança o tempo (medidor já está com valores fixos)
        if self.mode == "loopback":
            self.t_s += self.tick_s
            return

        # === Modo FULL: simulação completa ===
        self.t_s += self.tick_s
        t_int = int(self.t_s)

        self._poll_events()
        ev = self._events_cache

        # --- perfis ---
        u_global = (
            self.u_profile.value(t_int, self.u_default)
            if self.u_profile else self.u_default
        )
        u_global = sat(u_global, 0.0, 1.0)

        load_p0_kw, load_q0_kvar = (
            self.load_profile.value(t_int, self.load_p_kw_default, self.load_q_kvar_default)
            if self.load_profile
            else (self.load_p_kw_default, self.load_q_kvar_default)
        )

        # --- snapshot atômico dos setpoints ---
        setpoints: Dict[int, Tuple[float, int]] = {}
        for sid, inv in self.inverters.items():
            setpoints[sid] = (inv.p_ref_pct, inv.pf_cmd_raw)

        # --- atualizar inversores ---
        for sid, inv in self.inverters.items():
            if sid in ev.force_u:
                inv.u = sat(ev.force_u[sid], 0.0, 1.0)
            else:
                inv.u = u_global

            inv.comms_drop = (sid in ev.drop_comms)
            if inv.comms_drop:
                inv.p_ref_pct = max(0.0, inv.p_ref_pct - (self.tick_s / 5.0) * 100.0)

            if inv.frozen_s > 0:
                inv.frozen_s = max(0.0, inv.frozen_s - self.tick_s)
                continue

            sp_pct, sp_pf_raw = setpoints[sid]

            alpha_eff = self.tick_s / inv.tau_p_s if inv.tau_p_s > 0 else 1.0
            beta_eff = self.tick_s / inv.tau_q_s if inv.tau_q_s > 0 else 1.0

            p_avail = inv.u * inv.p_nom_kw
            p_ref = (sp_pct / 100.0) * inv.p_nom_kw

            inv.p_kw = sat(
                inv.p_kw + alpha_eff * (p_ref - inv.p_kw),
                0.0, p_avail
            )

            pf_mag, sign_q = self._decode_pf(sp_pf_raw)
            if pf_mag >= 0.999 or sign_q == 0:
                q_ref = 0.0
            else:
                q_ref = float(sign_q) * inv.p_kw * tan(acos(pf_mag))

            q_lim = sqrt(max(0.0, inv.s_nom_kva ** 2 - inv.p_kw ** 2))
            inv.q_kvar = sat(
                inv.q_kvar + beta_eff * (q_ref - inv.q_kvar),
                -q_lim, +q_lim
            )

        # --- agregação PCC ---
        p_gen = sum(inv.p_kw for inv in self.inverters.values())
        q_gen = sum(inv.q_kvar for inv in self.inverters.values())

        p_pcc = load_p0_kw - p_gen
        q_pcc = load_q0_kvar - q_gen

        self.v_pcc_ll_v = self.thevenin.v_pcc_ll(p_pcc, q_pcc)

        load_p_kw, load_q_kvar = self.zip_load.evaluate(
            load_p0_kw, load_q0_kvar,
            self.v_pcc_ll_v, self.v_ll_v
        )

        p_pcc = load_p_kw - p_gen
        q_pcc = load_q_kvar - q_gen
        s_pcc = sqrt(p_pcc * p_pcc + q_pcc * q_pcc)

        self.v_pcc_ll_v = self.thevenin.v_pcc_ll(p_pcc, q_pcc)

        # --- atualizar medidor ---
        if self.meter:
            self.meter.p_pcc_kw = p_pcc
            self.meter.q_pcc_kvar = q_pcc
            self.meter.v_pcc_ll_v = self.v_pcc_ll_v

            v_pcc_ln = self.v_pcc_ll_v / sqrt(3.0) if self.v_pcc_ll_v > 0 else 0.0

            pf_mag = abs(p_pcc) / s_pcc if s_pcc > 1e-9 else 1.0
            pf_signed = pf_mag if q_pcc >= 0 else -pf_mag

            self.meter.pfa = pf_signed
            self.meter.pfb = pf_signed
            self.meter.pfc = pf_signed

            v_mt_ln = v_pcc_ln * (self.v_mt_ll_v / self.v_ll_v) if self.v_ll_v > 0 else 0.0
            v_mt_ll = v_mt_ln * sqrt(3.0)

            i_mt = (s_pcc * 1000.0) / (sqrt(3.0) * v_mt_ll) if v_mt_ll > 0 else 0.0

            self.meter.ia_a = i_mt
            self.meter.ib_a = i_mt
            self.meter.ic_a = i_mt

            self.meter.ua_v = v_mt_ln
            self.meter.ub_v = v_mt_ln
            self.meter.uc_v = v_mt_ln
