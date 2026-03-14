from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from math import acos, sqrt, tan
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple

from simulator.profiles import LoadProfile, StepProfile

log = logging.getLogger("simulator.simulation")


# ---------------------------------------------------------------------------
# Utilitário
# ---------------------------------------------------------------------------

def sat(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


# ---------------------------------------------------------------------------
# Equivalente de Thévenin (monofásico equivalente, referido ao BT)
# ---------------------------------------------------------------------------

@dataclass
class TheveninModel:
    """
    Aproximação linearizada de 1ª ordem:
        V_pcc_fase ≈ Vth_fase − (R·P_fase + X·Q_fase) / Vth_fase

    Convenção de P_pcc / Q_pcc:
        > 0  →  importação da rede  →  tensão cai
        < 0  →  exportação para rede →  tensão sobe
    """
    vth_ll_v: float = 380.0
    r_ohm: float = 0.00283
    x_ohm: float = 0.01416

    def v_pcc_ll(self, p_pcc_kw: float, q_pcc_kvar: float) -> float:
        """Retorna tensão linha-linha no PCC (V)."""
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
    Coeficientes ZIP para P e Q.
    ANEEL (perdas técnicas em alimentadores):
        P: 50% Z + 50% P constante
        Q: 100% P constante
    """
    a_Z: float = 0.50   # fração potência constante-Z  (P)
    a_I: float = 0.00   # fração corrente constante     (P)
    a_P: float = 0.50   # fração potência constante-P   (P)
    b_Z: float = 0.00   # fração potência constante-Z  (Q)
    b_I: float = 0.00   # fração corrente constante     (Q)
    b_P: float = 1.00   # fração potência constante-P   (Q)

    def evaluate(
        self,
        p0_kw: float,
        q0_kvar: float,
        v_ll_v: float,
        v0_ll_v: float,
    ) -> Tuple[float, float]:
        """Retorna (P_kW, Q_kVAr) ajustados pela tensão atual."""
        if v0_ll_v < 1.0:
            return p0_kw, q0_kvar
        vr = v_ll_v / v0_ll_v
        vr2 = vr * vr
        p = p0_kw * (self.a_Z * vr2 + self.a_I * vr + self.a_P)
        q = q0_kvar * (self.b_Z * vr2 + self.b_I * vr + self.b_P)
        return p, q


# ---------------------------------------------------------------------------
# Cache de eventos (injeção de falhas em tempo real)
# ---------------------------------------------------------------------------

@dataclass
class EventsCache:
    drop_comms: Set[int] = field(default_factory=set)
    freeze_s: Dict[int, float] = field(default_factory=dict)
    force_u: Dict[int, float] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Estado individual do inversor
# ---------------------------------------------------------------------------

@dataclass
class InverterState:
    slave_id: int
    p_nom_kw: float
    s_nom_kva: float
    tau_p_s: float
    tau_q_s: float

    # Setpoints escritos pelo callback Modbus (thread-safe via GIL do CPython)
    p_ref_pct: float = 0.0
    pf_cmd_raw: int = 100

    # Estados internos da dinâmica de 1ª ordem
    p_kw: float = 0.0
    q_kvar: float = 0.0

    # Disponibilidade de energia (irradiância normalizada [0..1])
    u: float = 1.0

    # Flags de eventos
    comms_drop: bool = False
    frozen_s: float = 0.0


# ---------------------------------------------------------------------------
# Estado do medidor no PCC
# ---------------------------------------------------------------------------

@dataclass
class MeterState:
    slave_id: int

    # Grandezas no SECUNDÁRIO dos instrumentos de medição (TP / TC).
    # O PLC multiplica por RTP/RTC para reconstruir as grandezas primárias.
    pfa: float = 1.0
    pfb: float = 1.0
    pfc: float = 1.0
    ia_a: float = 0.0    # corrente secundário TC (A); I_prim = ia_a × RTC
    ib_a: float = 0.0
    ic_a: float = 0.0
    ua_v: float = 0.0    # tensão secundário TP fase-neutro (V); V_prim = ua_v × RTP
    ub_v: float = 0.0
    uc_v: float = 0.0

    # Grandezas internas (não enviadas via Modbus, usadas p/ debug)
    p_pcc_kw: float = 0.0
    q_pcc_kvar: float = 0.0
    v_pcc_ll_v: float = 380.0


# ---------------------------------------------------------------------------
# Simulação da planta completa
# ---------------------------------------------------------------------------

class PlantSimulation:
    """
    Modos de operação:
      loopback  — servidores Modbus ativos, medidor com valores fixos,
                  sem simulação física. Etapa 1: validar comunicação.
      openloop  — simulação física ativa, carga e irradiância fixas (YAML),
                  perfis CSV e eventos ignorados. Etapa 2: validar controlador.
      full      — simulação completa: física + perfis CSV + eventos em tempo real.
                  Etapa 3: teste com perturbações.
    """

    VALID_MODES = frozenset({"loopback", "openloop", "full"})

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
        loopback_v_mt_ln_v: float = 66.4,
        loopback_i_mt_a: float = 2.5,
    ):
        if mode not in self.VALID_MODES:
            raise ValueError(f"Modo inválido: '{mode}'. Use: {sorted(self.VALID_MODES)}")

        self.inverters: Dict[int, InverterState] = {
            inv.slave_id: inv for inv in inverters
        }
        self.meter = meter
        self.tick_s = tick_s
        self.v_ll_v = v_ll_v

        self.load_p_kw_default = load_p_kw
        self.load_q_kvar_default = load_q_kvar
        self.u_default = u_default

        # Perfis (usados apenas no modo full)
        self.u_profile = u_profile
        self.load_profile = load_profile

        # Modelos físicos (usados nos modos openloop e full)
        self.thevenin = thevenin or TheveninModel(vth_ll_v=v_ll_v)
        self.zip_load = zip_load or ZipLoadModel()

        # Parâmetros de medição MT
        self.v_mt_ll_v = v_mt_ll_v
        self.rtp = rtp
        self.rtc = rtc

        # Eventos (usados apenas no modo full)
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

        # Modo loopback: preencher medidor com valores fixos imediatamente
        if self.mode == "loopback" and self.meter:
            self._init_loopback_meter()

    # -----------------------------------------------------------------------
    # Loopback: medidor com valores fixos conhecidos
    # -----------------------------------------------------------------------

    def _init_loopback_meter(self) -> None:
        """
        Preenche o medidor com valores fixos no secundário dos instrumentos.
        PLC multiplica por RTP (tensão) e RTC (corrente) para reconstruir primário.

        Valores esperados nos registradores U16:
          PF  = loopback_pf × 16384
          I   = loopback_i_mt_a × 256
          V   = loopback_v_mt_ln_v × 128
        """
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
            "Modo LOOPBACK: medidor fixo PF=%.2f, V_sec=%.2f V, I_sec=%.3f A",
            self.loopback_pf,
            self.loopback_v_mt_ln_v,
            self.loopback_i_mt_a,
        )

    # -----------------------------------------------------------------------
    # Interface de setpoints — chamada pelo callback Modbus (FC16)
    # -----------------------------------------------------------------------

    def set_inverter_setpoint_pct(self, slave_id: int, pct: float) -> None:
        inv = self.inverters.get(slave_id)
        if inv is None:
            log.warning("set_setpoint_pct: slave_id %d não encontrado", slave_id)
            return
        inv.p_ref_pct = sat(pct, 0.0, 100.0)
        if self.mode == "loopback":
            log.info(
                "LOOPBACK RX: inv %d → setpoint P = %.1f %%",
                slave_id,
                inv.p_ref_pct,
            )

    def set_inverter_pf_raw(self, slave_id: int, raw: int) -> None:
        inv = self.inverters.get(slave_id)
        if inv is None:
            log.warning("set_pf_raw: slave_id %d não encontrado", slave_id)
            return
        inv.pf_cmd_raw = int(raw)
        if self.mode == "loopback":
            log.info("LOOPBACK RX: inv %d → PF raw = %d", slave_id, inv.pf_cmd_raw)

    # -----------------------------------------------------------------------
    # Decodificação do comando de PF (U16 → magnitude + sinal de Q)
    # -----------------------------------------------------------------------

    @staticmethod
    def _decode_pf(raw: int) -> Tuple[float, int]:
        """
        Retorna (pf_magnitude, sign_q).
          sign_q = +1  → leading (capacitivo, injeta Q, Q > 0)
          sign_q = -1  → lagging (indutivo, consome Q, Q < 0)
          sign_q =  0  → unitário (Q = 0)

        Faixas válidas:
          1–20   → lagging:  PF = 1.00 − raw × 0.01  (0.80 .. 0.99)
          80–99  → leading:  PF = raw / 100           (0.80 .. 0.99)
          100    → unitário: PF = 1.0
          21–79  → inválido: tratado como unitário
        """
        if 1 <= raw <= 20:
            pf = sat(1.0 - raw * 0.01, 0.80, 0.99)
            return pf, -1
        if 80 <= raw <= 99:
            pf = sat(raw / 100.0, 0.80, 0.99)
            return pf, +1
        if raw == 100:
            return 1.0, 0
        # fora de faixa → unitário
        return 1.0, 0

    # -----------------------------------------------------------------------
    # Leitura de eventos em tempo real (apenas modo full)
    # -----------------------------------------------------------------------

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
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Erro ao ler events_file '%s': %s", self.events_file, exc)
            return

        new_freeze = {
            int(k): float(v) for k, v in data.get("freeze_s", {}).items()
        }
        # Accumula freeze: usa o maior valor entre o restante e o novo
        for sid, secs in new_freeze.items():
            if sid in self.inverters:
                self.inverters[sid].frozen_s = max(
                    self.inverters[sid].frozen_s, secs
                )

        self._events_cache = EventsCache(
            drop_comms=set(data.get("drop_comms", [])),
            freeze_s=new_freeze,
            force_u={
                int(k): float(v) for k, v in data.get("force_u", {}).items()
            },
        )

    # -----------------------------------------------------------------------
    # Passo de simulação — chamado a cada tick_s pelo loop assíncrono
    # -----------------------------------------------------------------------

    def step(self) -> None:
        """
        Avança a simulação em tick_s segundos.

        loopback  → apenas avança t_s; medidor mantém valores fixos.
        openloop  → física ativa; sem perfis CSV; sem eventos.
        full      → física ativa; perfis CSV; eventos em tempo real.
        """
        self.t_s += self.tick_s

        # --- MODO LOOPBACK: sem física ---
        if self.mode == "loopback":
            return

        # --- MODOS OPENLOOP e FULL: física ativa ---
        t_int = int(self.t_s)

        # Eventos: somente no modo full
        if self.mode == "full":
            self._poll_events()
        ev = self._events_cache  # empty EventsCache no openloop

        # --- Perfis de irradiância e carga ---
        if self.mode == "full":
            u_global = sat(
                self.u_profile.value(t_int, self.u_default)
                if self.u_profile else self.u_default,
                0.0, 1.0,
            )
            load_p0_kw, load_q0_kvar = (
                self.load_profile.value(
                    t_int, self.load_p_kw_default, self.load_q_kvar_default
                )
                if self.load_profile
                else (self.load_p_kw_default, self.load_q_kvar_default)
            )
        else:
            # openloop: valores fixos do YAML
            u_global = sat(self.u_default, 0.0, 1.0)
            load_p0_kw = self.load_p_kw_default
            load_q0_kvar = self.load_q_kvar_default

        # --- Snapshot atômico dos setpoints (evita race condition) ---
        setpoints: Dict[int, Tuple[float, int]] = {
            sid: (inv.p_ref_pct, inv.pf_cmd_raw)
            for sid, inv in self.inverters.items()
        }

        # --- Dinâmica dos inversores ---
        for sid, inv in self.inverters.items():

            # Disponibilidade de energia
            if self.mode == "full" and sid in ev.force_u:
                inv.u = sat(ev.force_u[sid], 0.0, 1.0)
            else:
                inv.u = u_global

            # Perda de comunicação (rampa a zero em 5 s)
            if self.mode == "full" and sid in ev.drop_comms:
                inv.comms_drop = True
                inv.p_ref_pct = max(
                    0.0, inv.p_ref_pct - (self.tick_s / 5.0) * 100.0
                )
            else:
                inv.comms_drop = False

            # Congelamento de firmware
            if inv.frozen_s > 0.0:
                inv.frozen_s = max(0.0, inv.frozen_s - self.tick_s)
                # P e Q permanecem constantes — não atualizar
                continue

            sp_pct, sp_pf_raw = setpoints[sid]

            # Constantes de tempo discretizadas (Euler explícito)
            alpha = self.tick_s / inv.tau_p_s if inv.tau_p_s > 0 else 1.0
            beta = self.tick_s / inv.tau_q_s if inv.tau_q_s > 0 else 1.0

            # Potência ativa
            p_avail = inv.u * inv.p_nom_kw
            p_ref = (sp_pct / 100.0) * inv.p_nom_kw
            inv.p_kw = sat(
                inv.p_kw + alpha * (p_ref - inv.p_kw),
                0.0,
                p_avail,
            )

            # Potência reativa
            pf_mag, sign_q = self._decode_pf(sp_pf_raw)
            if pf_mag >= 0.9999 or sign_q == 0:
                q_ref = 0.0
            else:
                q_ref = float(sign_q) * inv.p_kw * tan(acos(pf_mag))

            q_lim = sqrt(max(0.0, inv.s_nom_kva ** 2 - inv.p_kw ** 2))
            inv.q_kvar = sat(
                inv.q_kvar + beta * (q_ref - inv.q_kvar),
                -q_lim,
                +q_lim,
            )

        # --- Agregação no PCC ---
        p_gen = sum(inv.p_kw for inv in self.inverters.values())
        q_gen = sum(inv.q_kvar for inv in self.inverters.values())

        # 1ª iteração: P/Q na carga com tensão nominal
        p_pcc_0 = load_p0_kw - p_gen
        q_pcc_0 = load_q0_kvar - q_gen
        v_pcc_0 = self.thevenin.v_pcc_ll(p_pcc_0, q_pcc_0)

        # Correção ZIP com a tensão calculada
        load_p_kw, load_q_kvar = self.zip_load.evaluate(
            load_p0_kw, load_q0_kvar, v_pcc_0, self.v_ll_v
        )

        # 2ª iteração: P/Q com carga corrigida (iteração única — suficiente
        # para redes com Scc >> S_carga)
        p_pcc = load_p_kw - p_gen
        q_pcc = load_q_kvar - q_gen
        s_pcc = sqrt(p_pcc ** 2 + q_pcc ** 2)

        self.v_pcc_ll_v = self.thevenin.v_pcc_ll(p_pcc, q_pcc)

        # --- Atualizar medidor ---
        if self.meter is None:
            return

        self.meter.p_pcc_kw = p_pcc
        self.meter.q_pcc_kvar = q_pcc
        self.meter.v_pcc_ll_v = self.v_pcc_ll_v

        # FP com sinal: positivo = indutivo (Q_pcc > 0), negativo = capacitivo
        pf_mag = abs(p_pcc) / s_pcc if s_pcc > 1e-9 else 1.0
        pf_signed = pf_mag if q_pcc >= 0.0 else -pf_mag
        self.meter.pfa = pf_signed
        self.meter.pfb = pf_signed
        self.meter.pfc = pf_signed

        # Tensão no secundário do TP (fase-neutro, V):
        #   V_BT_fn  = V_pcc_ll / sqrt(3)
        #   V_MT_fn  = V_BT_fn × (V_MT_nom / V_BT_nom)
        #   V_sec_fn = V_MT_fn / RTP
        v_pcc_fn = self.v_pcc_ll_v / sqrt(3.0) if self.v_pcc_ll_v > 0.0 else 0.0
        v_mt_fn = v_pcc_fn * (self.v_mt_ll_v / self.v_ll_v) if self.v_ll_v > 0.0 else 0.0
        v_mt_ll = v_mt_fn * sqrt(3.0)
        v_sec_fn = v_mt_fn / self.rtp if self.rtp > 0.0 else 0.0

        # Corrente no secundário do TC (A):
        #   I_MT_prim = S_PCC / (sqrt(3) × V_MT_LL)
        #   I_sec = I_MT_prim / RTC
        #   O PLC reconstrói: I_prim = reg_valor(A) × RTC
        i_mt_prim = (
            (s_pcc * 1000.0) / (sqrt(3.0) * v_mt_ll)
            if v_mt_ll > 0.0
            else 0.0
        )
        i_sec = i_mt_prim / self.rtc if self.rtc > 0.0 else 0.0

        self.meter.ua_v = v_sec_fn
        self.meter.ub_v = v_sec_fn
        self.meter.uc_v = v_sec_fn
        self.meter.ia_a = i_sec
        self.meter.ib_a = i_sec
        self.meter.ic_a = i_sec
