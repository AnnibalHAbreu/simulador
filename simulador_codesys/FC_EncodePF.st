// =============================================================================
// FC_EncodePF — Codifica fator de potência com sinal em UINT (U16)
// Equivalente a modbus_server.py → encode_pf_u16()
//
// Convenção (igual ao Python):
//   pf ∈ [ 0.0,  1.0] → reg = ROUND(pf × 16384)         (0..16384)
//   pf ∈ [-1.0,  0.0) → reg = 65535 − ROUND(|pf| × 16384)
//
// O master (WAGO SCRPI) decodifica:
//   se reg ≤ 16384  → pf =  reg / 16384
//   se reg ≥ 49151  → pf = -(65535 - reg) / 16384
// =============================================================================

FUNCTION FC_EncodePF : UINT
VAR_INPUT
    pf  : REAL;     // Fator de potência com sinal (−1.0 .. +1.0)
END_VAR
VAR
    pf_sat  : REAL;
    raw     : DINT;
END_VAR

// Saturar entrada
pf_sat := pf;
IF pf_sat >  1.0 THEN pf_sat :=  1.0; END_IF
IF pf_sat < -1.0 THEN pf_sat := -1.0; END_IF

IF pf_sat >= 0.0 THEN
    // Positivo: indutivo (Q > 0)
    raw := REAL_TO_DINT(pf_sat * 16384.0 + 0.5);   // arredondamento
    IF raw > 16384 THEN raw := 16384; END_IF
    FC_EncodePF := DINT_TO_UINT(raw);
ELSE
    // Negativo: capacitivo (Q < 0)
    raw := REAL_TO_DINT(ABS(pf_sat) * 16384.0 + 0.5);
    IF raw > 16384 THEN raw := 16384; END_IF
    FC_EncodePF := DINT_TO_UINT(65535 - raw);
END_IF

END_FUNCTION
