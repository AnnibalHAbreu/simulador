# Roteiro de Testes — Startup sem Hardware (FB_Startup)
## PPC-GD — WAGO CC100 + Simulador Windows

**Versão:** 1.0 — Março 2026

---

## O Problema

O `FB_Startup` tem **5 barreiras sequenciais** que dependem de hardware físico:

```
stInit → stCheck_COM → stCheck_Medidor → stCheck_Inversores → stWait_K1 → stWait_K2 → stDone
```

Sem medidor e sem inversores conectados, o startup trava em `stCheck_Medidor` com timeout de 10 s e vai para `stError` → `MachineState = ERRO`. As etapas E1 a E7 do roteiro principal ficam inacessíveis.

---

## Duas Abordagens Disponíveis

### Opção A — `DEBUG_MODE` (para rodar E1–E7 sem hardware)

O código já possui uma diretiva de pré-processador no `PRG_MainProgram`. Basta descomentá-la:

```pascal
// Mudar de:
// {#define DEBUG_MODE}

// Para:
{#define DEBUG_MODE}
```

Com isso, na transição do estado START o sistema **pula direto para CONTROL**, ignorando completamente `stCheck_COM`, `stCheck_Medidor`, `stCheck_Inversores`, `stWait_K1` e `stWait_K2`. O simulador já responde em Loopback, então READ e WRITE funcionam normalmente.

> **Usar para:** etapas E1 a E7 completas do roteiro principal.
>
> **Não usar para:** testar o startup em si — use a Opção B para isso.
>
> ⚠️ **CRÍTICO:** remover `DEBUG_MODE` antes do upload final para campo. Nunca fazer deploy com esta define ativa.

---

### Opção B — Forçar condições via Watch Window (para testar o startup)

Para testar **cada sub-estado do startup individualmente**, sem modificar a lógica de produção e sem hardware real, injete as condições que cada estado espera diretamente pela Watch Window:

| Sub-estado | O que ele espera | Como simular |
|---|---|---|
| `stCheck_COM` | `xMaster01IsReady = TRUE` e `xMaster02IsReady = TRUE` | O driver Modbus RTU sobe automaticamente se as portas COM estão configuradas no projeto. Não depende de dispositivo externo. |
| `stCheck_Medidor` | ACK Modbus do slave 100 dentro de 10 s | Ligar o simulador em **Loopback** antes do CLP. O slave 100 responde ao FC03. |
| `stCheck_Inversores` | `CheckThreshold`% dos inversores configurados respondem | Ligar o simulador em **Loopback** (slaves 101, 201, 202 respondem). |
| `stWait_K1` | `K1_in = TRUE` estável por 500 ms | Escrever `GVL_Main.K1_in := TRUE` na Watch Window. |
| `stWait_K2` | `K2_in = TRUE` estável por 500 ms | Escrever `GVL_Main.K2_in := TRUE` na Watch Window. |

---

## Roteiro de Teste do Startup — Passo a Passo

**Pré-condição para todos os testes abaixo:**
- `DEBUG_MODE` comentado (compilação de produção)
- Parâmetros do T0.1 configurados (`InvActivePower`, `InstalledPower = 120.0`, etc.)
- Simulador Windows em modo **Loopback** (`g_SimMode = 0`) rodando **antes** de ligar o CLP

---

### TS0.1 — stInit (calculado automaticamente)

**O que testa:** Leitura do RTC, cálculo de `InstalledPower`, inicialização dos arrays internos.

**Como executar:**

1. Ligar o CLP com `DEBUG_MODE` comentado.
2. Abrir a Watch Window e adicionar as variáveis abaixo.
3. Observar `fbStart.stState` avançar de `stInit` para `stCheck_COM` em menos de 1 ciclo (automático — sem intervenção).

**Variáveis a monitorar:**

| Variável | Valor esperado |
|---|---|
| `fbStart.stState` | Avança de `stInit` para `stCheck_COM` |
| `GVL_Main.timestampUTC` | Valor não-zero (RTC lido com sucesso) |
| `GVL_Alarm.CRIT_RTC_FAIL` | `FALSE` |
| `GVL_Main.InstalledPower` | `120.0` kW |
| `fbStart.bSoftInitDone` | `TRUE` |

**Critério de aprovação:**
- [ ] `stState` avança para `stCheck_COM` automaticamente
- [ ] `CRIT_RTC_FAIL = FALSE`
- [ ] `InstalledPower = 120.0`
- [ ] `bSoftInitDone = TRUE`
- [ ] Eventos `INFO_STARTUP_BEGIN`, `INFO_RTC_OK` e `INFO_INSTALLED_POWER` no log

---

### TS0.2 — stCheck_COM (driver Modbus RTU)

**O que testa:** Se os drivers seriais COM1 e COM2 inicializaram corretamente.

**Como executar:**

1. Não requer ação — o driver sobe automaticamente após `stInit`.
2. Monitorar na Watch Window:

| Variável | Valor esperado |
|---|---|
| `fbStart.xMaster01IsReady` | `TRUE` |
| `fbStart.xMaster02IsReady` | `TRUE` |
| `fbStart.TonComTimeout.ET` | Não deve chegar a 10 s |
| `fbStart.stState` | Avança para `stCheck_Medidor` |

3. Se o driver **não subir** (timeout de 10 s esgotado):
   - Verificar configuração das portas COM no projeto Codesys (Device Tree → Serial Port)
   - Verificar que o hardware do CC100 tem as portas habilitadas
   - `CRIT_SERIAL_INIT_FAILED` aparece no log → `stError`

**Critério de aprovação:**
- [ ] `xMaster01IsReady = TRUE` e `xMaster02IsReady = TRUE` dentro de 10 s
- [ ] `INFO_SERIAL_COM_OK` no log
- [ ] `stState` avança para `stCheck_Medidor`

---

### TS0.3 — stCheck_Medidor (com simulador Loopback)

**O que testa:** Se o medidor (slave 100) responde ao FC03 dentro do timeout de 10 s.

**Como executar:**

1. Confirmar que o simulador está em Loopback e respondendo na porta COM1.
2. Monitorar na Watch Window:

| Variável | Valor esperado |
|---|---|
| `fbStart.TonMedTimeout.ET` | Não deve chegar a 10 s |
| `GVL_Comm.eMeterResult` | `DONE` |
| `fbStart.stState` | Avança para `stCheck_Inversores` |

**Para testar o caminho de falha (timeout):**
1. Desligar o simulador durante este estado.
2. Aguardar `TonMedTimeout.ET` atingir 10 s.
3. Verificar:
   - `CRIT_MEAS_INIC_ERRO_TIMEOUT` ou `CRIT_MEAS_INIC_FAIL` no log
   - `stState = stError`
   - `MachineState = ERRO`

**Critério de aprovação (caminho normal):**
- [ ] `eMeterResult = DONE` antes de 10 s
- [ ] `stState` avança para `stCheck_Inversores`

**Critério de aprovação (caminho de falha):**
- [ ] Timeout gera evento crítico no log
- [ ] `stState = stError` e `MachineState = ERRO`

---

### TS0.4 — stCheck_Inversores (com simulador Loopback)

**O que testa:** Varredura de presença dos inversores configurados. Verifica se pelo menos `CheckThreshold`% respondem.

**Como executar:**

1. Com simulador Loopback rodando (slaves 101, 201, 202 respondendo).
2. Monitorar na Watch Window:

| Variável | Valor esperado |
|---|---|
| `GVL_Comm.abInvOnline_COM1[101]` | `TRUE` |
| `GVL_Comm.abInvOnline_COM2[201]` | `TRUE` |
| `GVL_Comm.abInvOnline_COM2[202]` | `TRUE` |
| `fbCheckInv.uRespondedTotal` | `3` |
| `fbCheckInv.uConfiguredTotal` | `3` |
| `fbStart.stState` | Avança para `stWait_K1` |

**Para testar o limiar `CheckThreshold` (abaixo do mínimo):**
1. Desligar um slave no simulador: `g_Ev_DropComms[0] := TRUE` (slave 101 para de responder).
2. Com 2 de 3 respondendo (66%): verificar se passa ou falha conforme `CheckThreshold` configurado.
3. Verificar `WARN_INV_STARTUP_FAIL` com `rParam1 = 101` (slave ID que não respondeu) no log.

**Critério de aprovação (caminho normal):**
- [ ] 3/3 inversores `abInvOnline = TRUE`
- [ ] `uRespondedTotal = 3`
- [ ] `INFO_INV_CHECK_OK` no log
- [ ] `stState` avança para `stWait_K1`

**Critério de aprovação (caminho de falha):**
- [ ] Slave ausente → `WARN_INV_STARTUP_FAIL` com slave ID correto no log
- [ ] Se abaixo do `CheckThreshold`: `stState = stError`

---

### TS0.5 — stWait_K1 (forçar via Watch Window)

**O que testa:** Se K1 (permissivo / disjuntor de geração) é confirmado com debounce de 500 ms.

**Como executar:**

1. Aguardar `stState = stWait_K1`.
2. **Forçar na Watch Window:** `GVL_Main.K1_in := TRUE`
3. Monitorar:

| Variável | Valor esperado |
|---|---|
| `fbStart.TonDebounceK1.ET` | Contando até 500 ms |
| `fbStart.debouncedK1` | `TRUE` após 500 ms |
| `fbStart.stState` | Avança para `stWait_K2` após debounce |

4. **Testar timeout (K1 não fecha):**
   - Manter `K1_in = FALSE`.
   - Aguardar `TonK1Timeout` (5 s).
   - Verificar `CRIT_K1_TIMEOUT` no log → `stError`.

5. **Testar intermitência (debounce resetando):**
   - Alternar `K1_in` entre `TRUE` e `FALSE` antes dos 500 ms.
   - Verificar que `TonDebounceK1.ET` reinicia a cada borda de descida.
   - O estado não deve avançar enquanto `K1_in` não permanecer estável.

**Critério de aprovação:**
- [ ] `K1_in = TRUE` por ≥ 500 ms → `INFO_K1_CONFIRMED` no log
- [ ] `stState` avança para `stWait_K2`
- [ ] Intermitência < 500 ms não avança o estado
- [ ] Timeout de 5 s sem K1 → `CRIT_K1_TIMEOUT` → `stError`

---

### TS0.6 — stWait_K2 (forçar via Watch Window)

**O que testa:** Se K2 (trip / religador) está confirmado com debounce de 500 ms.

**Como executar:**

1. Aguardar `stState = stWait_K2`.
2. **Forçar na Watch Window:** `GVL_Main.K2_in := TRUE`
3. Monitorar:

| Variável | Valor esperado |
|---|---|
| `fbStart.TonDebounceK2.ET` | Contando até 500 ms |
| `fbStart.debouncedK2` | `TRUE` após 500 ms |
| `fbStart.stState` | Avança para `stDone` após debounce |
| `GVL_Main.MachineState` | Transita para `READ` (2) |

4. **Testar timeout (K2 não fecha):**
   - Manter `K2_in = FALSE`.
   - Aguardar `TonK2Timeout` (5 s).
   - Verificar `CRIT_K2_TIMEOUT` no log → `stError`.

**Critério de aprovação:**
- [ ] `K2_in = TRUE` por ≥ 500 ms → `INFO_K2_CONFIRMED` no log
- [ ] `stState = stDone` → `MachineState = READ`
- [ ] Timeout de 5 s sem K2 → `CRIT_K2_TIMEOUT` → `stError`

---

### TS0.7 — Startup completo de ponta a ponta

**O que testa:** A sequência completa do startup do primeiro boot ao primeiro ciclo de controle.

**Como executar:**

1. Simulador em **Loopback** rodando.
2. Fazer power cycle no CLP (desligar e ligar).
3. Monitorar `fbStart.stState` na Watch Window.
4. **Quando `stState = stWait_K1`:** forçar `GVL_Main.K1_in := TRUE` na Watch Window.
5. **Quando `stState = stWait_K2`:** forçar `GVL_Main.K2_in := TRUE` na Watch Window.
6. Verificar que `MachineState` chega a `READ` e depois ao ciclo normal.

**Sequência esperada de eventos no log (em ordem):**

```
INFO_STARTUP_BEGIN
INFO_RTC_OK
INFO_INSTALLED_POWER       rParam1 = 120.0
INFO_SERIAL_COM_OK
INFO_INVERTER_COUNT        uRespondedTotal = 3
INFO_INV_CHECK_OK
INFO_K1_CONFIRMED
INFO_K2_CONFIRMED
INFO_STARTUP_DONE
INFO_CYCLE_COMPLETE        (primeiro ciclo READ→CONTROL→WRITE concluído)
```

**Critério de aprovação:**
- [ ] Sequência completa de eventos no log, na ordem correta
- [ ] Nenhum evento `CRIT_*` ou `ALARM_*` no log
- [ ] `MachineState = READ` após `stDone`
- [ ] Primeiro `INFO_CYCLE_COMPLETE` aparece no log (sistema operando)
- [ ] LEDs: Verde aceso ao final do startup

---

## Resumo: Quando Usar Cada Abordagem

| Objetivo | Abordagem | Pré-condição |
|---|---|---|
| Testar o startup em si (TS0.1 a TS0.7) | Watch Window para K1/K2 + simulador Loopback | `DEBUG_MODE` comentado |
| Rodar etapas E1 a E7 do roteiro principal | `{#define DEBUG_MODE}` no PRG_MainProgram | Simulador em qualquer modo |
| Deploy em campo / produção | Hardware real (K1, K2, medidor, inversores) | `DEBUG_MODE` removido antes do upload |

---

## Checklist de Encerramento dos Testes de Startup

- [ ] `stInit` calculou `InstalledPower = 120.0` kW corretamente
- [ ] `stCheck_COM`: ambos os drivers subiram em < 10 s
- [ ] `stCheck_Medidor`: slave 100 respondeu com simulador Loopback
- [ ] `stCheck_Medidor`: timeout gera evento crítico correto (testado propositalmente)
- [ ] `stCheck_Inversores`: 3/3 inversores online com simulador Loopback
- [ ] `stCheck_Inversores`: slave ausente gera `WARN_INV_STARTUP_FAIL` com slave ID correto
- [ ] `stWait_K1`: debounce de 500 ms funcionando (intermitência não avança)
- [ ] `stWait_K1`: timeout de 5 s gera `CRIT_K1_TIMEOUT`
- [ ] `stWait_K2`: debounce de 500 ms funcionando
- [ ] `stWait_K2`: timeout de 5 s gera `CRIT_K2_TIMEOUT`
- [ ] Startup ponta a ponta: sequência de log correta sem eventos críticos

---

*Documento gerado em março de 2026*
*Controlador: PPC-GD v1.x — WAGO CC100 (751-9402) — Codesys V3.5 SP21 Patch 4*
