// =============================================================================
// FB_ZipLoad — Modelo de carga ZIP (coeficientes ANEEL)
// Equivalente a ZipLoadModel em simulation.py
//
// Coeficientes ANEEL para alimentadores de distribuição:
//   P: 50% impedância constante (Z) + 50% potência constante (P)
//   Q: 100% potência constante (P)
//
// Equações:
//   P_load = P0 × (aZ·Vr² + aI·Vr + aP)
//   Q_load = Q0 × (bZ·Vr² + bI·Vr + bP)
//   onde Vr = V_atual / V_nominal
// =============================================================================

FUNCTION_BLOCK FB_ZipLoad
VAR_INPUT
    p0_kw       : REAL;     // Potência ativa nominal da carga (kW)
    q0_kvar     : REAL;     // Potência reativa nominal da carga (kVAr)
    v_ll_v      : REAL;     // Tensão atual linha-linha (V)
    v0_ll_v     : REAL;     // Tensão nominal de referência (V)
    // Coeficientes ZIP para P
    a_Z         : REAL;
    a_I         : REAL;
    a_P         : REAL;
    // Coeficientes ZIP para Q
    b_Z         : REAL;
    b_I         : REAL;
    b_P         : REAL;
END_VAR
VAR_OUTPUT
    p_kw        : REAL;     // Potência ativa ajustada (kW)
    q_kvar      : REAL;     // Potência reativa ajustada (kVAr)
END_VAR
VAR
    vr          : REAL;
    vr2         : REAL;
END_VAR

IF v0_ll_v < 1.0 THEN
    // Proteção divisão por zero — retorna valores nominais
    p_kw  := p0_kw;
    q_kvar := q0_kvar;
    RETURN;
END_IF

vr  := v_ll_v / v0_ll_v;
vr2 := vr * vr;

p_kw   := p0_kw   * (a_Z * vr2 + a_I * vr + a_P);
q_kvar := q0_kvar * (b_Z * vr2 + b_I * vr + b_P);

END_FUNCTION_BLOCK
