// =============================================================================
// FB_Simulator — Bloco principal do simulador de usina FV
// Equivalente a PlantSimulation (simulation.py) + main.py
//
// Chamado ciclicamente pela task de simulação (período = TICK_S).
// Lê setpoints de g_Inv_P_Ref_Pct[] e g_Inv_PF_Cmd_Raw[] (escritos pelo
// driver Modbus Slave quando o master envia FC16).
// Escreve MW_Meter[] (lido pelo driver Modbus Slave para responder FC03).
//
// MODOS (g_SimMode):
//   SIM_MODE_LOOPBACK (0) — medidor fixo, sem física
//   SIM_MODE_OPENLOOP (1) — física ativa, carga/u fixas
//   SIM_MODE_FULL     (2) — física + perfis + eventos
//
// RESET:
//   Setar g_Reset := TRUE para zerar todos os estados dinâmicos.
//   O FB limpa g_Reset automaticamente após reset.
// =============================================================================

FUNCTION_BLOCK FB_Simulator
VAR_INPUT
    // Sem entradas externas — tudo via GVL_SimState e GVL_SimConfig
END_VAR
VAR_OUTPUT
    // Sem saídas diretas — escreve nas GVLs
END_VAR
VAR
    // -----------------------------------------------------------------------
    // Instâncias dos modelos físicos
    // -----------------------------------------------------------------------
    fbThevenin  : FB_Thevenin;
    fbZipLoad   : FB_ZipLoad;
    fbInv       : ARRAY[0..17] OF FB_InverterDyn;

    // -----------------------------------------------------------------------
    // Variáveis de trabalho internas
    // -----------------------------------------------------------------------
    i               : INT;
    t_int           : DINT;

    // Carga
    load_p0_kw      : REAL;
    load_q0_kvar    : REAL;
    load_p_kw       : REAL;
    load_q_kvar     : REAL;

    // Irradiância global
    u_global        : REAL;
    u_inv           : REAL;

    // PCC 1ª iteração
    p_gen           : REAL;
    q_gen           : REAL;
    p_pcc_0         : REAL;
    q_pcc_0         : REAL;
    v_pcc_0         : REAL;

    // PCC 2ª iteração
    p_pcc           : REAL;
    q_pcc           : REAL;
    s_pcc           : REAL;
    s_pcc_sq        : REAL;
    v_pcc_ll        : REAL;

    // Medidor — grandezas calculadas
    pf_mag          : REAL;
    pf_signed       : REAL;
    v_pcc_fn        : REAL;
    v_mt_fn         : REAL;
    v_mt_ll         : REAL;
    v_sec_fn        : REAL;
    i_mt_prim       : REAL;
    i_sec           : REAL;

    // Controle de modo anterior (detecta mudança de modo)
    _prev_mode      : INT := -1;

    // Constantes matemáticas
    SQRT3           : REAL := 1.7320508;
    SQRT3_INV       : REAL := 0.5773503;    // 1/sqrt(3)

    // Evento drop_comms: cópia de p_ref_pct após aplicação da rampa
    _p_ref_pct_eff  : ARRAY[0..17] OF REAL;
END_VAR

// ===========================================================================
// RESET
// ===========================================================================
IF g_Reset THEN
    g_T_s := 0.0;
    FOR i := 0 TO 17 DO
        g_Inv_P_kW[i]      := 0.0;
        g_Inv_Q_kVAr[i]    := 0.0;
        g_Inv_U[i]         := 1.0;
        g_Inv_CommsDrop[i] := FALSE;
        g_Inv_Frozen_s[i]  := 0.0;
        // Zerar estados internos dos FB de inversores via re-init
        // (no Codesys, reinicializar instâncias de FB não é direto;
        //  o workaround é forçar p_kw=0 via setpoint zero e esperar decaimento,
        //  ou usar o campo _p_kw diretamente se a versão do Codesys permitir.)
        g_Inv_P_Ref_Pct[i]  := 0.0;
        g_Inv_PF_Cmd_Raw[i] := 100;
    END_FOR
    g_Meter_P_PCC_kW    := 0.0;
    g_Meter_Q_PCC_kVAr  := 0.0;
    g_Meter_V_PCC_LL_V  := V_LL_V;
    _prev_mode          := -1;
    g_Reset             := FALSE;
    RETURN;
END_IF

// ===========================================================================
// DETECÇÃO DE MUDANÇA DE MODO
// ===========================================================================
IF g_SimMode <> _prev_mode THEN
    _prev_mode := g_SimMode;
    // Ao entrar no modo LOOPBACK: inicializa medidor com valores fixos
    IF g_SimMode = SIM_MODE_LOOPBACK THEN
        g_Meter_PFa := LOOPBACK_PF;
        g_Meter_PFb := LOOPBACK_PF;
        g_Meter_PFc := LOOPBACK_PF;
        g_Meter_Ia_A := LOOPBACK_I_MT_A;
        g_Meter_Ib_A := LOOPBACK_I_MT_A;
        g_Meter_Ic_A := LOOPBACK_I_MT_A;
        g_Meter_Ua_V := LOOPBACK_V_MT_LN_V;
        g_Meter_Ub_V := LOOPBACK_V_MT_LN_V;
        g_Meter_Uc_V := LOOPBACK_V_MT_LN_V;
        // Codifica e preenche MW_Meter
        MW_Meter[0]  := FC_EncodePF(LOOPBACK_PF);
        MW_Meter[1]  := FC_EncodePF(LOOPBACK_PF);
        MW_Meter[2]  := FC_EncodePF(LOOPBACK_PF);
        MW_Meter[3]  := 0;  MW_Meter[4]  := 0;
        MW_Meter[5]  := 0;  MW_Meter[6]  := 0;
        MW_Meter[7]  := FC_EncodeI(LOOPBACK_I_MT_A);
        MW_Meter[8]  := FC_EncodeI(LOOPBACK_I_MT_A);
        MW_Meter[9]  := FC_EncodeI(LOOPBACK_I_MT_A);
        MW_Meter[10] := 0;
        MW_Meter[11] := FC_EncodeV(LOOPBACK_V_MT_LN_V);
        MW_Meter[12] := FC_EncodeV(LOOPBACK_V_MT_LN_V);
        MW_Meter[13] := FC_EncodeV(LOOPBACK_V_MT_LN_V);
        MW_Meter[14] := 0;  MW_Meter[15] := 0;  MW_Meter[16] := 0;
        MW_Meter[17] := 0;  MW_Meter[18] := 0;  MW_Meter[19] := 0;
        MW_Meter[20] := 0;  MW_Meter[21] := 0;  MW_Meter[22] := 0;
        MW_Meter[23] := 0;  MW_Meter[24] := 0;  MW_Meter[25] := 0;
        MW_Meter[26] := 0;  MW_Meter[27] := 0;
    END_IF
END_IF

// ===========================================================================
// AVANÇA TEMPO
// ===========================================================================
g_T_s := g_T_s + TICK_S;
t_int := REAL_TO_DINT(g_T_s);

// ===========================================================================
// MODO LOOPBACK — sem física, apenas loga setpoints recebidos
// ===========================================================================
IF g_SimMode = SIM_MODE_LOOPBACK THEN
    // MW_Meter já foi preenchido na detecção de mudança de modo.
    // Inversores apenas registram o que o master enviou (sem simulação).
    // (O log seria feito via variável de diagnóstico em HMI)
    RETURN;
END_IF

// ===========================================================================
// MODOS OPENLOOP e FULL — física ativa
// ===========================================================================

// ---------------------------------------------------------------------------
// 1. Perfis de irradiância e carga
// ---------------------------------------------------------------------------
IF g_SimMode = SIM_MODE_FULL THEN
    u_global := FC_ProfileStep(
        t_s         := t_int,
        n           := U_PROFILE_N,
        T_s         := U_Profile_T_s,
        vals        := U_Profile_Val,
        default_val := U_DEFAULT
    );
    IF u_global < 0.0 THEN u_global := 0.0; END_IF
    IF u_global > 1.0 THEN u_global := 1.0; END_IF

    load_p0_kw := FC_ProfileStep(
        t_s         := t_int,
        n           := LOAD_PROFILE_N,
        T_s         := Load_Profile_T_s,
        vals        := Load_Profile_P_kW,
        default_val := LOAD_P_KW_DEFAULT
    );
    load_q0_kvar := FC_ProfileStep(
        t_s         := t_int,
        n           := LOAD_PROFILE_N,
        T_s         := Load_Profile_T_s,
        vals        := Load_Profile_Q_kVAr,
        default_val := LOAD_Q_KVAR_DEFAULT
    );
ELSE
    // OPENLOOP: valores fixos do YAML / GVL_SimConfig
    u_global     := U_DEFAULT;
    IF u_global < 0.0 THEN u_global := 0.0; END_IF
    IF u_global > 1.0 THEN u_global := 1.0; END_IF
    load_p0_kw   := LOAD_P_KW_DEFAULT;
    load_q0_kvar := LOAD_Q_KVAR_DEFAULT;
END_IF

// ---------------------------------------------------------------------------
// 2. Dinâmica de cada inversor
// ---------------------------------------------------------------------------
FOR i := 0 TO 17 DO

    // Disponibilidade de energia (irradiância por inversor)
    IF g_SimMode = SIM_MODE_FULL AND g_Ev_Force_U[i] >= 0.0 THEN
        u_inv := g_Ev_Force_U[i];
        IF u_inv > 1.0 THEN u_inv := 1.0; END_IF
    ELSE
        u_inv := u_global;
    END_IF
    g_Inv_U[i] := u_inv;

    // drop_comms: só no modo full
    IF g_SimMode = SIM_MODE_FULL THEN
        g_Inv_CommsDrop[i] := g_Ev_DropComms[i];
    ELSE
        g_Inv_CommsDrop[i] := FALSE;
    END_IF

    // freeze_s: só no modo full; acumulativo — usa o maior valor entre restante e evento
    IF g_SimMode = SIM_MODE_FULL THEN
        IF g_Ev_Freeze_s[i] > g_Inv_Frozen_s[i] THEN
            g_Inv_Frozen_s[i] := g_Ev_Freeze_s[i];
        END_IF
    END_IF

    // Chamar FB de dinâmica do inversor
    fbInv[i](
        p_nom_kw      := INV_P_NOM_KW[i],
        s_nom_kva     := INV_S_NOM_KVA[i],
        tau_p_s       := INV_TAU_P_S[i],
        tau_q_s       := INV_TAU_Q_S[i],
        tick_s        := TICK_S,
        p_ref_pct     := g_Inv_P_Ref_Pct[i],
        pf_cmd_raw    := g_Inv_PF_Cmd_Raw[i],
        u             := u_inv,
        comms_drop    := g_Inv_CommsDrop[i],
        frozen_s      := g_Inv_Frozen_s[i]
    );

    // Realimentar estados e saídas do FB
    g_Inv_P_kW[i]     := fbInv[i].p_kw;
    g_Inv_Q_kVAr[i]   := fbInv[i].q_kvar;
    g_Inv_Frozen_s[i] := fbInv[i].frozen_s_out;

    // Atualizar p_ref_pct efetivo (drop_comms reduz gradualmente)
    IF g_Inv_CommsDrop[i] THEN
        g_Inv_P_Ref_Pct[i] := fbInv[i].p_ref_pct_out;
    END_IF

END_FOR

// ---------------------------------------------------------------------------
// 3. Agregação no PCC
// ---------------------------------------------------------------------------
p_gen := 0.0;
q_gen := 0.0;
FOR i := 0 TO 17 DO
    p_gen := p_gen + g_Inv_P_kW[i];
    q_gen := q_gen + g_Inv_Q_kVAr[i];
END_FOR
g_P_Gen_Total_kW   := p_gen;
g_Q_Gen_Total_kVAr := q_gen;

// ---------------------------------------------------------------------------
// 4. 1ª iteração Thévenin (tensão com carga nominal)
// ---------------------------------------------------------------------------
p_pcc_0 := load_p0_kw   - p_gen;
q_pcc_0 := load_q0_kvar - q_gen;

fbThevenin(
    p_pcc_kw   := p_pcc_0,
    q_pcc_kvar := q_pcc_0,
    vth_ll_v   := THEVENIN_VTH_LL_V,
    r_ohm      := THEVENIN_R_OHM,
    x_ohm      := THEVENIN_X_OHM
);
v_pcc_0 := fbThevenin.v_pcc_ll_v;

// ---------------------------------------------------------------------------
// 5. Correção ZIP com tensão calculada
// ---------------------------------------------------------------------------
fbZipLoad(
    p0_kw   := load_p0_kw,
    q0_kvar := load_q0_kvar,
    v_ll_v  := v_pcc_0,
    v0_ll_v := V_LL_V,
    a_Z     := ZIP_P_Z,
    a_I     := ZIP_P_I,
    a_P     := ZIP_P_P,
    b_Z     := ZIP_Q_Z,
    b_I     := ZIP_Q_I,
    b_P     := ZIP_Q_P
);
load_p_kw   := fbZipLoad.p_kw;
load_q_kvar := fbZipLoad.q_kvar;

// ---------------------------------------------------------------------------
// 6. 2ª iteração Thévenin (com carga corrigida pelo ZIP)
// ---------------------------------------------------------------------------
p_pcc := load_p_kw   - p_gen;
q_pcc := load_q_kvar - q_gen;

s_pcc_sq := p_pcc * p_pcc + q_pcc * q_pcc;
s_pcc    := SQRT(s_pcc_sq);

fbThevenin(
    p_pcc_kw   := p_pcc,
    q_pcc_kvar := q_pcc,
    vth_ll_v   := THEVENIN_VTH_LL_V,
    r_ohm      := THEVENIN_R_OHM,
    x_ohm      := THEVENIN_X_OHM
);
v_pcc_ll := fbThevenin.v_pcc_ll_v;

// Atualizar grandezas internas do PCC
g_Meter_P_PCC_kW   := p_pcc;
g_Meter_Q_PCC_kVAr := q_pcc;
g_Meter_V_PCC_LL_V := v_pcc_ll;

// ---------------------------------------------------------------------------
// 7. Fator de potência no PCC com sinal
//    Positivo = indutivo (Q_pcc > 0)
//    Negativo = capacitivo (Q_pcc < 0)
// ---------------------------------------------------------------------------
IF s_pcc > 1.0E-9 THEN
    pf_mag := ABS(p_pcc) / s_pcc;
ELSE
    pf_mag := 1.0;
END_IF
IF q_pcc >= 0.0 THEN
    pf_signed := pf_mag;
ELSE
    pf_signed := -pf_mag;
END_IF
g_Meter_PFa := pf_signed;
g_Meter_PFb := pf_signed;
g_Meter_PFc := pf_signed;

// ---------------------------------------------------------------------------
// 8. Tensão no secundário do TP (fase-neutro, V)
//    V_pcc_fn  = V_pcc_ll / sqrt(3)
//    V_mt_fn   = V_pcc_fn × (V_MT_nom / V_BT_nom)
//    V_sec_fn  = V_mt_fn / RTP
// ---------------------------------------------------------------------------
IF v_pcc_ll > 0.0 THEN
    v_pcc_fn := v_pcc_ll * SQRT3_INV;
ELSE
    v_pcc_fn := 0.0;
END_IF

IF V_LL_V > 0.0 THEN
    v_mt_fn  := v_pcc_fn * (V_MT_LL_V / V_LL_V);
ELSE
    v_mt_fn  := 0.0;
END_IF

v_mt_ll  := v_mt_fn * SQRT3;

IF RTP > 0.0 THEN
    v_sec_fn := v_mt_fn / RTP;
ELSE
    v_sec_fn := 0.0;
END_IF

g_Meter_Ua_V := v_sec_fn;
g_Meter_Ub_V := v_sec_fn;
g_Meter_Uc_V := v_sec_fn;

// ---------------------------------------------------------------------------
// 9. Corrente no secundário do TC (A)
//    I_mt_prim = S_pcc / (sqrt(3) × V_mt_ll)
//    I_sec     = I_mt_prim / RTC
// ---------------------------------------------------------------------------
IF v_mt_ll > 0.0 THEN
    i_mt_prim := (s_pcc * 1000.0) / (SQRT3 * v_mt_ll);
ELSE
    i_mt_prim := 0.0;
END_IF

IF RTC > 0.0 THEN
    i_sec := i_mt_prim / RTC;
ELSE
    i_sec := 0.0;
END_IF

g_Meter_Ia_A := i_sec;
g_Meter_Ib_A := i_sec;
g_Meter_Ic_A := i_sec;

// ---------------------------------------------------------------------------
// 10. Codifica grandezas do medidor em registradores U16 para Modbus
// ---------------------------------------------------------------------------
MW_Meter[0]  := FC_EncodePF(g_Meter_PFa);
MW_Meter[1]  := FC_EncodePF(g_Meter_PFb);
MW_Meter[2]  := FC_EncodePF(g_Meter_PFc);
MW_Meter[3]  := 0;
MW_Meter[4]  := 0;
MW_Meter[5]  := 0;
MW_Meter[6]  := 0;
MW_Meter[7]  := FC_EncodeI(g_Meter_Ia_A);
MW_Meter[8]  := FC_EncodeI(g_Meter_Ib_A);
MW_Meter[9]  := FC_EncodeI(g_Meter_Ic_A);
MW_Meter[10] := 0;
MW_Meter[11] := FC_EncodeV(g_Meter_Ua_V);
MW_Meter[12] := FC_EncodeV(g_Meter_Ub_V);
MW_Meter[13] := FC_EncodeV(g_Meter_Uc_V);
MW_Meter[14] := 0;  MW_Meter[15] := 0;  MW_Meter[16] := 0;
MW_Meter[17] := 0;  MW_Meter[18] := 0;  MW_Meter[19] := 0;
MW_Meter[20] := 0;  MW_Meter[21] := 0;  MW_Meter[22] := 0;
MW_Meter[23] := 0;  MW_Meter[24] := 0;  MW_Meter[25] := 0;
MW_Meter[26] := 0;  MW_Meter[27] := 0;

END_FUNCTION_BLOCK
