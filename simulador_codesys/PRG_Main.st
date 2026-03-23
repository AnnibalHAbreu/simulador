// =============================================================================
// PRG_Main — Programa principal do simulador
// Equivalente a main.py (task loop)
//
// Deve ser chamado pela Task Cíclica do Codesys com período = TICK_S (50 ms).
//
// CONFIGURAÇÃO DA TASK no Codesys:
//   Nome    : Task_Simulator
//   Tipo    : Cíclica
//   Período : 50 ms         (coincide com TICK_S = 0.05 s)
//   Prioridade: 2           (abaixo do Modbus, acima do HMI)
//
// MAPEAMENTO MODBUS SLAVE (configurar no Codesys Modbus RTU Slave):
//
//   Porta COM1-A (slave 100, medidor):
//     Holding Registers (FC03): MW_Meter[0..27]
//     Base address: 153 (0x0099)
//
//   Porta COM1-B (slave 101, inversor 0):
//     Holding Registers (FC16): %MW mapeado em g_Inv_P_Ref_Pct[0] e g_Inv_PF_Cmd_Raw[0]
//     HR 256 → g_Inv_P_Ref_Pct[0]   (REAL ou UINT conforme escalonamento)
//     HR 257 → g_Inv_PF_Cmd_Raw[0]  (INT)
//     (ver nota de escalonamento abaixo)
//
//   Porta COM2-A (slave 201, inversor 9):
//     HR 256 → g_Inv_P_Ref_Pct[9]
//     HR 257 → g_Inv_PF_Cmd_Raw[9]
//
//   Porta COM2-B (slave 202, inversor 10):
//     HR 256 → g_Inv_P_Ref_Pct[10]
//     HR 257 → g_Inv_PF_Cmd_Raw[10]
//
// NOTA DE ESCALONAMENTO DO MODBUS:
//   HR 256 (%P): o master escreve 0..100 como UINT. Codesys recebe como UINT.
//   Converter: g_Inv_P_Ref_Pct[i] := UINT_TO_REAL(MW_Inv_P_Raw[i]);
//   HR 257 (FP raw): o master escreve 1..100 como UINT.
//   Converter: g_Inv_PF_Cmd_Raw[i] := UINT_TO_INT(MW_Inv_PF_Raw[i]);
//
//   Se o driver Modbus do Codesys mapear diretamente em variáveis tipadas,
//   ajustar os tipos conforme necessário.
// =============================================================================

PROGRAM PRG_Main
VAR
    fbSim           : FB_Simulator;

    // Registradores raw escritos pelo driver Modbus (UINT, 0-based)
    // Estes são os buffers de recepção do driver Modbus Slave.
    // Mapeados via I/O Mapping do Codesys para as portas RS485.
    //
    // COM1-B: inversor 0 (slave 101)
    MW_Inv_P_Raw    : ARRAY[0..17] OF UINT := [18(0)];  // HR 256 de cada inversor
    MW_Inv_PF_Raw   : ARRAY[0..17] OF UINT := [18(100)]; // HR 257 de cada inversor

    i               : INT;
    bFirstScan      : BOOL := TRUE;
END_VAR

// ===========================================================================
// PRIMEIRA VARREDURA: inicializar modo
// ===========================================================================
IF bFirstScan THEN
    bFirstScan  := FALSE;
    g_SimMode   := SIM_MODE_LOOPBACK;   // Inicia sempre em loopback (Etapa 1)
    g_Reset     := TRUE;                // Limpa estados
END_IF

// ===========================================================================
// COPIAR REGISTRADORES MODBUS → VARIÁVEIS DE SIMULAÇÃO
// Converte UINT (recebido via Modbus) para os tipos internos.
// ===========================================================================
FOR i := 0 TO 17 DO
    // HR 256: setpoint %P (0..100 inteiro)
    g_Inv_P_Ref_Pct[i] := UINT_TO_REAL(MW_Inv_P_Raw[i]);
    // Saturar para garantir faixa válida mesmo se master enviar fora
    IF g_Inv_P_Ref_Pct[i] < 0.0   THEN g_Inv_P_Ref_Pct[i] := 0.0;   END_IF
    IF g_Inv_P_Ref_Pct[i] > 100.0 THEN g_Inv_P_Ref_Pct[i] := 100.0; END_IF

    // HR 257: FP raw (1..100)
    g_Inv_PF_Cmd_Raw[i] := UINT_TO_INT(MW_Inv_PF_Raw[i]);
    // Fora de faixa → unitário (decodificado no FB_InverterDyn)
END_FOR

// ===========================================================================
// EXECUTAR SIMULAÇÃO
// ===========================================================================
fbSim();

// ===========================================================================
// MW_Meter[] é atualizado pelo FB_Simulator e lido automaticamente pelo
// driver Modbus Slave quando o master faz FC03 ao slave 100.
// Nenhuma cópia adicional necessária.
// ===========================================================================

END_PROGRAM
