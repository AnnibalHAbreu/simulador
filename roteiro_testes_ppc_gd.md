# Roteiro de Testes — PPC-GD
## Controlador de Exportação de Energia Solar (WAGO CC100 + Simulador Windows)

**Versão:** 1.0 — Março 2026  
**Hardware:** WAGO CC100 (751-9402), Codesys V3.5 SP21 Patch 4  
**Simulador:** Windows, Modbus RTU RS485  

---

## Topologia de Referência

```
WAGO CC100 (Master Modbus RTU)
├── COM1 → Slave 100  : Medidor (FC03, 28 regs a partir de 0x0099)
│         Slave 101  : Inversor 60 kW (FC16, HR256/HR257)
└── COM2 → Slave 201  : Inversor 30 kW (FC16, HR256/HR257)
          Slave 202  : Inversor 30 kW (FC16, HR256/HR257)

Potência instalada total: 120 kW
```

**Convenção de sinais do medidor (CRÍTICO — interpretar todos os resultados com base nisto):**

| Sinal de Pt | Significado |
|---|---|
| Positivo (+) | Importando da rede (Consumo > Geração) |
| Negativo (−) | Exportando para a rede (Geração > Consumo) |

Setpoints de exportação são sempre **negativos** (ex.: limite de 90 kW → `ExportLimit_kW = 90.0`, `P_setpoint = −90.0`).

---

## Modos do Simulador

| Modo | Constante | Quando usar |
|---|---|---|
| Loopback | `SIM_MODE_LOOPBACK` | Validação de comunicação — valores fixos, sem física |
| Openloop | `SIM_MODE_OPENLOOP` | Controle em regime estável — física ativa, carga e irradiância fixas |
| Full | `SIM_MODE_FULL` | Cenários dinâmicos — perfis de irradiância + carga + injeção de falhas |

Para alterar o modo: modificar `g_SimMode` na Watch Window do Codesys (simulador).

---

## Ferramentas necessárias

- **Codesys V3.5 SP21 Patch 4** com projeto do simulador carregado no PC Windows
- **Codesys V3.5 SP21 Patch 4** com projeto do PPC-GD carregado no WAGO CC100
- **Watch Window** do Codesys (CLP e simulador) — monitoramento em tempo real
- **Log de eventos** (`GVL_Log` / FB_EventLog) — registro de alarmes e transições
- **WebVisu** (IHM web do CLP) — para comandos de operador
- **Multímetro / analisador de rede** — para verificação física (opcional, nas etapas com hardware)
- Cabo RS485 entre PC e WAGO para cada porta COM

---

## Índice de Etapas

| Etapa | Descrição | Modo simulador |
|---|---|---|
| E0 | Pré-requisitos e configuração inicial | Manual (sem simulador) |
| E1 | Validação de comunicação (Loopback) | Loopback |
| E2 | Leitura e validação de medição | Openloop |
| E3 | Controle de potência ativa (P) | Openloop |
| E4 | Controle de fator de potência / reativo (Q) | Openloop |
| E5 | Máquina de estados e proteções | Openloop |
| E6 | Injeção de falhas | Full |
| E7 | Cenários integrados com perfil dinâmico | Full |

---

---

# ETAPA 0 — Pré-requisitos e Configuração Inicial

**Modo simulador:** Nenhum (manual, sem simulador ligado)  
**Objetivo:** Garantir que o CLP está configurado corretamente antes de qualquer teste. Falhar aqui invalida todos os testes subsequentes.

---

## T0.1 — Verificação de parâmetros persistentes (GVL_Pers)

### Como executar

1. Conectar ao WAGO CC100 via Codesys (Login → Online → sem executar programa ainda, ou em modo STOP).
2. Abrir **Watch Window** e adicionar as variáveis abaixo.
3. Verificar que cada variável tem o valor esperado. Se não tiver, escrever o valor correto diretamente na Watch Window (duplo clique → Write Value) ou via WebVisu na tela de configuração.
4. Para variáveis PERSISTENT RETAIN (GVL_Pers), os valores sobrevivem a power cycle — confirmar que não existem valores "fantasmas" de testes anteriores nos arrays de inversores.

### Variáveis a verificar

| Variável | Valor esperado | Observação |
|---|---|---|
| `GVL_Pers.InvActivePower_COM1[101]` | `60.0` | kW nominal do inversor COM1 |
| `GVL_Pers.InvSmaxPower_COM1[101]` | `66.0` | kVA — ~110% do nominal |
| `GVL_Pers.InvActivePower_COM2[201]` | `30.0` | kW nominal inversor 1 COM2 |
| `GVL_Pers.InvSmaxPower_COM2[201]` | `33.0` | kVA |
| `GVL_Pers.InvActivePower_COM2[202]` | `30.0` | kW nominal inversor 2 COM2 |
| `GVL_Pers.InvSmaxPower_COM2[202]` | `33.0` | kVA |
| `GVL_Pers.Kp_P` | `0.25` | Ganho proporcional PI |
| `GVL_Pers.Ki_P` | `0.02` | Ganho integral PI |
| `GVL_Pers.RampUp_P` | `15.0` | kW/s — rampa de subida |
| `GVL_Pers.RampDown_P` | `20.0` | kW/s — rampa de descida |
| `GVL_Pers.Deadband_P` | `1.0` | % da potência instalada |
| `GVL_Pers.PF_target` | `0.92` | Fator de potência alvo |
| `GVL_Pers.bExportEnabled` | `FALSE` | Começa com exportação desabilitada |
| `GVL_Pers.ProfileCodeCOM1` | código fabricante | Ver tabela de perfis |
| `GVL_Pers.ProfileCodeCOM2` | código fabricante | Ver tabela de perfis |
| `GVL_HW.TC_Power_kW` | valor calculado | √3 × V × I_TC (ex.: 329 kW para TC 500A, 380V) |
| `GVL_HW.SafetyMargin_pct` | `3.0` | Margem de segurança do TC |
| `GVL_HW.MeasDeviceType` | tipo correto | CHINT_DTSU666 ou RELAY_URP1439TU |
| `GVL_HW.MeterSlaveId` | `100` | Slave ID do medidor |

> **Verificar também:** todos os slots de inversores **não usados** devem ter `InvActivePower = 0.0` para não serem incluídos na potência instalada calculada.

### Verificação de InstalledPower calculada

Após iniciar o programa (estado START), verificar:
- `GVL_Main.InstalledPower` deve ser exatamente `120.0` kW (60 + 30 + 30)
- Se for diferente: revisar os arrays de potência acima

### Critério de aprovação

- [ ] Todos os parâmetros com valores corretos confirmados na Watch Window
- [ ] `GVL_Main.InstalledPower = 120.0` kW após START
- [ ] `GVL_Alarm.CRIT_INSTALLED_PWR_ZERO = FALSE`
- [ ] Nenhum alarme `CRIT_*` no log de eventos

---

## T0.2 — Verificação da agenda (FB_Scheduler)

### Como executar

1. Com o CLP em RUN (aguardar passar pelo estado START sem erro).
2. Identificar o dia da semana atual e a hora atual (1=Dom, 2=Seg, ..., 7=Sáb).
3. Na Watch Window, escrever: `GVL_Pers.WeekSchedule_kW[dia_atual][hora_atual] := 90.0`
   - Exemplo para segunda-feira às 14h: `WeekSchedule_kW[2][14] := 90.0`
4. Aguardar o sistema completar um ciclo READ→CONTROL.
5. Verificar que `GVL_Main.ExportLimit_kW = 90.0` no estado CONTROL.

> **Atenção com horário de verão:** se `GVL_Pers.bHorarioVerao = TRUE`, o scheduler adiciona 1h. Ajustar o índice do array de acordo.

### Critério de aprovação

- [ ] `GVL_Main.ExportLimit_kW` reflete o valor configurado na agenda
- [ ] Ao configurar o horário adjacente com valor diferente, a transição ocorre corretamente na virada de hora

---

---

# ETAPA 1 — Validação de Comunicação (Loopback)

**Modo simulador:** `SIM_MODE_LOOPBACK` (g_SimMode = 0)  
**Objetivo:** Verificar protocolo Modbus RTU, endereçamento de slaves, codificação de registradores e integridade da cadeia de leitura/escrita — sem física ativa. Esta é a etapa de "shake hands" entre o controlador e o simulador.

---

## T1.1 — Leitura do medidor (FC03, Slave 100)

### Como executar

1. Iniciar o simulador Windows em modo Loopback (`g_SimMode = 0`).
2. Verificar que a porta COM1 está conectada e configurada (9600bps, N, 8, 1).
3. Ligar o CLP e aguardar o estado START completar.
4. Observar o estado `GVL_Main.MachineState` transitar para READ.
5. Na Watch Window do CLP, monitorar:
   - `GVL_Comm.eMeterResult` — deve ser `DONE` (não `TIMEOUT`)
   - `GVL_Comm.bMeterReadDone` — deve ficar TRUE a cada ciclo
6. Verificar os valores decodificados nas variáveis globais:

| Variável | Valor esperado (Loopback) |
|---|---|
| `GVL_Main.PFt` | ≈ 0.92 |
| `GVL_Main.PFa` | ≈ 0.92 |
| `GVL_Main.PFb` | ≈ 0.92 |
| `GVL_Main.PFc` | ≈ 0.92 |
| `GVL_Main.Ia` | ≈ 2.5 A (valor secundário) |
| `GVL_Main.Ib` | ≈ 2.5 A |
| `GVL_Main.Ic` | ≈ 2.5 A |
| `GVL_Main.Ua` | ≈ 66.4 V (secundário TP, com RTP=120) |
| `GVL_Main.Ub` | ≈ 66.4 V |
| `GVL_Main.Uc` | ≈ 66.4 V |

> **Referência registradores raw (Loopback):** MW[0]=15073 (PFa), MW[7]=640 (Ia), MW[11]=8499 (Ua). Conferir diretamente no simulador se necessário.

7. Verificar que `FB_ValidaDados.bDadosOK = TRUE` (dados aceitos como válidos).
8. Verificar que nenhum alarme de range está ativo em `GVL_Alarm`.

### Diagnóstico de falhas

| Sintoma | Causa provável | Ação |
|---|---|---|
| `eMeterResult = TIMEOUT` | Cabo desconectado, Slave ID errado, baudrate errado | Verificar cabeamento, `GVL_HW.MeterSlaveId`, configuração serial |
| Valores totalmente errados | MeasDeviceType incorreto | Verificar `GVL_HW.MeasDeviceType` |
| `ALARM_MEAS_RANGE_ERROR = TRUE` | Escala TP/TC errada | Verificar `GVL_HW.RTP` e `GVL_HW.RTC` |
| `bDadosOK = FALSE` | Dados fora da faixa esperada | Verificar PMAX, IMAX, VMIN/VMAX em GVL_HW |

### Critério de aprovação

- [ ] `GVL_Comm.eMeterResult = DONE` de forma consistente
- [ ] Valores decodificados dentro de ±2% dos valores fixos do Loopback
- [ ] `FB_ValidaDados.bDadosOK = TRUE`
- [ ] Nenhum alarme `ALARM_MB_APP_TIMEOUT` no log

---

## T1.2 — Escrita nos inversores (FC16, Slaves 101/201/202)

### Como executar

1. Com simulador em Loopback e CLP em RUN.
2. Aguardar o sistema completar pelo menos um ciclo READ→CONTROL→WRITE.
3. Na Watch Window do CLP, verificar os setpoints calculados para cada inversor:
   - `GVL_Main.P_inv_Percent_COM1[101]` — percentual de P para o inversor 60kW
   - `GVL_Main.PF_inv_COM1[101]` — FP físico com sinal (±1.0)
   - Idem para COM2[201] e COM2[202]
4. Com `bExportEnabled = FALSE` (Zero Grid), **todos devem ser 0.0%**.
5. No simulador Windows, verificar o log de recepção de FC16:
   - Slave 101 deve ter recebido HR256=0 (P=0%) e HR257=código para FP=1.0
   - Slaves 201 e 202 idem
6. **Teste com valor não-zero (opcional):** Forçar manualmente via Watch Window:
   - `GVL_Main.P_inv_Percent_COM1[101] := 50.0`
   - `GVL_Main.PF_inv_COM1[101] := 0.95`
   - Executar um ciclo de WRITE e verificar que o simulador registrou HR256=50 e HR257=código correto para 0.95 no perfil do fabricante.

> **CRÍTICO:** Confirme que `FC_EncodePF` produz o código de registro correto para o fabricante configurado em `GVL_Pers.ProfileCodeCOM1/2`. Um erro aqui faz o inversor operar com FP errado **silenciosamente**.

### Diagnóstico de falhas

| Sintoma | Causa provável | Ação |
|---|---|---|
| `WARN_WRITE_INV_TIMEOUT` para slave 101 | Cabo COM1 para inversores desconectado | Verificar cabeamento |
| `WARN_WRITE_INV_TIMEOUT` para slaves 201/202 | Cabo COM2 desconectado | Verificar COM2 |
| FP escrito errado | ProfileCode incorreto ou FC_EncodePF com bug | Verificar perfil do fabricante e decodificar o valor raw recebido |

### Critério de aprovação

- [ ] FC16 recebido pelos três slaves sem timeout
- [ ] Com `bExportEnabled = FALSE`: todos os inversores recebem P=0%
- [ ] FC_EncodePF produz valor correto para o perfil do fabricante
- [ ] Nenhum `WARN_WRITE_INV_ERROR` ou `WARN_WRITE_INV_TIMEOUT` em operação normal

---

## T1.3 — Ciclo completo READ→CONTROL→WRITE→IDLE

### Como executar

1. Com simulador Loopback, `bExportEnabled = FALSE`, CLP em RUN.
2. Abrir Watch Window e adicionar `GVL_Main.MachineState`.
3. Monitorar a sequência de estados por pelo menos **5 ciclos completos** (~5 segundos).
4. Verificar no log de eventos a presença repetida de `INFO_CYCLE_COMPLETE` (código 0x1600).
5. Verificar que `tonReadTimeout.Q = FALSE` e `tonWriteTimeout.Q = FALSE` em todo momento.
6. Anotar o tempo de ciclo real: medir o intervalo entre dois `INFO_CYCLE_COMPLETE` consecutivos. Deve ser próximo de 1 segundo.

### Critério de aprovação

- [ ] Sequência de estados: IDLE→READ→CONTROL→WRITE→IDLE confirmada ciclicamente
- [ ] `INFO_CYCLE_COMPLETE` aparece no log a cada ciclo
- [ ] Tempo de ciclo ≈ 1.0 s (tolerância: 0.8 s a 1.5 s)
- [ ] Nenhum timeout de leitura ou escrita em operação normal

---

---

# ETAPA 2 — Leitura e Validação de Medição

**Modo simulador:** `SIM_MODE_OPENLOOP` (g_SimMode = 1)  
**Objetivo:** Verificar que `FB_ValidaDados` aceita dados válidos, rejeita inválidos, aplica o filtro EMA corretamente e não deixa dados corrompidos chegarem ao controlador.

---

## T2.1 — Validação de faixas físicas normais

### Como executar

1. Iniciar simulador em Openloop com configuração padrão:
   - Na Watch Window do simulador: `LOAD_P_KW_DEFAULT := 200.0`, `LOAD_Q_KVAR_DEFAULT := 50.0`
   - Todos os inversores a 0% (nenhum setpoint ainda enviado pelo CLP)
2. Ligar CLP e aguardar estabilização.
3. Verificar na Watch Window do CLP:
   - `GVL_Main.Pt` deve ser positivo (≈ +200 kW — importando, pois geração = 0)
   - `GVL_Main.Qt` deve ser positivo (≈ +50 kvar — carga indutiva)
   - `GVL_Main.PFt` deve estar entre 0.95 e 0.98 (carga com cos(φ) ≈ 0.97)
   - `FB_ValidaDados.bDadosOK = TRUE`
4. Agora habilitar inversores a 100% no simulador:
   - Na Watch Window do simulador: forçar `g_Inv_P_Ref_Pct[0] := 100.0` (inversor 101)
   - Aguardar alguns ciclos
5. Verificar que `GVL_Main.Pt` fica negativo (usina exportando ≈ −(120−200) = ainda importando, pois geração < carga).
6. Para ver exportação: reduzir carga no simulador para `LOAD_P_KW_DEFAULT := 50.0` e verificar `Pt < 0`.

### Critério de aprovação

- [ ] `bDadosOK = TRUE` estável com medições físicas válidas
- [ ] `Pt` positivo com inversores a 0%, negativo com geração > carga
- [ ] `PFt` entre 0.5 e 1.0 em todos os cenários
- [ ] Nenhum alarme de range espúrio

---

## T2.2 — Comportamento com dado fora de faixa

### Como executar

1. Com simulador em Openloop e CLP operando normalmente.
2. Capturar o valor atual de `GVL_Main.Pt` (ex.: +150 kW). Este é o último valor válido.
3. No simulador, injetar um valor impossível de potência:
   - Alterar o buffer Modbus para produzir `Pt > GVL_HW.PMAX` (ex.: PMAX = 3200 kW → forçar Pt = 4000 kW)
   - Ou simplesmente: na Watch Window do simulador, forçar `g_Meter_P_kW := 9999.0` temporariamente
4. Verificar na Watch Window do CLP:
   - `GVL_Alarm.ALARM_MEAS_RANGE_ERROR = TRUE`
   - `FB_ValidaDados.bDadosOK = FALSE`
   - `GVL_Main.Pt` **não muda** — mantém o último valor válido (≈ +150 kW)
   - Log registra `ALARM_MEAS_PT_RANGE` com o valor inválido como parâmetro
5. Repetir o erro por 5 ciclos consecutivos e verificar:
   - `FB_ValidaDados.nErrors` incrementa até 5 (clampado)
   - `FB_ValidaDados.bPoucosErros = FALSE` após o 5º erro
6. Restaurar valor válido e verificar recuperação:
   - `nErrors` decrementa a cada ciclo OK
   - `bDadosOK` volta a TRUE no primeiro ciclo válido
   - `bPoucosErros` volta a TRUE quando nErrors < 5

### Critério de aprovação

- [ ] Dado inválido → `bDadosOK = FALSE`, globais não atualizadas
- [ ] `ALARM_MEAS_RANGE_ERROR` ativo com dado inválido
- [ ] Após 5 erros consecutivos: `bPoucosErros = FALSE`
- [ ] Recuperação gradual ao restaurar dado válido
- [ ] Controlador não vai a FAIL por apenas 1 ou 2 erros isolados (deve tolerar até `RETRIES_READ` falhas antes de escalar)

---

## T2.3 — Filtro EMA — constante de tempo

### Como executar

1. Com simulador em Openloop, sistema estabilizado com carga = 100 kW.
2. Registrar valor atual de `GVL_Main.Pt` (deve ser ≈ +100 kW filtrado).
3. Aplicar degrau: alterar carga no simulador de 100 kW para 200 kW instantaneamente.
   - Watch Window simulador: `LOAD_P_KW_DEFAULT := 200.0`
4. Registrar o valor de `GVL_Main.Pt` a cada ciclo (1 segundo) durante 15 segundos.
5. Calcular a constante de tempo do filtro EMA com `ALPHA = 0.25`:
   - Fórmula: τ = (1 − ALPHA) / ALPHA × CycleTime = (0.75 / 0.25) × 1 = 3 segundos
   - Em 3 ciclos, `Pt` deve ter avançado ≈ 63% do degrau de 100 kW
   - Em 3 ciclos: Pt esperado ≈ 100 + 63 = 163 kW (de 100 partindo para 200)
6. Verificar que o filtro suaviza sem introduzir erro estacionário (após 15–20 ciclos, Pt deve estar em ≈ 200 kW).

> **Atenção:** o filtro é aplicado sobre o dado validado. Se `bDadosOK = FALSE`, o filtro não atualiza.

### Critério de aprovação

- [ ] Em 3 ciclos após o degrau, `Pt` avança ≈ 63% da variação total
- [ ] Sem erro estacionário após convergência (≈ 20 ciclos)
- [ ] Sem oscilação pós-degrau

---

## T2.4 — Validação cruzada Pa+Pb+Pc ≈ Pt (apenas para medidor CHINT_DTSU666)

> Pular este teste se `GVL_HW.MeasDeviceType = RELAY_URP1439TU`

### Como executar

1. Com simulador Openloop e medidor tipo CHINT, verificar na Watch Window:
   - `GVL_Main.Pa + GVL_Main.Pb + GVL_Main.Pc` deve diferir de `GVL_Main.Pt` em menos de 5%
2. Para forçar falha de validação cruzada (simulação):
   - No simulador, fazer com que o registrador de Pt não corresponda à soma das fases
   - Verificar alarme `WARN_MEAS_CROSS_CHECK_PT_SUM` no log
3. Verificar que o evento é logado com `rParam1 = Pt_medido` e `rParam2 = soma_fases`.

### Critério de aprovação

- [ ] Em operação normal, Pa+Pb+Pc ≈ Pt dentro de ±5% (tolerância configurada)
- [ ] Inconsistência detectada gera alarme `WARN_MEAS_CROSS_CHECK_PT_SUM`
- [ ] Evento registrado no log com valores numéricos

---

---

# ETAPA 3 — Controle de Potência Ativa (P)

**Modo simulador:** `SIM_MODE_OPENLOOP` (g_SimMode = 1)  
**Objetivo:** Validar o laço PI, rampa, deadband, safety margin e alocação proporcional entre os três inversores.

---

## T3.1 — Convergência básica Zero Grid (bExportEnabled = TRUE, limite = 0 kW)

### Como executar

1. Configurar simulador Openloop: `LOAD_P_KW_DEFAULT := 80.0`, `LOAD_Q_KVAR_DEFAULT := 20.0`.
2. Configurar agenda com limite = 0 kW: `WeekSchedule_kW[dia][hora] := 0.0` (Zero Grid).
3. CLP em RUN, aguardar estabilizar.
4. Na Watch Window, habilitar exportação: `GVL_Pers.bExportEnabled := TRUE`.
5. Monitorar as seguintes variáveis a cada ciclo por **90 segundos**:
   - `GVL_Main.Pt` — potência medida no ponto de conexão
   - `GVL_Main.MachineState` — deve permanecer em ciclo normal
   - `fbControle.fbPowerCtrl.rPI_erro` — erro do PI
   - `fbControle.fbPowerCtrl.rPI_integ` — acumulador integral
   - `fbControle.fbPowerCtrl.P_cmd_kW` — comando de P total
   - `GVL_Main.P_inv_Percent_COM1[101]` — percentual para inversor 60kW
6. Registrar: tempo até `|Pt| < 3 kW`, valor estabilizado de Pt, presença de oscilação.

**Comportamento esperado:**
- t=0: Pt ≈ +80 kW (importando, pois inversores a 0%)
- PI detecta erro positivo, incrementa geração em até 15 kW/ciclo
- t≈6 ciclos: geração chega a 80 kW, Pt tende a zero
- t≈30 s: convergência com Pt dentro da deadband (±1.2 kW = ±1% × 120 kW)
- Integral continua a eliminar erro residual

### Diagnóstico de oscilação

| Sintoma | Causa | Ação |
|---|---|---|
| Pt oscila ±10 kW após convergência | Kp muito alto | Reduzir Kp_P para 0.15 |
| Pt não converge, cresce indefinidamente | Kp negativo ou sinal de erro invertido | Verificar convenção de sinais em FB_PowerController |
| Convergência muito lenta (> 120 s) | Ki muito baixo | Verificar Ki_P, verificar CycleTime real |

### Critério de aprovação

- [ ] `GVL_Main.Pt` converge para `0 ± 3 kW` em menos de 60 segundos
- [ ] Sem oscilação sustentada após convergência
- [ ] `WARN_PI_P_SATURATED` não persiste após convergência
- [ ] Sistema permanece no ciclo normal (sem FAIL)

---

## T3.2 — Limite de exportação não-zero

### Como executar

1. Configurar simulador: `LOAD_P_KW_DEFAULT := 50.0`.
2. Configurar agenda: `WeekSchedule_kW[dia][hora] := 70.0` (limite de 70 kW de exportação).
3. `bExportEnabled := TRUE`. Aguardar convergência (60–90 s).
4. Verificar na Watch Window:
   - `GVL_Main.ExportLimit_kW` deve ser `70.0`
   - `GVL_Main.Pt` deve convergir para ≈ `−70 kW` (exportando 70 kW)
   - `GVL_Main.P_inv_Percent_COM1[101]` deve estar próximo de 100% (120 kW necessários = 50 carga + 70 exportação ≈ capacidade total)
   - `fbPowerCtrl.bSaturated` pode ficar TRUE intermitentemente

### Critério de aprovação

- [ ] `Pt` estabiliza em `−70 ± 5 kW`
- [ ] Inversores operando próximo de 100% de capacidade
- [ ] Sem violação do limite (Pt não fica abaixo de −80 kW de forma prolongada)

---

## T3.3 — Safety Margin

### Como executar

1. Verificar que `GVL_HW.TC_Power_kW` está configurado (ex.: 120 kW para TC calibrado para a usina).
2. Verificar que `GVL_HW.SafetyMargin_pct = 3.0`.
3. Na Watch Window, verificar:
   - `fbControle.fbPowerCtrl.Margin_applied_kW` deve ser `3% × TC_Power_kW`
   - Exemplo: TC_Power = 120 kW → Margin = 3.6 kW
   - `fbControle.fbPowerCtrl.EffectiveExportLimit_kW` = `|ExportLimit| − Margin`
   - Exemplo: limite = 70 kW → EffectiveLimit = 70 − 3.6 = 66.4 kW
4. Verificar que mesmo que o PI tente comandar 70 kW de exportação, o safety margin reduz para 66.4 kW.
5. Com `TC_Power_kW = 0.0` (não configurado), verificar que margem não é aplicada (`Margin_applied_kW = 0.0`).

> **CRÍTICO:** `TC_Power_kW = 0.0` desabilita a margem de segurança silenciosamente. Verificar o log de startup para o alarme `CRIT_TC_POWER_NOT_SET` se TC não estiver configurado.

### Critério de aprovação

- [ ] `Margin_applied_kW` calculada corretamente (TC_Power_kW × SafetyMargin_pct ÷ 100)
- [ ] `EffectiveExportLimit_kW` = `|ExportLimit| − Margin` (nunca negativo)
- [ ] PI não ultrapassa o EffectiveExportLimit

---

## T3.4 — Alocação proporcional entre os três inversores

### Como executar

1. Configurar limite para que `P_cmd_kW` convirja para 90 kW:
   - Carga = 0 kW, limite = 90 kW → `bExportEnabled = TRUE`
   - O PI vai saturar o inversor em 90 kW de geração (para exportar 90 kW com carga zero)
2. Após convergência, verificar na Watch Window:

| Variável | Cálculo esperado | Valor esperado |
|---|---|---|
| `P_inv_kW_COM1[101]` | 90 × (60/120) | 45.0 kW |
| `P_inv_kW_COM2[201]` | 90 × (30/120) | 22.5 kW |
| `P_inv_kW_COM2[202]` | 90 × (30/120) | 22.5 kW |
| `P_inv_Percent_COM1[101]` | 45/60 × 100 | 75.0 % |
| `P_inv_Percent_COM2[201]` | 22.5/30 × 100 | 75.0 % |
| `P_inv_Percent_COM2[202]` | 22.5/30 × 100 | 75.0 % |
| `P_allocated_kW` | soma | 90.0 kW |

### Critério de aprovação

- [ ] Alocação proporcional à potência nominal de cada inversor (±0.5 kW)
- [ ] `P_allocated_kW = 90.0 kW` (sem saturação com capacidade disponível)
- [ ] Todos os três inversores operando no mesmo percentual da capacidade nominal

---

## T3.5 — Rampa de subida e descida

### Como executar

**Teste de rampa de subida:**
1. Configurar `bExportEnabled = FALSE`. Aguardar P_cmd = 0.
2. Configurar limite = 120 kW, carga = 0 kW.
3. Habilitar `bExportEnabled := TRUE`.
4. Monitorar `P_cmd_kW` ciclo a ciclo. Registrar valor de cada ciclo.
5. Verificar que o incremento por ciclo nunca ultrapassa `RampUp_P × CycleTime = 15 kW/s × 1s = 15 kW/ciclo`.

**Teste de rampa de descida:**
1. Com sistema gerando ≈ 100 kW, alterar limite para 0 kW abruptamente.
2. Monitorar `P_cmd_kW` ciclo a ciclo.
3. Verificar que o decremento por ciclo nunca ultrapassa `RampDown_P × CycleTime = 20 kW/ciclo`.

### Critério de aprovação

- [ ] Incremento de P_cmd ≤ 15 kW por ciclo na subida
- [ ] Decremento de P_cmd ≤ 20 kW por ciclo na descida
- [ ] Sem degrau abrupto nos setpoints dos inversores (verificar `P_inv_Percent_COM1[101]`)

---

## T3.6 — Deadband (zona morta do PI)

### Como executar

1. Com sistema em Zero Grid (limite = 0), aguardar convergência (Pt ≈ 0).
2. Aguardar até que `|Pt| < 1.2 kW` (dentro da deadband de 1% × 120 kW = 1.2 kW).
3. Monitorar `rPI_integ` por 10 ciclos com sistema dentro da deadband:
   - Deve **não mudar** — o integrador deve estar parado
   - `P_cmd_kW` deve permanecer constante
4. Aplicar perturbação pequena no simulador: `LOAD_P_KW_DEFAULT += 0.5` (variação de 0.5 kW).
   - `Pt` varia em ≈ 0.5 kW (dentro da deadband ampliada)
   - PI **não deve responder**
5. Aplicar perturbação maior: `LOAD_P_KW_DEFAULT += 3.0` (3 kW — fora da deadband de 1.2 kW).
   - PI deve responder nos próximos ciclos
   - `rPI_integ` deve começar a acumular

### Critério de aprovação

- [ ] Com `|Pt| < 1.2 kW`: `rPI_integ` estável e `P_cmd_kW` constante
- [ ] Perturbação de 0.5 kW não provoca resposta do PI
- [ ] Perturbação de 3.0 kW provoca resposta do PI

---

---

# ETAPA 4 — Controle de Fator de Potência / Reativo (Q)

**Modo simulador:** `SIM_MODE_OPENLOOP` com carga indutiva.  
**Objetivo:** Validar a cadeia Q (FFQ → PIQ → QAlloc → Smax), a direção de compensação e o comportamento quando FP não é atingível.

---

## T4.1 — Feedforward de Q (FFQ) — verificação de sinal

### Como executar

**Caso A — Carga Indutiva (Q positivo, compensação deve ser capacitiva):**
1. Configurar simulador: `LOAD_P_KW_DEFAULT := 100.0`, `LOAD_Q_KVAR_DEFAULT := 50.0`.
   - PF esperado sem compensação: cos(atan(50/100)) ≈ 0.894 (indutivo)
2. `bExportEnabled := TRUE`, limite = 0 kW. Aguardar estabilização de P.
3. Verificar na Watch Window:
   - `GVL_Main.Qt` ≈ +50 kvar (carga consumindo Q indutivo)
   - `fbControle.Q_sign` deve ser `−1.0` (compensação capacitiva)
   - `fbControle.Q_feedforward_kvar` deve ser negativo (≈ −50 kvar)
   - `GVL_Main.PF_inv_COM1[101]` deve ser negativo (FP capacitivo)

**Caso B — Carga Capacitiva (Q negativo, compensação deve ser indutiva):**
1. Configurar simulador: `LOAD_Q_KVAR_DEFAULT := −30.0` (carga gerando Q).
2. Verificar:
   - `GVL_Main.Qt` ≈ −30 kvar (carga gerando Q — situação capacitiva)
   - `fbControle.Q_sign` deve ser `+1.0` (compensação indutiva)
   - `fbControle.Q_feedforward_kvar` deve ser positivo (≈ +30 kvar)
   - `GVL_Main.PF_inv_COM1[101]` deve ser positivo (FP indutivo)

> **CRÍTICO:** Se Q_sign estiver invertido em qualquer caso, o controlador **piora o FP** ao invés de melhorar. Este é um dos bugs mais perigosos possíveis. Verificar explicitamente com ambas as polaridades de Q.

### Critério de aprovação

- [ ] Q_sign = −1.0 para carga indutiva (Qt > 0)
- [ ] Q_sign = +1.0 para carga capacitiva (Qt < 0)
- [ ] Q_feedforward tem sinal consistente com Q_sign
- [ ] FC_EncodePF produz código correto para FP capacitivo E indutivo (verificar no simulador)

---

## T4.2 — Convergência do PIQ para PF_target

### Como executar

1. Configurar: `LOAD_P_KW_DEFAULT := 100.0`, `LOAD_Q_KVAR_DEFAULT := 60.0`.
   - PF sem compensação ≈ 0.857 (abaixo do target 0.92)
2. `bExportEnabled := TRUE`, `PF_target = 0.92`. Aguardar convergência.
3. Monitorar `GVL_Main.PFt` a cada ciclo por **120 segundos**.
4. Registrar: valor inicial de PFt, valor após 30s, valor após 60s, valor estabilizado.
5. Verificar que `Q_cmd_kvar` converge para o valor necessário para atingir PF=0.92:
   - Com P=100 kW e FP=0.92: Q_necessário = P × tan(acos(0.92)) ≈ 39.4 kvar
   - Q_total = 60 (carga) − 39.4 (compensação) = 20.6 kvar residual → FP ≈ 0.98 (controlável)

### Critério de aprovação

- [ ] `GVL_Main.PFt ≥ 0.92` após convergência
- [ ] Convergência em menos de 120 segundos
- [ ] Sem oscilação de Q após convergência
- [ ] `WARN_PF_BELOW_TARGET` não persiste após convergência

---

## T4.3 — Limitação por Smax dos inversores

### Como executar

1. Configurar sistema gerando 58 kW no inversor 101 (P ≈ 97% de 60 kW):
   - Ajustar carga e limite para que `P_inv_kW_COM1[101] ≈ 58.0 kW`
2. Com Smax_COM1[101] = 66 kVA: Q_max = √(66²−58²) ≈ 29.7 kvar disponível.
3. Forçar `Q_cmd_kvar` alto o suficiente para saturar (ex.: −50 kvar):
   - Na Watch Window: `fbControle.Q_cmd_kvar := −50.0` por alguns ciclos
   - Ou: configurar carga com Q muito alto para forçar o PIQ a solicitar mais Q do que disponível
4. Verificar:
   - `GVL_Alarm.ALARM_Q_LIMITED_BY_SMAX = TRUE`
   - `GVL_Main.Q_allocated_kvar` < Q_comandado
   - `GVL_Main.PF_inv_COM1[101]` entre −1.0 e −0.80 (não inferior a 0.80)
   - Evento `WARN_Q_LIMITED_BY_SMAX` no log

### Critério de aprovação

- [ ] Saturação detectada e alarme `ALARM_Q_LIMITED_BY_SMAX` ativo
- [ ] PF do inversor clampado em ≥ 0.80 absoluto
- [ ] Evento logado com valores de Q_comandado e Q_alocado

---

## T4.4 — FP impossível de atingir (P satura Smax — sem redução de P)

### Como executar

1. Configurar todos os inversores operando em 100% (P = 120 kW):
   - Carga = 0, limite = 120 kW, bExportEnabled = TRUE
   - Aguardar inversores chegarem a ≈ 100%
2. Com Smax = 66 kVA e P = 60 kW no inversor 101: Q disponível = √(66²−60²) ≈ 26.6 kvar
3. Configurar carga com Q alto: `LOAD_Q_KVAR_DEFAULT := 100.0`
   - 100 kvar não poderá ser compensado (capacidade máxima total ≈ 3 × 26 = 78 kvar com todos a 100% de P)
4. Aguardar e verificar:
   - `GVL_Main.PFt` fica abaixo de 0.92 (FP não atingível)
   - `WARN_PF_NOT_ACHIEVABLE` ou `WARN_PF_BELOW_TARGET` no log
   - `GVL_Main.P_inv_Percent_COM1[101]` permanece em 100% (**P NÃO é reduzido**)
   - Sistema continua no ciclo normal (sem FAIL)

### Critério de aprovação

- [ ] P não é reduzido para liberar Q (prioridade 1 = P máximo, prioridade 2 = FP)
- [ ] Alarme de FP não atingível registrado no log
- [ ] Sistema continua operando normalmente (ciclo READ→CONTROL→WRITE) sem escalar para FAIL

---

---

# ETAPA 5 — Máquina de Estados e Proteções

**Modo simulador:** `SIM_MODE_OPENLOOP` (g_SimMode = 1)  
**Objetivo:** Verificar todas as transições de estado, timers normativos, watchdogs e comportamento fail-safe do controlador.

---

## T5.1 — Ciclo normal e timing

### Como executar

1. Sistema em operação normal (Openloop, bExportEnabled = TRUE).
2. Abrir Watch Window e adicionar `GVL_Main.MachineState`.
3. Monitorar por **10 ciclos consecutivos** e registrar o estado a cada segundo.
4. Verificar que os timers de timeout **não disparam**:
   - `PRG_MainProgram.tonReadTimeout.Q = FALSE`
   - `PRG_MainProgram.tonWriteTimeout.Q = FALSE`
5. Verificar `INFO_CYCLE_COMPLETE` no log a cada ciclo.
6. Medir o intervalo entre dois `INFO_CYCLE_COMPLETE` consecutivos para estimar o tempo real de ciclo.

### Critério de aprovação

- [ ] Sequência de estados IDLE→READ→CONTROL→WRITE→IDLE confirmada
- [ ] Tempo de ciclo medido entre 0.8 s e 1.5 s
- [ ] Nenhum timeout disparado em operação normal

---

## T5.2 — Timeout de leitura do medidor → FAIL

### Como executar

1. Com sistema em operação normal Openloop.
2. Desligar o simulador Windows (ou desconectar o cabo RS485 do medidor).
3. Monitorar `GVL_Main.MachineState` e `PRG_MainProgram.tonReadTimeout`.
4. Após o timeout (`tonReadTimeout.Q = TRUE`), verificar:
   - `GVL_Main.MachineState` transita para FAIL (5)
   - `GVL_Alarm.CRIT_FAIL_ENTRY = TRUE`
   - Setpoints dos inversores zerados:
     - `GVL_Main.P_inv_Percent_COM1[101] = 0.0`
     - `GVL_Main.P_inv_Percent_COM2[201] = 0.0`
     - `GVL_Main.P_inv_Percent_COM2[202] = 0.0`
5. Verificar eventos no log: `CRIT_FAIL_ENTRY` ou equivalente.
6. Confirmar que nenhum comando de P não-zero é enviado durante FAIL.

> **Verificar:** quantos erros de leitura consecutivos são necessários para ir a FAIL (parâmetro `RETRIES_READ` ou timeout direto). O sistema **não deve** ir a FAIL por apenas 1 ou 2 falhas isoladas.

### Critério de aprovação

- [ ] Após timeout de leitura: sistema transita para FAIL
- [ ] Em FAIL: todos os setpoints de P zerados confirmados
- [ ] `CRIT_FAIL_ENTRY` no log
- [ ] Nenhum comando de P não-zero enviado durante FAIL sem medição válida

---

## T5.3 — Recuperação automática de FAIL

### Como executar

1. Com sistema em FAIL (medidor desconectado — continuação do T5.2).
2. Reconectar o cabo do medidor / reiniciar o simulador.
3. Monitorar na Watch Window:
   - `GVL_Main.MachineState` (deve permanecer FAIL durante recuperação)
   - `FB_FailSafe.bMeasRecovered` — deve ficar TRUE quando medidor responde
   - `FB_FailSafe.bExportOK` — verifica se exportação está dentro do limite
   - `FB_FailSafe.uRecoveryCycles` — incrementa a cada ciclo OK consecutivo
   - `FB_FailSafe.tonRecovery.ET` — timer de 10s de estabilidade
4. Aguardar `RECOVERY_CYCLES` ciclos consecutivos OK + 10 segundos estável.
5. Verificar transição de retorno ao ciclo normal:
   - `MachineState` volta para READ (2)
   - `INFO_FAIL_RECOVERY` no log
   - Geração retoma com rampa (não degrau abrupto)

### Critério de aprovação

- [ ] Recuperação automática sem intervenção do operador
- [ ] `uRecoveryCycles` incrementa corretamente por ciclo OK consecutivo
- [ ] Retorno ao ciclo normal após critério de recuperação satisfeito
- [ ] Geração retoma com rampa de subida (RampUp_P = 15 kW/s)
- [ ] `INFO_FAIL_RECOVERY` registrado no log

---

## T5.4 — Timeout global em FAIL → STOP

### Como executar

1. Deixar sistema em FAIL com medidor desconectado (não reconectar).
2. Monitorar `FB_FailSafe.tonGlobal.ET` (timer de 120 s).
3. Após 120 segundos sem recuperação, verificar:
   - `MachineState` transita para STOP (6)
   - `GVL_Alarm.CRIT_FAIL_WRITE_EXHAUSTED` ou evento de STOP no log
4. Tentar colocar o sistema para funcionar novamente **sem apertar reset**:
   - Sistema deve **permanecer em STOP** — não sai automaticamente
5. Apertar o botão de reset (ou usar IHM) e verificar reinicialização.

> **ATENÇÃO:** Em ambiente de produção, STOP requer intervenção humana. Documentar qual botão/procedimento faz o reset.

### Critério de aprovação

- [ ] STOP ativado após 120 s em FAIL sem recuperação
- [ ] STOP não sai automaticamente — requer reset manual
- [ ] Log registra evento de escalonamento para STOP

---

## T5.5 — Estado TURNOFF (desligamento controlado)

### Como executar

1. Com sistema em operação normal (Openloop, gerando energia).
2. Acionar TurnOff via IHM ou na Watch Window: `GVL_IHM.bTurnOff := TRUE` (ou o equivalente configurado).
3. Monitorar `FB_TurnOff.eSubState` e a sequência esperada:
   - `TO_INIT` → pulso de reset de PI e setpoints
   - `TO_WRITE_ZERO` → inversores recebem P=0%
   - `TO_VERIFY` → aguarda confirmação que exportação caiu para zero
   - `TO_DISCONNECT` → K2 acionado (se aplicável)
   - `TO_DONE` → processo completo
4. Verificar durante `TO_WRITE_ZERO`:
   - `GVL_Comm.arWriteValuesCOM1[1, 0] = 0.0` (P=0% para inversor 101)
   - `GVL_Comm.arWriteValuesCOM2[1, 0] = 0.0` e `[2, 0] = 0.0`
5. Verificar que `FB_TurnOff.xK2_out = TRUE` no estado de desconexão.
6. Verificar que o sistema pode ser reiniciado normalmente após TURNOFF completo.

### Critério de aprovação

- [ ] Sequência TO_INIT → TO_WRITE_ZERO → TO_VERIFY → TO_DISCONNECT → TO_DONE completa
- [ ] Inversores recebem P=0% durante TO_WRITE_ZERO
- [ ] Log registra todos os sub-estados do TURNOFF
- [ ] Sistema reinicia normalmente após TURNOFF

---

## T5.6 — Hard Limit normativo (DIS-NOR-033)

### Como executar

1. Verificar os timers normativos configurados:
   - `PRG_MainProgram.tonStopTrip` — timer de STOP após trip
   - `FB_FailSafe.ton15s` — 15s com exportação acima do Hard Limit (110% LPI)
   - `FB_FailSafe.ton30s` — 30s com exportação acima do LPI
2. Verificar valor de `PRG_MainProgram.HardLimit_mag`:
   - Deve ser 110% do LPI configurado
3. Para simular violação de Hard Limit:
   - Configurar limite alto (ex.: 110 kW) e carga 0 kW — sistema exporta ≈ 110 kW
   - Ajustar `HardLimit_mag` manualmente para valor menor (ex.: 80 kW) na Watch Window
   - Verificar que `ton15s` começa a contar
4. Aguardar 15 segundos e verificar que sistema vai para FAIL.

### Critério de aprovação

- [ ] `tonStopTrip`, `ton15s` e `ton30s` configurados com valores corretos
- [ ] `HardLimit_mag = 110% × LPI_mag`
- [ ] Violação do hard limit por 15 s dispara FAIL

---

---

# ETAPA 6 — Injeção de Falhas

**Modo simulador:** `SIM_MODE_FULL` (g_SimMode = 2)  
**Objetivo:** Verificar o comportamento do controlador sob falhas reais de campo — perda de inversor, congelamento e sombreamento.

> **Como injetar falhas:** Modificar variáveis `g_Ev_*` na Watch Window do simulador Windows.  
> Para limpar todas as falhas: `g_Ev_DropComms[0..17] := FALSE`, `g_Ev_Freeze_s[0..17] := 0.0`, `g_Ev_Force_U[0..17] := -1.0`

**Mapeamento índice ↔ slave (topologia 3 inversores):**

| Índice no simulador | Slave ID Modbus | Porta | Potência |
|---|---|---|---|
| 0 | 101 | COM1 | 60 kW |
| 9 | 201 | COM2 | 30 kW |
| 10 | 202 | COM2 | 30 kW |

---

## T6.1 — Perda de comunicação com um inversor (drop_comms)

### Como executar

1. Modo Full, sistema em operação normal. Registrar estado inicial:
   - `GVL_Main.Pt`, `P_inv_Percent_COM1[101]`, `P_inv_Percent_COM2[201/202]`
2. Injetar falha no simulador: `g_Ev_DropComms[0] := TRUE` (slave 101 para de responder).
3. Aguardar 30 segundos e monitorar:
   - `GVL_Alarm.WARN_WRITE_INV_TIMEOUT` para slave 101
   - `GVL_Main.MachineState` — deve **permanecer no ciclo normal** (não ir a FAIL)
   - `GVL_Main.Pt` — deve desviar do setpoint (inversor 101 para de gerar no simulador)
   - `P_inv_Percent_COM2[201]` e `[202]` — PI pode aumentar setpoints tentando compensar
4. Verificar log: `WARN_WRITE_INV_TIMEOUT` com slave_id = 101.
5. Remover falha: `g_Ev_DropComms[0] := FALSE`. Verificar recuperação automática.

### Critério de aprovação

- [ ] Falha em um inversor isolado **não causa FAIL** do sistema
- [ ] `WARN_WRITE_INV_TIMEOUT` no log com slave ID 101 identificado
- [ ] PI tenta compensar nos demais inversores (setpoints de COM2 sobem)
- [ ] Recuperação automática ao restaurar comunicação

---

## T6.2 — Perda de todos os inversores

### Como executar

1. Modo Full, sistema em operação.
2. Injetar falha simultânea em todos os inversores:
   ```
   g_Ev_DropComms[0]  := TRUE  (slave 101)
   g_Ev_DropComms[9]  := TRUE  (slave 201)
   g_Ev_DropComms[10] := TRUE  (slave 202)
   ```
3. Monitorar:
   - `GVL_Main.MachineState` — deve transitar para FAIL após `RETRIES_WRITE` falhas
   - Tempo até FAIL: anotar quantos ciclos com falhas de escrita levam ao FAIL
   - Log: `CRIT_FAIL_WRITE_FAILED` ou equivalente
4. Verificar que setpoints zerados foram enviados antes da transição para FAIL.

### Critério de aprovação

- [ ] Perda total de comunicação com inversores → FAIL dentro do número configurado de retries
- [ ] Evento crítico de falha de escrita registrado no log
- [ ] Nenhum comando de P não-zero enviado após a falha total

---

## T6.3 — Congelamento de firmware de inversor (freeze_s)

### Como executar

1. Modo Full, sistema em operação. Anotar setpoint atual enviado ao slave 101 (ex.: 70%).
2. Injetar congelamento: `g_Ev_Freeze_s[0] := 20.0` (slave 101 ignora novos setpoints por 20 s).
3. Durante os 20 segundos de congelamento:
   - O simulador continua respondendo ao FC16 (sem timeout), mas ignora o valor
   - Inversor 101 permanece no setpoint congelado (ex.: 70%)
   - Se o PI mudar o setpoint para 50%, o inversor 101 continua em 70%
4. Monitorar:
   - `GVL_Main.Pt` — deve desviar do setpoint esperado (inversores "desobedecendo")
   - O controlador **não detecta** o congelamento diretamente — percebe apenas via medidor
   - `P_cmd_kW` e setpoints dos demais inversores se ajustam tentando compensar
5. Aguardar 20 s e verificar retorno ao comportamento normal.

> **Limitação arquitetural confirmada:** O controlador é cego ao estado interno dos inversores. Congelamento só é percebido via desvio no medidor. Isso é esperado e deve ser documentado.

### Critério de aprovação

- [ ] Congelamento causa desvio de Pt do setpoint (detectável no medidor)
- [ ] PI responde ao desvio tentando ajustar os demais inversores
- [ ] Sistema não vai a FAIL pelo congelamento isolado (sem perda de comunicação)
- [ ] Após 20 s: comportamento normal retorna

---

## T6.4 — Sombreamento parcial (force_u)

### Como executar

1. Modo Full, sistema em operação com todos os inversores a ≈ 70%.
2. Injetar sombreamento no inversor 101: `g_Ev_Force_U[0] := 0.3` (30% de irradiância → capacidade real ≈ 18 kW em vez de 60 kW).
3. Aguardar 60 segundos e monitorar:
   - `GVL_Main.Pt` — deve subir (menos geração, mais importação)
   - `P_cmd_kW` — PI detecta erro e aumenta o comando
   - `P_inv_Percent_COM2[201]` e `[202]` — devem subir tentando compensar
   - `GVL_Alarm.WARN_P_ALLOC_SATURATED` — deve ficar TRUE quando comando > capacidade real disponível
4. Remover sombreamento: `g_Ev_Force_U[0] := -1.0`. Verificar recuperação gradual com rampa.

### Critério de aprovação

- [ ] PI responde ao desvio de Pt causado pelo sombreamento
- [ ] Inversores COM2 sobem o percentual tentando compensar
- [ ] `WARN_P_ALLOC_SATURATED` ativo quando capacidade real é insuficiente
- [ ] Sem FAIL por sombreamento isolado
- [ ] Recuperação com rampa ao remover a falha

---

## T6.5 — Falha combinada: congelamento + perda de inversor

### Como executar

1. Modo Full, sistema em operação.
2. Injetar simultaneamente:
   ```
   g_Ev_DropComms[9]  := TRUE    (slave 201 — perda total de comunicação)
   g_Ev_Freeze_s[0]   := 30.0   (slave 101 — congelado por 30 s)
   ```
3. Monitorar por 60 segundos:
   - `WARN_WRITE_INV_TIMEOUT` para slave 201
   - `GVL_Main.Pt` — desvio significativo do setpoint
   - `P_inv_Percent_COM2[202]` — único inversor COM2 disponível deve subir
   - `WARN_P_ALLOC_SATURATED` — capacidade restante pode ser insuficiente
   - `GVL_Main.MachineState` — deve permanecer em ciclo normal (somente 1 inversor com perda total)
4. Verificar que não há oscilação instável do PI.
5. Remover falhas sequencialmente e verificar recuperação.

### Critério de aprovação

- [ ] Sistema opera degradado sem crash ou oscilação instável
- [ ] Ambos os eventos logados (`WARN_WRITE_INV_TIMEOUT` e `WARN_P_ALLOC_SATURATED`)
- [ ] `MachineState` permanece no ciclo normal (sem FAIL por 1 perda + 1 congelamento)
- [ ] Recuperação gradual ao remover as falhas

---

---

# ETAPA 7 — Cenários Integrados com Perfil Dinâmico

**Modo simulador:** `SIM_MODE_FULL` (g_SimMode = 2)  
**Objetivo:** Verificar o comportamento do sistema completo com variações dinâmicas de irradiância, carga e agenda. Esta é a etapa mais próxima das condições reais de campo.

---

## T7.1 — Perfil de irradiância variável (20 minutos)

### Como executar

1. Verificar perfil padrão do simulador (confirmar na Watch Window do simulador):
   - `U_Profile_T_s[]` = {0, 300, 600, 900, 1200}
   - `U_Profile_Val[]` = {1.0, 0.7, 0.4, 0.8, 1.0}
   - `Load_Profile_P_kW[]` = {200, 250, 180, 220, 200}
2. Configurar agenda: `WeekSchedule_kW[dia][hora] := 80.0` (limite = 80 kW).
3. `bExportEnabled := TRUE`. Iniciar perfil Full (`g_SimMode := 2`).
4. Registrar a cada 30 segundos durante 20 minutos:

| t (s) | Pt (kW) | P_cmd (kW) | P_alloc (kW) | PFt | Alarmes ativos |
|---|---|---|---|---|---|
| 0 | | | | | |
| 30 | | | | | |
| ... | | | | | |

5. Identificar os momentos críticos:
   - **t=300 s:** irradiância cai para 70%, carga sobe para 250 kW → menos geração disponível, PI deve reduzir exigência
   - **t=600 s:** nuvem (40% irradiância), carga 180 kW → geração máxima ≈ 48 kW, exportação impossível de manter; PI deve ir à saturação e `Pt` vai subir (menos exportação)
   - **t=900 s:** recuperação para 80% irradiância → PI retoma com rampa de subida

### Critérios de aprovação

- [ ] **t=0–300 s:** `Pt ≈ −80 ± 5 kW` (dentro do limite com margem)
- [ ] **t=600 s:** `Pt` desvia mas sistema **não vai a FAIL**; `WARN_P_ALLOC_SATURATED` pode estar ativo
- [ ] **Recuperação em t=900 s:** rampa de subida de 15 kW/s respeitada
- [ ] `PFt ≥ 0.92` durante toda operação normal
- [ ] Nenhuma transição para FAIL (exceto se medidor perder comunicação)
- [ ] Log coerente com eventos esperados

---

## T7.2 — Transições de agenda horária

### Como executar

1. Configurar três valores de agenda consecutivos para teste:
   - `WeekSchedule_kW[dia][hora_atual] := 90.0`
   - `WeekSchedule_kW[dia][hora_atual+1] := 50.0`
   - `WeekSchedule_kW[dia][hora_atual+2] := 0.0` (Zero Grid)
2. Operar o sistema e aguardar a virada de hora natural, **ou** avançar o RTC via `FB_SetRTC` na IHM.
3. Para avançar o RTC: usar a tela de configuração de RTC na WebVisu (ou Watch Window), setar hora = hora_atual + 1.
4. Verificar transições:
   - Quando `ExportLimit_kW` muda de 90 para 50 kW: PI deve reduzir P_cmd sem oscilação
   - Quando muda para 0 kW (Zero Grid): inversores devem ser levados a 0% via rampa
5. Verificar a transição entre 23h e 0h (boundary do array de agenda): sem crash ou valor inválido.

### Critério de aprovação

- [ ] Mudança de limite ao longo do tempo sem oscilação do PI
- [ ] Zero Grid funciona corretamente (Pt converge para 0 ± deadband)
- [ ] Transição 23h→0h sem erro de índice ou comportamento inesperado
- [ ] Log registra mudanças de setpoint do scheduler

---

## T7.3 — Degrau de carga (rejeição de carga)

### Como executar

1. Modo Full, sistema estabilizado com `Pt ≈ −70 kW` (limite = 70 kW, carga = 100 kW, geração ≈ 170 kW).
2. Aplicar degrau de carga instantâneo no simulador:
   - `LOAD_P_KW_DEFAULT := 200.0` (carga dobra de 100 para 200 kW)
3. Monitorar e registrar:
   - **Desvio máximo de Pt:** valor máximo de Pt após o degrau (deve ser < −120 kW brevemente)
   - **Tempo de resposta:** tempo até Pt retornar para −70 ± 5 kW
   - **Comportamento do PI:** rPI_erro sobe, rPI_integ começa a acumular
4. Norma DIS-NOR-033: limitação de exportação deve ocorrer em menos de 15 segundos.
   - Verificar que em menos de 15 ciclos, Pt está de volta ao limite

### Critério de aprovação

- [ ] Sistema responde ao degrau sem ir a FAIL
- [ ] Pt retorna ao setpoint em menos de 15 segundos (DIS-NOR-033)
- [ ] Sem oscilação persistente pós-degrau
- [ ] Log não registra erros críticos

---

## T7.4 — Verificação de Zero Grid com carga baixa

### Como executar

1. Configurar limite = 0 kW (Zero Grid), `bExportEnabled = TRUE`.
2. Configurar carga baixa: `LOAD_P_KW_DEFAULT := 5.0`.
3. Com carga de apenas 5 kW, o sistema deve gerar ≈ 5 kW (equilíbrio) sem exportar.
4. Verificar:
   - `GVL_Main.Pt` ≈ 0 ± deadband (≈ ±1.2 kW)
   - `P_cmd_kW ≈ 5 kW` (sistema comanda apenas o suficiente para atender a carga)
   - Inversores operam a muito baixo percentual (≈ 4% de 120 kW)
5. Reduzir carga para `LOAD_P_KW_DEFAULT := 1.0` e verificar que Pt não fica negativo de forma prolongada (sistema reduz geração para praticamente zero).

### Critério de aprovação

- [ ] Zero Grid funciona com carga mínima (sem exportação prolongada)
- [ ] `Pt ≈ 0 ± 3 kW` com carga de 5 kW
- [ ] PI reduz geração corretamente com carga muito baixa
- [ ] Sem fluxo reverso (exportação) persistente em modo Zero Grid

---

---

# Checklist Final de Encerramento dos Testes

Antes de considerar os testes concluídos e o controlador aprovado para comissionamento em campo, confirmar item a item:

## Comunicação

- [ ] Todos os slaves (100, 101, 201, 202) respondem sem timeout em operação normal
- [ ] FC_EncodePF produz código correto para FP indutivo E capacitivo no perfil do fabricante
- [ ] Nenhum slave ID conflitante no barramento RS485

## Controle ativo (P)

- [ ] PI converge em Zero Grid em menos de 60 s
- [ ] PI converge com limite não-zero em menos de 60 s
- [ ] Rampa de subida ≤ 15 kW/ciclo confirmada
- [ ] Rampa de descida ≤ 20 kW/ciclo confirmada
- [ ] Deadband funcional (PI para dentro da zona morta)
- [ ] Alocação proporcional correta entre os três inversores (±0.5 kW)
- [ ] Safety Margin aplicada corretamente

## Controle reativo (Q)

- [ ] Q_sign = −1.0 para carga indutiva confirmado
- [ ] Q_sign = +1.0 para carga capacitiva confirmado
- [ ] PFt converge para ≥ 0.92 em cenário padrão
- [ ] P não é reduzido para liberar Q (prioridade verificada)
- [ ] Saturação de Smax detectada e logada

## Proteções e máquina de estados

- [ ] Timeout de medidor → FAIL → P=0 nos inversores
- [ ] Recuperação automática de FAIL funcional (ciclos OK + 10 s)
- [ ] FAIL → STOP após 120 s sem recuperação
- [ ] STOP requer reset manual confirmado
- [ ] TURNOFF executa sequência completa corretamente
- [ ] Hard limit dispara FAIL dentro do tempo normativo

## Falhas e resiliência

- [ ] Perda de um inversor não causa FAIL do sistema
- [ ] Perda de todos os inversores causa FAIL
- [ ] Sombreamento → saturação → alarme (sem FAIL)
- [ ] Falha combinada → operação degradada (sem crash ou oscilação instável)

## Qualidade de registro

- [ ] Todos os eventos críticos registrados no log com parâmetros numéricos
- [ ] Alarmes claros com descrição via FC_EventCodeToString
- [ ] IHM/WebVisu reflete estado correto em todos os cenários

---

---

# Observações para o Comissionamento em Campo

Após aprovação completa no simulador, os seguintes pontos **requerem validação adicional com hardware real**, pois o simulador não modela estes aspectos:

**1. Latência real do barramento RS485**  
Com os três inversores e o medidor em barramentos físicos, o tempo de varredura real pode diferir do simulado. Medir o tempo efetivo de ciclo em campo e verificar se os timers de timeout (`MeterTimeout`, `tonReadTimeout`) estão adequados.

**2. Comportamento real dos inversores com FP comandado**  
O simulador aceita qualquer código de FP. O inversor real tem rampa interna, saturação de corrente e pode rejeitar comandos fora de faixa. Verificar em campo que FC_EncodePF produz valores aceitos pelo hardware para os casos extremos (FP = 0.80 capacitivo e FP = 0.80 indutivo).

**3. Desequilíbrio de fases real**  
O simulador usa modelo monofásico equivalente. FB_FLimiter com `PowerMode = 2` depende de Pa, Pb, Pc medidos por fase. Validar em campo com carga real desequilibrada que a limitação por fase funciona corretamente.

**4. Calibração do TC e safety margin**  
`TC_Power_kW` deve ser calculado para o TC real da instalação: `TC_Power_kW = √3 × V_nominal × I_TC`. A safety margin de 3% compensa o erro de classe do TC em baixas correntes. Verificar que o valor está correto para o equipamento instalado.

**5. Configuração inicial do RTC**  
Verificar que o relógio do CLP está sincronizado com o fuso horário local antes de ativar a agenda. Um erro de fuso faz o scheduler aplicar limites errados silenciosamente. Usar FB_SetRTC com a hora local confirmada.

---

*Documento gerado em março de 2026*  
*Controlador: PPC-GD v1.x — WAGO CC100 (751-9402) — Codesys V3.5 SP21 Patch 4*  
*Simulador: Windows COM1/COM2 — 1 medidor + 1 inversor 60kW (COM1) + 2 inversores 30kW (COM2)*
