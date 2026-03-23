// =============================================================================
// FC_ProfileStep — Leitura de perfil piecewise-constant (step profile)
// Equivalente a profiles.py → StepProfile.value()
//
// O valor vigente é o último ponto com T_s[i] <= t_s.
// Se nenhum ponto for atingido, retorna default_val.
//
// Uso para perfil de irradiância (u_profile):
//   u := FC_ProfileStep(
//       t_s         := REAL_TO_DINT(g_T_s),
//       n           := U_PROFILE_N,
//       T_s         := U_Profile_T_s,
//       vals        := U_Profile_Val,
//       default_val := U_DEFAULT
//   );
//
// Uso para perfil de carga: chamar 2x (uma para P, outra para Q),
//   passando Load_Profile_P_kW ou Load_Profile_Q_kVAr como vals.
// =============================================================================

FUNCTION FC_ProfileStep : REAL
VAR_INPUT
    t_s         : DINT;                     // Tempo atual (s, inteiro)
    n           : INT;                      // Número de pontos ativos
    T_s         : ARRAY[0..63] OF DINT;    // Tempos dos pontos (s)
    vals        : ARRAY[0..63] OF REAL;    // Valores nos pontos
    default_val : REAL;                     // Valor se nenhum ponto atingido
END_VAR
VAR
    i       : INT;
    result  : REAL;
END_VAR

result := default_val;

FOR i := 0 TO n - 1 DO
    IF t_s >= T_s[i] THEN
        result := vals[i];
    ELSE
        EXIT;   // Lista ordenada: pode parar no primeiro ponto futuro
    END_IF
END_FOR

FC_ProfileStep := result;

END_FUNCTION
