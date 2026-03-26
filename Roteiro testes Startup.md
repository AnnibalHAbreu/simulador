// Mudar de:
// {#define DEBUG_MODE}

// Para:
{#define DEBUG_MODE}
```

Com isso, na transição do estado START o sistema **pula direto para CONTROL**, ignorando completamente stCheck_COM, stCheck_Medidor, stCheck_Inversores, stWait_K1 e stWait_K2. O simulador já responde em Loopback, então READ e WRITE funcionam normalmente.

**Usar para:** etapas E1 a E7 completas.  
**Não usar para:** testar o startup em si (o objetivo das próximas etapas abaixo).

---

### Opção B — Forçar estados via Watch Window (sem recompilar)

Para testar **cada sub-estado do startup individualmente**, sem modificar código e sem hardware real, use a Watch Window para injetar as condições que cada estado espera:

| Sub-estado | O que ele espera | O que forçar na Watch Window |
|---|---|---|
| `stCheck_COM` | `xMaster01IsReady = TRUE` e `xMaster02IsReady = TRUE` | Essas variáveis são internas do FB. O driver Modbus RTU deve estar em RUNNING. Se o driver sobe normalmente (COM configurada, mesmo sem dispositivo), avança sozinho. |
| `stCheck_Medidor` | ACK Modbus do slave 100 dentro de 10 s | Ligar simulador em **Loopback** antes de ligar o CLP. O slave 100 responde ao FC03. |
| `stCheck_Inversores` | `CheckThreshold` % dos inversores configurados respondem | Ligar simulador em **Loopback** (slaves 101, 201, 202 respondem). |
| `stWait_K1` | `K1_in = TRUE` por 500 ms | `GVL_Main.K1_in := TRUE` na Watch Window. |
| `stWait_K2` | `K2_in = TRUE` por 500 ms | `GVL_Main.K2_in := TRUE` na Watch Window. |

---

## Roteiro de teste do startup passo a passo

### Pré-condição: simulador em modo **Loopback** rodando antes de ligar o CLP

---

### TS0.1 — stInit (calculado automaticamente)

**O que testa:** RTC, cálculo de InstalledPower, inicialização dos arrays.

**Como executar:**
1. Compilar com `DEBUG_MODE` comentado (produção normal).
2. Ligar o CLP.
3. Watch Window: monitorar `fbStart.stState`.
4. Verificar que `stState` avança de `stInit` para `stCheck_COM` em menos de 1 ciclo.
5. Verificar na Watch Window:
   - `GVL_Main.timestampUTC` — deve ser não-zero (RTC lido)
   - `GVL_Alarm.CRIT_RTC_FAIL = FALSE`
   - `GVL_Main.InstalledPower = 120.0` (se parâmetros do T0.1 estiverem corretos)
   - `fbStart.bSoftInitDone = TRUE`

**Critério:** `stState` avança para `stCheck_COM`, sem `CRIT_RTC_FAIL`, `InstalledPower = 120.0`.

---

### TS0.2 — stCheck_COM (driver Modbus RTU)

**O que testa:** Se os drivers seriais COM1 e COM2 subiram corretamente.

**Como executar:**
1. O driver sobe automaticamente se as portas COM estão configuradas no projeto Codesys. Não depende de hardware externo.
2. Watch Window: monitorar `fbStart.xMaster01IsReady` e `fbStart.xMaster02IsReady`.
3. Se o CLP não tiver as portas COM fisicamente conectadas mas o driver estiver configurado, o driver pode não subir. Nesse caso:
   - Verificar se `TonComTimeout.ET` está contando (timeout de 10 s)
   - Se timeout estourar: `CRIT_SERIAL_INIT_FAILED` no log → `stError`

**Critério:** Ambos `xMaster01IsReady = TRUE` e `xMaster02IsReady = TRUE` dentro de 10 s. `INFO_SERIAL_COM_OK` no log.

---

### TS0.3 — stCheck_Medidor (com simulador Loopback)

**O que testa:** Se o medidor (slave 100) responde ao FC03 dentro do timeout de 10 s.

**Como executar:**
1. **Simulador deve estar em Loopback e rodando antes deste passo.**
2. Watch Window: monitorar `fbStart.TonMedTimeout.ET` (conta até 10 s).
3. Se o slave 100 responder: `stState` avança para `stCheck_Inversores`.
4. Se não responder (timeout): `CRIT_MEAS_INIC_ERRO_TIMEOUT` ou `CRIT_MEAS_INIC_FAIL` no log → `stError`.

**Para testar o caminho de falha propositalmente:**
- Desligar o simulador durante este estado
- Verificar que o evento crítico correto é gerado no log após 10 s
- Verificar que `stState = stError` e `MachineState = ERRO`

**Critério:** Com simulador Loopback ativo, `stState` avança para `stCheck_Inversores` sem timeout.

---

### TS0.4 — stCheck_Inversores (com simulador Loopback)

**O que testa:** Varredura de presença dos inversores configurados. Verifica se pelo menos `CheckThreshold`% respondem.

**Como executar:**
1. Com simulador Loopback (slaves 101, 201, 202 respondendo).
2. Watch Window:
   - `GVL_Comm.abInvOnline_COM1[101]` — deve ficar `TRUE`
   - `GVL_Comm.abInvOnline_COM2[201]` — deve ficar `TRUE`
   - `GVL_Comm.abInvOnline_COM2[202]` — deve ficar `TRUE`
   - `fbCheckInv.uRespondedTotal` — deve ser `3`
   - `fbCheckInv.uConfiguredTotal` — deve ser `3`
3. Com todos respondendo: `stState` avança para `stWait_K1`.

**Para testar o limiar `CheckThreshold`:**
- Desligar um slave no simulador (ex.: `g_Ev_DropComms[0] := TRUE` — slave 101)
- Com 2 de 3 respondendo (66%): dependendo do `CheckThreshold` configurado, pode passar ou falhar
- Verificar `WARN_INV_STARTUP_FAIL` para o slave que não respondeu

**Critério:** 3/3 inversores online → `stState = stWait_K1`. Log registra `INFO_INV_CHECK_OK`.

---

### TS0.5 — stWait_K1 (forçar via Watch Window)

**O que testa:** Se K1 (permissivo/disjuntor de geração) é confirmado com debounce de 500 ms.

**Como executar:**
1. Quando `stState = stWait_K1`, o startup aguarda `K1_in = TRUE` por 500 ms consecutivos.
2. **Forçar na Watch Window:** `GVL_Main.K1_in := TRUE`
3. Monitorar `fbStart.TonDebounceK1.ET` contando até 500 ms.
4. Após 500 ms estável: `INFO_K1_CONFIRMED` no log, `stState` avança para `stWait_K2`.
5. **Testar timeout:** manter `K1_in = FALSE` e aguardar `TonK1Timeout` (5 s) → `CRIT_K1_TIMEOUT` → `stError`.
6. **Testar intermitência:** alternar `K1_in` entre TRUE e FALSE antes dos 500 ms → debounce deve resetar.

**Critério:** `K1_in = TRUE` por ≥ 500 ms → `INFO_K1_CONFIRMED` no log → `stState = stWait_K2`.

---

### TS0.6 — stWait_K2 (forçar via Watch Window)

**O que testa:** Se K2 (trip/religador) está confirmado aberto (condição de segurança inicial).

**Como executar:**
1. Quando `stState = stWait_K2`:
2. **Forçar na Watch Window:** `GVL_Main.K2_in := TRUE`
3. Monitorar `fbStart.TonDebounceK2.ET` contando até 500 ms.
4. Após 500 ms: `INFO_K2_CONFIRMED` → `stState = stDone` → `MachineState = READ`.
5. **Testar timeout:** manter `K2_in = FALSE` → `CRIT_K2_TIMEOUT` após 5 s → `stError`.

**Critério:** `K2_in = TRUE` por ≥ 500 ms → `INFO_K2_CONFIRMED` → `stState = stDone` → `MachineState = READ`.

---

### TS0.7 — Startup completo de ponta a ponta

**Como executar:**
1. Simulador em Loopback rodando.
2. CLP power cycle (reiniciar do zero).
3. Quando `stState = stWait_K1`: forçar `K1_in := TRUE` na Watch Window.
4. Quando `stState = stWait_K2`: forçar `K2_in := TRUE` na Watch Window.
5. Verificar que `MachineState` chega a READ e depois ao ciclo normal.

**Sequência esperada de eventos no log:**
```
INFO_STARTUP_BEGIN
INFO_RTC_OK
INFO_INSTALLED_POWER       (rParam1 = 120.0)
INFO_SERIAL_COM_OK
INFO_INVERTER_COUNT        (uRespondedTotal = 3)
INFO_INV_CHECK_OK
INFO_K1_CONFIRMED
INFO_K2_CONFIRMED
INFO_STARTUP_DONE
INFO_CYCLE_COMPLETE        (primeiro ciclo de controle)