// =============================================================================
// FC_EncodeI — Codifica corrente secundária TC em UINT (U16)
// Equivalente a modbus_server.py → encode_i_u16()
//
// Resolução: 1/256 A por LSB
//   reg = ROUND(I_sec_A × 256)
//   Master reconstrói: I_sec = reg / 256
//   I_prim = I_sec × RTC
// =============================================================================

FUNCTION FC_EncodeI : UINT
VAR_INPUT
    i_a : REAL;     // Corrente secundária TC (A), ≥ 0
END_VAR
VAR
    raw : DINT;
END_VAR

IF i_a < 0.0 THEN i_a := 0.0; END_IF
raw := REAL_TO_DINT(i_a * 256.0 + 0.5);
IF raw > 65535 THEN raw := 65535; END_IF
FC_EncodeI := DINT_TO_UINT(raw);

END_FUNCTION


// =============================================================================
// FC_EncodeV — Codifica tensão secundária TP em UINT (U16)
// Equivalente a modbus_server.py → encode_v_u16()
//
// Resolução: 1/128 V por LSB
//   reg = ROUND(V_sec_V × 128)
//   Master reconstrói: V_sec = reg / 128
//   V_prim = V_sec × RTP
// =============================================================================

FUNCTION FC_EncodeV : UINT
VAR_INPUT
    v_v : REAL;     // Tensão secundária TP fase-neutro (V), ≥ 0
END_VAR
VAR
    raw : DINT;
END_VAR

IF v_v < 0.0 THEN v_v := 0.0; END_IF
raw := REAL_TO_DINT(v_v * 128.0 + 0.5);
IF raw > 65535 THEN raw := 65535; END_IF
FC_EncodeV := DINT_TO_UINT(raw);

END_FUNCTION
