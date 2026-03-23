// =============================================================================
// FB_Thevenin — Equivalente de Thévenin (monofásico, referido ao BT)
// Equivalente a TheveninModel em simulation.py
//
// Aproximação linearizada de 1ª ordem:
//   V_pcc_fase ≈ Vth_fase − (R·P_fase + X·Q_fase) / Vth_fase
//
// Convenção P_pcc / Q_pcc:
//   > 0  →  importação da rede  →  tensão cai
//   < 0  →  exportação p/ rede  →  tensão sobe
//
// Parâmetros configurados via GVL_SimConfig (THEVENIN_*).
// =============================================================================

FUNCTION_BLOCK FB_Thevenin
VAR_INPUT
    p_pcc_kw    : REAL;     // Potência ativa no PCC (kW)  + = importa
    q_pcc_kvar  : REAL;     // Potência reativa no PCC (kVAr)
    vth_ll_v    : REAL;     // Tensão de Thévenin LL (V)
    r_ohm       : REAL;     // Resistência equivalente (Ω)
    x_ohm       : REAL;     // Reatância equivalente (Ω)
END_VAR
VAR_OUTPUT
    v_pcc_ll_v  : REAL;     // Tensão linha-linha no PCC (V)
END_VAR
VAR
    vth_fase    : REAL;
    p_fase_w    : REAL;
    q_fase_var  : REAL;
    delta_v     : REAL;
    v_pcc_fase  : REAL;
    SQRT3       : REAL := 1.7320508;
END_VAR

vth_fase := vth_ll_v / SQRT3;

IF vth_fase < 1.0 THEN
    v_pcc_ll_v := 0.0;
    RETURN;
END_IF

p_fase_w    := p_pcc_kw   * 1000.0 / 3.0;
q_fase_var  := q_pcc_kvar * 1000.0 / 3.0;

delta_v     := (r_ohm * p_fase_w + x_ohm * q_fase_var) / vth_fase;
v_pcc_fase  := vth_fase - delta_v;

IF v_pcc_fase < 0.0 THEN v_pcc_fase := 0.0; END_IF

v_pcc_ll_v := v_pcc_fase * SQRT3;

END_FUNCTION_BLOCK
