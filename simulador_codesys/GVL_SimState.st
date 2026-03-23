// =============================================================================
// GVL_SimState — Estado em tempo de execução do simulador
// Equivalente às dataclasses InverterState, MeterState e PlantSimulation
// em simulation.py.
//
// Estas variáveis são LIDAS/ESCRITAS pelo FB_Simulator a cada ciclo.
// O driver Modbus Slave do Codesys mapeia diretamente os registradores
// do medidor (MW_Meter) e dos inversores (MW_Inv_*) em memória.
// =============================================================================

VAR_GLOBAL

    // =========================================================================
    // CONTROLE GERAL
    // =========================================================================

    // Modo ativo (alterável em runtime via HMI ou variável)
    //   0 = LOOPBACK | 1 = OPENLOOP | 2 = FULL
    g_SimMode           : INT := 0;

    // Tempo acumulado de simulação (s) — avança a cada ciclo
    g_T_s               : REAL := 0.0;

    // Flag de reinicialização: setar TRUE para reiniciar estados
    g_Reset             : BOOL := FALSE;

    // =========================================================================
    // ESTADO DOS INVERSORES
    // =========================================================================

    // --- Setpoints recebidos do master via FC16 (escritos pelo driver Modbus) ---
    // HR 256: setpoint %P  (0..100)
    g_Inv_P_Ref_Pct     : ARRAY[0..17] OF REAL := [18(0.0)];

    // HR 257: FP raw (1..100)
    g_Inv_PF_Cmd_Raw    : ARRAY[0..17] OF INT  := [18(100)];

    // --- Estados internos da dinâmica de 1ª ordem ---
    g_Inv_P_kW          : ARRAY[0..17] OF REAL := [18(0.0)];
    g_Inv_Q_kVAr        : ARRAY[0..17] OF REAL := [18(0.0)];

    // --- Disponibilidade de energia (irradiância normalizada 0..1) ---
    g_Inv_U             : ARRAY[0..17] OF REAL := [18(1.0)];

    // --- Flags de eventos ---
    g_Inv_CommsDrop     : ARRAY[0..17] OF BOOL := [18(FALSE)];
    g_Inv_Frozen_s      : ARRAY[0..17] OF REAL := [18(0.0)];

    // =========================================================================
    // ESTADO DO MEDIDOR (grandezas no SECUNDÁRIO dos instrumentos)
    // =========================================================================
    // O driver Modbus Slave mapeia MW_Meter[] nos registradores FC03
    // a partir do endereço base 0x0099 (153 decimal).
    // Cada elemento é um UINT (U16) codificado conforme especificação.

    // Registradores raw U16 para o driver Modbus Slave
    // Índice 0..27 → offsets relativos a 0x0099
    //   [0]  = PF fase A     [1]  = PF fase B     [2]  = PF fase C
    //   [3..6] = reservado = 0
    //   [7]  = Ia sec        [8]  = Ib sec         [9]  = Ic sec
    //   [10] = reservado = 0
    //   [11] = Ua sec fn     [12] = Ub sec fn      [13] = Uc sec fn
    //   [14..27] = reservado = 0
    MW_Meter            : ARRAY[0..27] OF UINT := [28(0)];

    // Grandezas físicas internas do medidor (REAL, para debug/HMI)
    g_Meter_PFa         : REAL := 1.0;
    g_Meter_PFb         : REAL := 1.0;
    g_Meter_PFc         : REAL := 1.0;
    g_Meter_Ia_A        : REAL := 0.0;  // corrente sec. TC (A)
    g_Meter_Ib_A        : REAL := 0.0;
    g_Meter_Ic_A        : REAL := 0.0;
    g_Meter_Ua_V        : REAL := 0.0;  // tensão sec. TP fase-neutro (V)
    g_Meter_Ub_V        : REAL := 0.0;
    g_Meter_Uc_V        : REAL := 0.0;
    g_Meter_P_PCC_kW    : REAL := 0.0;  // potência ativa no PCC (kW)
    g_Meter_Q_PCC_kVAr  : REAL := 0.0;  // potência reativa no PCC (kVAr)
    g_Meter_V_PCC_LL_V  : REAL := 380.0; // tensão linha-linha no PCC (V)

    // =========================================================================
    // EVENTOS EM TEMPO REAL (equivalente a events.json)
    // Alteráveis via HMI Codesys ou CoDeSys VisualizationControl
    // =========================================================================

    // drop_comms: TRUE = inversor perde comunicação (rampa P→0 em 5 s)
    g_Ev_DropComms      : ARRAY[0..17] OF BOOL := [18(FALSE)];

    // freeze_s: segundos restantes de congelamento de firmware (0 = normal)
    g_Ev_Freeze_s       : ARRAY[0..17] OF REAL := [18(0.0)];

    // force_u: sobrescreve irradiância do inversor (−1 = não forçar)
    //   −1.0 = usa u_global do perfil
    //   0.0..1.0 = força esta irradiância (sombreamento)
    g_Ev_Force_U        : ARRAY[0..17] OF REAL := [18(-1.0)];

    // =========================================================================
    // PERFIS (equivalente a u_profile.csv e load_profile.csv)
    // Piecewise-constant: valor vira ativo quando g_T_s >= time_s[i]
    // =========================================================================

    // --- Perfil de irradiância (u_profile.csv) ---
    // Dimensione conforme o número de pontos do seu perfil (máx. 64 pontos)
    U_PROFILE_N         : INT := 5;        // Número de pontos ativos
    U_Profile_T_s       : ARRAY[0..63] OF DINT := [
          0,   300,   600,   900,  1200,
         59(0)
    ];
    U_Profile_Val       : ARRAY[0..63] OF REAL := [
        1.0,   0.7,   0.4,   0.8,   1.0,
        59(0.0)
    ];

    // --- Perfil de carga (load_profile.csv) ---
    LOAD_PROFILE_N      : INT := 5;
    Load_Profile_T_s    : ARRAY[0..63] OF DINT := [
          0,   300,   600,   900,  1200,
         59(0)
    ];
    Load_Profile_P_kW   : ARRAY[0..63] OF REAL := [
        200.0, 250.0, 180.0, 220.0, 200.0,
        59(0.0)
    ];
    Load_Profile_Q_kVAr : ARRAY[0..63] OF REAL := [
         50.0,  60.0,  45.0,  55.0,  50.0,
         59(0.0)
    ];

    // =========================================================================
    // DIAGNÓSTICO
    // =========================================================================
    g_P_Gen_Total_kW    : REAL := 0.0;   // Soma P de todos inversores
    g_Q_Gen_Total_kVAr  : REAL := 0.0;   // Soma Q de todos inversores
    g_CycleOverrun      : BOOL := FALSE; // TRUE se task demorou mais que TICK_S

END_VAR
