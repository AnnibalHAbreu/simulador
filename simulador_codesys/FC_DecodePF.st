// =============================================================================
// FC_DecodePF — Decodifica FP raw (U16) enviado pelo master ao inversor
// Equivalente a PlantSimulation._decode_pf() em simulation.py
//
// Protocolo:
//   1..20   → lagging (indutivo):  PF = 1.00 − raw×0.01    (0.80..0.99)
//             sign_q = −1  →  Q < 0  (consome reativo)
//   80..99  → leading (capacitivo): PF = raw/100            (0.80..0.99)
//             sign_q = +1  →  Q > 0  (injeta reativo)
//   100     → unitário: PF = 1.0, Q = 0
//   21..79  → inválido: tratado como unitário
//
// Saídas:
//   pf_mag  : REAL  — magnitude do FP (0.80..1.00)
//   sign_q  : INT   — +1 leading | −1 lagging | 0 unitário
// =============================================================================

FUNCTION FC_DecodePF : BOOL    // retorna TRUE sempre (função não falha)
VAR_INPUT
    raw     : INT;              // FP raw recebido via HR 257
END_VAR
VAR_OUTPUT
    pf_mag  : REAL;             // Magnitude do FP
    sign_q  : INT;              // Sinal de Q: +1 | 0 | -1
END_VAR

IF raw >= 1 AND raw <= 20 THEN
    // Lagging (indutivo): consome reativo, Q < 0
    pf_mag := 1.0 - REAL(raw) * 0.01;
    IF pf_mag < 0.80 THEN pf_mag := 0.80; END_IF
    IF pf_mag > 0.99 THEN pf_mag := 0.99; END_IF
    sign_q := -1;

ELSIF raw >= 80 AND raw <= 99 THEN
    // Leading (capacitivo): injeta reativo, Q > 0
    pf_mag := REAL(raw) / 100.0;
    IF pf_mag < 0.80 THEN pf_mag := 0.80; END_IF
    IF pf_mag > 0.99 THEN pf_mag := 0.99; END_IF
    sign_q := 1;

ELSIF raw = 100 THEN
    // Unitário
    pf_mag := 1.0;
    sign_q := 0;

ELSE
    // Fora de faixa (21..79 ou negativo) → trata como unitário
    pf_mag := 1.0;
    sign_q := 0;
END_IF

FC_DecodePF := TRUE;

END_FUNCTION
