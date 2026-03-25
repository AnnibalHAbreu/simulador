// =============================================================================
// GVL_Events — Injeção de falhas e eventos em tempo real
// Equivalente a configs/events.json (Etapa 3 — modo FULL)
//
// USADO APENAS QUANDO g_SimMode = SIM_MODE_FULL (2).
// Nos modos loopback e openloop estas variáveis são ignoradas.
//
// COMO USAR (via HMI Codesys ou Watch/Write no IDE):
//
//   T1 — Perda de inversor grande (slave 101 = índice 0):
//     g_Ev_DropComms[0]  := TRUE;
//     (restaurar: g_Ev_DropComms[0] := FALSE)
//
//   T2 — Nuvem passageira em toda a COM1 (índices 0..8):
//     g_Ev_Force_U[0] := 0.3;  g_Ev_Force_U[1] := 0.3;
//     g_Ev_Force_U[2] := 0.3;  g_Ev_Force_U[3] := 0.3;
//     g_Ev_Force_U[4] := 0.3;  g_Ev_Force_U[5] := 0.3;
//     g_Ev_Force_U[6] := 0.3;  g_Ev_Force_U[7] := 0.3;
//     g_Ev_Force_U[8] := 0.3;
//     (restaurar: g_Ev_Force_U[0..8] := −1.0)
//
//   T3 — Travamento + perda de comunicação combinados:
//     g_Ev_DropComms[15]  := TRUE;          // slave 207 = índice 15
//     g_Ev_Freeze_s[2]    := 20.0;          // slave 103 = índice 2
//     g_Ev_Freeze_s[16]   := 15.0;          // slave 208 = índice 16
//     (restaurar: FALSE e 0.0)
//
//   T4 — Retorno à operação normal:
//     Zerar todos os g_Ev_* (ver abaixo)
//
// TABELA DE ÍNDICES × SLAVE IDs:
//   Índice | Slave ID | Porta | P_nom
//   -------+----------+-------+------
//     0    |   101    | COM1  | 60 kW
//     1    |   102    | COM1  | 60 kW
//     2    |   103    | COM1  | 35 kW
//     3    |   104    | COM1  | 15 kW
//     4    |   105    | COM1  | 15 kW
//     5    |   106    | COM1  | 15 kW
//     6    |   107    | COM1  | 15 kW
//     7    |   108    | COM1  | 15 kW
//     8    |   109    | COM1  | 15 kW
//     9    |   201    | COM2  | 15 kW
//    10    |   202    | COM2  | 15 kW
//    11    |   203    | COM2  | 15 kW
//    12    |   204    | COM2  | 15 kW
//    13    |   205    | COM2  | 15 kW
//    14    |   206    | COM2  | 15 kW
//    15    |   207    | COM2  | 35 kW
//    16    |   208    | COM2  | 35 kW
//    17    |   209    | COM2  | 50 kW
//
// CAMPOS (todos em GVL_SimState):
//
//   g_Ev_DropComms[i] : BOOL
//     TRUE  = inversor i perde comunicação (rampa P→0 em 5 s)
//     FALSE = normal
//
//   g_Ev_Freeze_s[i]  : REAL
//     > 0.0 = segundos de congelamento de firmware restantes
//             (P e Q ficam constantes, ignora setpoints)
//     0.0   = normal
//     Nota: acumulativo — FB_Simulator usa MAX(restante, novo valor)
//
//   g_Ev_Force_U[i]   : REAL
//     0.0..1.0 = sobrescreve irradiância daquele inversor (sombreamento)
//     −1.0     = usa u_global do perfil (padrão)
//
// =============================================================================
// Este arquivo é apenas documentação. As variáveis estão declaradas em
// GVL_SimState.st. Nenhuma declaração adicional necessária aqui.
// =============================================================================
