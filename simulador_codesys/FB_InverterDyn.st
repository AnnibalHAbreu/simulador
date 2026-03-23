// =============================================================================
// FB_InverterDyn — Dinâmica de 1ª ordem de um inversor fotovoltaico
// Equivalente ao loop de inversores em PlantSimulation.step()
//
// Modela um inversor como dois filtros de 1ª ordem independentes (P e Q),
// com saturação na potência disponível (u × P_nom) e no limite de S_nom.
//
// Discretização: Euler explícito
//   P[k+1] = P[k] + (Ts/tau_p) × (P_ref − P[k])
//   Q[k+1] = Q[k] + (Ts/tau_q) × (Q_ref − Q[k])
//
// Um bloco FB_InverterDyn é instanciado para cada inversor (0..17).
// O FB_Simulator chama todos a cada ciclo.
// =============================================================================

FUNCTION_BLOCK FB_InverterDyn
VAR_INPUT
    // Parâmetros fixos (configurados uma vez)
    p_nom_kw    : REAL;     // Potência ativa nominal (kW)
    s_nom_kva   : REAL;     // Potência aparente nominal (kVA)
    tau_p_s     : REAL;     // Constante de tempo de P (s)
    tau_q_s     : REAL;     // Constante de tempo de Q (s)
    tick_s      : REAL;     // Período de amostragem (s) = TICK_S

    // Setpoints (escritos pelo driver Modbus a cada FC16)
    p_ref_pct   : REAL;     // Setpoint %P  (0..100)
    pf_cmd_raw  : INT;      // FP raw HR257 (1..100)

    // Disponibilidade de energia (irradiância normalizada 0..1)
    u           : REAL;

    // Eventos
    comms_drop  : BOOL;     // TRUE = perda de comunicação (rampa P→0)
    frozen_s    : REAL;     // Segundos restantes de congelamento
END_VAR
VAR_OUTPUT
    p_kw        : REAL;     // Potência ativa atual (kW)
    q_kvar      : REAL;     // Potência reativa atual (kVAr)
    frozen_s_out: REAL;     // Tempo de congelamento restante após step
    p_ref_pct_out: REAL;    // p_ref_pct após aplicação de drop_comms
END_VAR
VAR
    alpha       : REAL;     // Ts / tau_p
    beta        : REAL;     // Ts / tau_q
    p_avail     : REAL;     // Potência disponível (u × p_nom)
    p_ref_kw    : REAL;     // Referência de P em kW
    pf_mag      : REAL;
    sign_q      : INT;
    q_ref       : REAL;
    q_lim       : REAL;
    q_lim_sq    : REAL;
    p_ref_pct_w : REAL;     // cópia de trabalho de p_ref_pct
    SQRT3       : REAL := 1.7320508;
    COS_INV_ARG : REAL;
    // variáveis internas de estado (persistem entre chamadas)
    _p_kw       : REAL;
    _q_kvar     : REAL;
END_VAR

// -----------------------------------------------------------------------
// Preservar saídas com estado persistente
// -----------------------------------------------------------------------
p_kw  := _p_kw;
q_kvar := _q_kvar;

// -----------------------------------------------------------------------
// Congelamento de firmware: P e Q ficam constantes, decrementar timer
// -----------------------------------------------------------------------
IF frozen_s > 0.0 THEN
    frozen_s_out  := frozen_s - tick_s;
    IF frozen_s_out < 0.0 THEN frozen_s_out := 0.0; END_IF
    p_ref_pct_out := p_ref_pct;
    // P e Q NÃO mudam — retornar valores atuais
    RETURN;
END_IF
frozen_s_out := 0.0;

// -----------------------------------------------------------------------
// Perda de comunicação: rampa P a zero em 5 s
// -----------------------------------------------------------------------
p_ref_pct_w := p_ref_pct;
IF comms_drop THEN
    p_ref_pct_w := p_ref_pct_w - (tick_s / 5.0) * 100.0;
    IF p_ref_pct_w < 0.0 THEN p_ref_pct_w := 0.0; END_IF
END_IF
p_ref_pct_out := p_ref_pct_w;

// -----------------------------------------------------------------------
// Constantes de tempo discretizadas (Euler explícito)
// -----------------------------------------------------------------------
IF tau_p_s > 0.0 THEN
    alpha := tick_s / tau_p_s;
ELSE
    alpha := 1.0;
END_IF

IF tau_q_s > 0.0 THEN
    beta := tick_s / tau_q_s;
ELSE
    beta := 1.0;
END_IF

// Saturar alpha/beta em 1.0 para evitar instabilidade numérica
IF alpha > 1.0 THEN alpha := 1.0; END_IF
IF beta  > 1.0 THEN beta  := 1.0; END_IF

// -----------------------------------------------------------------------
// Potência ativa
// -----------------------------------------------------------------------
p_avail  := u * p_nom_kw;
IF p_avail < 0.0 THEN p_avail := 0.0; END_IF

p_ref_kw := (p_ref_pct_w / 100.0) * p_nom_kw;

_p_kw := _p_kw + alpha * (p_ref_kw - _p_kw);

// Saturar em [0, p_avail]
IF _p_kw < 0.0     THEN _p_kw := 0.0;     END_IF
IF _p_kw > p_avail THEN _p_kw := p_avail; END_IF

// -----------------------------------------------------------------------
// Potência reativa — decodifica FP raw e calcula Q_ref
// -----------------------------------------------------------------------
FC_DecodePF(raw := pf_cmd_raw, pf_mag => pf_mag, sign_q => sign_q);

IF pf_mag >= 0.9999 OR sign_q = 0 THEN
    q_ref := 0.0;
ELSE
    // Q_ref = sign_q × P × tan(acos(pf_mag))
    // Usando identidade: tan(acos(x)) = sqrt(1-x²)/x
    COS_INV_ARG := 1.0 - pf_mag * pf_mag;
    IF COS_INV_ARG < 0.0 THEN COS_INV_ARG := 0.0; END_IF
    q_ref := REAL(sign_q) * _p_kw * SQRT(COS_INV_ARG) / pf_mag;
END_IF

// Limite de Q pela capacidade aparente: |Q| ≤ sqrt(S² − P²)
q_lim_sq := s_nom_kva * s_nom_kva - _p_kw * _p_kw;
IF q_lim_sq < 0.0 THEN q_lim_sq := 0.0; END_IF
q_lim := SQRT(q_lim_sq);

_q_kvar := _q_kvar + beta * (q_ref - _q_kvar);

// Saturar em [−q_lim, +q_lim]
IF _q_kvar < -q_lim THEN _q_kvar := -q_lim; END_IF
IF _q_kvar >  q_lim THEN _q_kvar :=  q_lim; END_IF

// -----------------------------------------------------------------------
// Atualizar saídas com estado persistente
// -----------------------------------------------------------------------
p_kw   := _p_kw;
q_kvar := _q_kvar;

END_FUNCTION_BLOCK
