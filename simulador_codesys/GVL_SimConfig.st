// =============================================================================
// GVL_SimConfig — Parâmetros globais de configuração do simulador
// Equivalente a: config.py + config_etapa1/2/3.yaml
//
// COMO USAR:
//   Etapa 1 (loopback)  → SIM_MODE := 0
//   Etapa 2 (openloop)  → SIM_MODE := 1
//   Etapa 3 (full)      → SIM_MODE := 2
//
// Alterar SIM_MODE em tempo de execução reinicializa o comportamento na
// próxima chamada de FB_Simulator (bEdgeInit detecta a mudança).
// =============================================================================

VAR_GLOBAL CONSTANT

    // -------------------------------------------------------------------------
    // Modo de simulação
    //   0 = LOOPBACK  — comunicação Modbus, medidor fixo, física OFF
    //   1 = OPENLOOP  — física ON, carga/irradiância fixas, sem perfis/eventos
    //   2 = FULL      — física ON, perfis ativos, eventos ativos
    // -------------------------------------------------------------------------
    SIM_MODE_LOOPBACK   : INT := 0;
    SIM_MODE_OPENLOOP   : INT := 1;
    SIM_MODE_FULL       : INT := 2;

    // -------------------------------------------------------------------------
    // Temporização
    // -------------------------------------------------------------------------
    TICK_S              : REAL := 0.05;     // Período do ciclo de simulação (s)
                                             // Deve coincidir com o período da
                                             // task cíclica no Codesys Scheduler.
                                             // 50 ms é o mínimo seguro.

    // -------------------------------------------------------------------------
    // Rede elétrica
    // -------------------------------------------------------------------------
    V_LL_V              : REAL := 380.0;    // Tensão nominal linha-linha BT (V)
    V_MT_LL_V           : REAL := 13800.0;  // Tensão nominal linha-linha MT (V)

    // -------------------------------------------------------------------------
    // Equivalente de Thévenin da rede (referido ao BT)
    // -------------------------------------------------------------------------
    THEVENIN_VTH_LL_V   : REAL := 380.0;   // Tensão de Thévenin LL (V)
    THEVENIN_R_OHM      : REAL := 0.00283; // Resistência equivalente (Ω)
    THEVENIN_X_OHM      : REAL := 0.01416; // Reatância equivalente (Ω)

    // -------------------------------------------------------------------------
    // Relações de transformação dos instrumentos
    // -------------------------------------------------------------------------
    RTP                 : REAL := 120.0;    // Relação do TP  (ex: 13800/115 → 120)
    RTC                 : REAL := 200.0;    // Relação do TC  (ex: 200/5 → 200)

    // -------------------------------------------------------------------------
    // Modelo de carga ZIP (coeficientes ANEEL para alimentadores)
    //   P: 50% impedância constante + 50% potência constante
    //   Q: 100% potência constante
    // -------------------------------------------------------------------------
    ZIP_P_Z             : REAL := 0.50;    // Fração Z para P
    ZIP_P_I             : REAL := 0.00;    // Fração I para P
    ZIP_P_P             : REAL := 0.50;    // Fração P para P
    ZIP_Q_Z             : REAL := 0.00;    // Fração Z para Q
    ZIP_Q_I             : REAL := 0.00;    // Fração I para Q
    ZIP_Q_P             : REAL := 1.00;    // Fração P para Q

    // -------------------------------------------------------------------------
    // Carga padrão (usada em openloop e como fallback no full)
    // -------------------------------------------------------------------------
    LOAD_P_KW_DEFAULT   : REAL := 200.0;   // Potência ativa da carga (kW)
    LOAD_Q_KVAR_DEFAULT : REAL := 50.0;    // Potência reativa da carga (kVAr)

    // -------------------------------------------------------------------------
    // Irradiância padrão (normalizada 0.0..1.0)
    // -------------------------------------------------------------------------
    U_DEFAULT           : REAL := 1.0;     // 1.0 = irradiância plena (100%)

    // -------------------------------------------------------------------------
    // Valores fixos do medidor no modo LOOPBACK (grandezas no SECUNDÁRIO)
    //   V_sec_fn = V_MT_fn / RTP = (13800 / sqrt(3)) / 120 ≈ 66.4 V
    //   I_sec    = valor de teste no secundário do TC
    //   PF       = fator de potência de teste
    // -------------------------------------------------------------------------
    LOOPBACK_PF         : REAL := 0.92;    // Fator de potência fixo (loopback)
    LOOPBACK_V_MT_LN_V  : REAL := 66.4;   // Tensão sec. TP fase-neutro (V)
    LOOPBACK_I_MT_A     : REAL := 2.5;    // Corrente sec. TC (A)

    // -------------------------------------------------------------------------
    // Medidor Modbus (slave 100, COM1)
    // -------------------------------------------------------------------------
    METER_SLAVE_ID      : INT  := 100;
    METER_BASE_ADDR     : INT  := 153;     // 0x0099 decimal — endereço base FC03
    METER_QTY_U16       : INT  := 28;      // Quantidade de registradores U16

    // -------------------------------------------------------------------------
    // Número total de inversores
    //   COM1: slaves 101..109  (9 inversores)
    //   COM2: slaves 201..209  (9 inversores)
    // -------------------------------------------------------------------------
    N_INV               : INT  := 18;      // Total de inversores
    N_INV_COM1          : INT  := 9;       // Inversores na COM1 (índices 0..8)
    N_INV_COM2          : INT  := 9;       // Inversores na COM2 (índices 9..17)

    // -------------------------------------------------------------------------
    // Slave IDs dos inversores
    //   Índice 0..8  → COM1: slaves 101..109
    //   Índice 9..17 → COM2: slaves 201..209
    // -------------------------------------------------------------------------
    INV_SLAVE_ID        : ARRAY[0..17] OF INT := [
        101, 102, 103, 104, 105, 106, 107, 108, 109,   // COM1
        201, 202, 203, 204, 205, 206, 207, 208, 209    // COM2
    ];

    // -------------------------------------------------------------------------
    // Potências nominais dos inversores (kW)
    // -------------------------------------------------------------------------
    INV_P_NOM_KW        : ARRAY[0..17] OF REAL := [
        60.0, 60.0, 35.0, 15.0, 15.0, 15.0, 15.0, 15.0, 15.0,  // COM1
        15.0, 15.0, 15.0, 15.0, 15.0, 15.0, 35.0, 35.0, 50.0   // COM2
    ];

    // -------------------------------------------------------------------------
    // Potências aparentes nominais dos inversores (kVA)
    // -------------------------------------------------------------------------
    INV_S_NOM_KVA       : ARRAY[0..17] OF REAL := [
        60.0, 60.0, 35.0, 15.0, 15.0, 15.0, 15.0, 15.0, 15.0,  // COM1
        15.0, 15.0, 15.0, 15.0, 15.0, 15.0, 35.0, 35.0, 50.0   // COM2
    ];

    // -------------------------------------------------------------------------
    // Constantes de tempo dos inversores (s)
    //   tau_p: dinâmica de P (1ª ordem)
    //   tau_q: dinâmica de Q (1ª ordem)
    // -------------------------------------------------------------------------
    INV_TAU_P_S         : ARRAY[0..17] OF REAL := [
        1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0,
        1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0
    ];
    INV_TAU_Q_S         : ARRAY[0..17] OF REAL := [
        1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0,
        1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0, 1.0
    ];

    // -------------------------------------------------------------------------
    // Endereços Modbus dos inversores (Holding Registers, base 0)
    // -------------------------------------------------------------------------
    INV_HR_P_PCT        : INT := 256;      // HR 256 → setpoint %P  (escrito pelo master)
    INV_HR_PF_RAW       : INT := 257;      // HR 257 → FP raw       (escrito pelo master)

    // -------------------------------------------------------------------------
    // Eventos: intervalo de releitura (s)
    // -------------------------------------------------------------------------
    EVENTS_POLL_S       : REAL := 2.0;

END_VAR
