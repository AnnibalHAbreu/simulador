// Mudar de:

// {\#define DEBUG\_MODE}

// Para:

{\#define DEBUG\_MODE}

\`\`\`

Com isso, na transição do estado START o sistema \*\*pula direto para CONTROL\*\*, ignorando completamente stCheck\_COM, stCheck\_Medidor, stCheck\_Inversores, stWait\_K1 e stWait\_K2. O simulador já responde em Loopback, então READ e WRITE funcionam normalmente.

\*\*Usar para:\*\* etapas E1 a E7 completas.  

\*\*Não usar para:\*\* testar o startup em si (o objetivo das próximas etapas abaixo).

\---

\#\#\# Opção B — Forçar estados via Watch Window (sem recompilar)

Para testar \*\*cada sub-estado do startup individualmente\*\*, sem modificar código e sem hardware real, use a Watch Window para injetar as condições que cada estado espera:

| Sub-estado | O que ele espera | O que forçar na Watch Window |

|---|---|---|

| \`stCheck\_COM\` | \`xMaster01IsReady \= TRUE\` e \`xMaster02IsReady \= TRUE\` | Essas variáveis são internas do FB. O driver Modbus RTU deve estar em RUNNING. Se o driver sobe normalmente (COM configurada, mesmo sem dispositivo), avança sozinho. |

| \`stCheck\_Medidor\` | ACK Modbus do slave 100 dentro de 10 s | Ligar simulador em \*\*Loopback\*\* antes de ligar o CLP. O slave 100 responde ao FC03. |

| \`stCheck\_Inversores\` | \`CheckThreshold\` % dos inversores configurados respondem | Ligar simulador em \*\*Loopback\*\* (slaves 101, 201, 202 respondem). |

| \`stWait\_K1\` | \`K1\_in \= TRUE\` por 500 ms | \`GVL\_Main.K1\_in := TRUE\` na Watch Window. |

| \`stWait\_K2\` | \`K2\_in \= TRUE\` por 500 ms | \`GVL\_Main.K2\_in := TRUE\` na Watch Window. |

\---

\#\# Roteiro de teste do startup passo a passo

\#\#\# Pré-condição: simulador em modo \*\*Loopback\*\* rodando antes de ligar o CLP

\---

\#\#\# TS0.1 — stInit (calculado automaticamente)

\*\*O que testa:\*\* RTC, cálculo de InstalledPower, inicialização dos arrays.

\*\*Como executar:\*\*

1\. Compilar com \`DEBUG\_MODE\` comentado (produção normal).

2\. Ligar o CLP.

3\. Watch Window: monitorar \`fbStart.stState\`.

4\. Verificar que \`stState\` avança de \`stInit\` para \`stCheck\_COM\` em menos de 1 ciclo.

5\. Verificar na Watch Window:

   \- \`GVL\_Main.timestampUTC\` — deve ser não-zero (RTC lido)

   \- \`GVL\_Alarm.CRIT\_RTC\_FAIL \= FALSE\`

   \- \`GVL\_Main.InstalledPower \= 120.0\` (se parâmetros do T0.1 estiverem corretos)

   \- \`fbStart.bSoftInitDone \= TRUE\`

\*\*Critério:\*\* \`stState\` avança para \`stCheck\_COM\`, sem \`CRIT\_RTC\_FAIL\`, \`InstalledPower \= 120.0\`.

\---

\#\#\# TS0.2 — stCheck\_COM (driver Modbus RTU)

\*\*O que testa:\*\* Se os drivers seriais COM1 e COM2 subiram corretamente.

\*\*Como executar:\*\*

1\. O driver sobe automaticamente se as portas COM estão configuradas no projeto Codesys. Não depende de hardware externo.

2\. Watch Window: monitorar \`fbStart.xMaster01IsReady\` e \`fbStart.xMaster02IsReady\`.

3\. Se o CLP não tiver as portas COM fisicamente conectadas mas o driver estiver configurado, o driver pode não subir. Nesse caso:

   \- Verificar se \`TonComTimeout.ET\` está contando (timeout de 10 s)

   \- Se timeout estourar: \`CRIT\_SERIAL\_INIT\_FAILED\` no log → \`stError\`

\*\*Critério:\*\* Ambos \`xMaster01IsReady \= TRUE\` e \`xMaster02IsReady \= TRUE\` dentro de 10 s. \`INFO\_SERIAL\_COM\_OK\` no log.

\---

\#\#\# TS0.3 — stCheck\_Medidor (com simulador Loopback)

\*\*O que testa:\*\* Se o medidor (slave 100\) responde ao FC03 dentro do timeout de 10 s.

\*\*Como executar:\*\*

1\. \*\*Simulador deve estar em Loopback e rodando antes deste passo.\*\*

2\. Watch Window: monitorar \`fbStart.TonMedTimeout.ET\` (conta até 10 s).

3\. Se o slave 100 responder: \`stState\` avança para \`stCheck\_Inversores\`.

4\. Se não responder (timeout): \`CRIT\_MEAS\_INIC\_ERRO\_TIMEOUT\` ou \`CRIT\_MEAS\_INIC\_FAIL\` no log → \`stError\`.

\*\*Para testar o caminho de falha propositalmente:\*\*

\- Desligar o simulador durante este estado

\- Verificar que o evento crítico correto é gerado no log após 10 s

\- Verificar que \`stState \= stError\` e \`MachineState \= ERRO\`

\*\*Critério:\*\* Com simulador Loopback ativo, \`stState\` avança para \`stCheck\_Inversores\` sem timeout.

\---

\#\#\# TS0.4 — stCheck\_Inversores (com simulador Loopback)

\*\*O que testa:\*\* Varredura de presença dos inversores configurados. Verifica se pelo menos \`CheckThreshold\`% respondem.

\*\*Como executar:\*\*

1\. Com simulador Loopback (slaves 101, 201, 202 respondendo).

2\. Watch Window:

   \- \`GVL\_Comm.abInvOnline\_COM1\[101\]\` — deve ficar \`TRUE\`

   \- \`GVL\_Comm.abInvOnline\_COM2\[201\]\` — deve ficar \`TRUE\`

   \- \`GVL\_Comm.abInvOnline\_COM2\[202\]\` — deve ficar \`TRUE\`

   \- \`fbCheckInv.uRespondedTotal\` — deve ser \`3\`

   \- \`fbCheckInv.uConfiguredTotal\` — deve ser \`3\`

3\. Com todos respondendo: \`stState\` avança para \`stWait\_K1\`.

\*\*Para testar o limiar \`CheckThreshold\`:\*\*

\- Desligar um slave no simulador (ex.: \`g\_Ev\_DropComms\[0\] := TRUE\` — slave 101\)

\- Com 2 de 3 respondendo (66%): dependendo do \`CheckThreshold\` configurado, pode passar ou falhar

\- Verificar \`WARN\_INV\_STARTUP\_FAIL\` para o slave que não respondeu

\*\*Critério:\*\* 3/3 inversores online → \`stState \= stWait\_K1\`. Log registra \`INFO\_INV\_CHECK\_OK\`.

\---

\#\#\# TS0.5 — stWait\_K1 (forçar via Watch Window)

\*\*O que testa:\*\* Se K1 (permissivo/disjuntor de geração) é confirmado com debounce de 500 ms.

\*\*Como executar:\*\*

1\. Quando \`stState \= stWait\_K1\`, o startup aguarda \`K1\_in \= TRUE\` por 500 ms consecutivos.

2\. \*\*Forçar na Watch Window:\*\* \`GVL\_Main.K1\_in := TRUE\`

3\. Monitorar \`fbStart.TonDebounceK1.ET\` contando até 500 ms.

4\. Após 500 ms estável: \`INFO\_K1\_CONFIRMED\` no log, \`stState\` avança para \`stWait\_K2\`.

5\. \*\*Testar timeout:\*\* manter \`K1\_in \= FALSE\` e aguardar \`TonK1Timeout\` (5 s) → \`CRIT\_K1\_TIMEOUT\` → \`stError\`.

6\. \*\*Testar intermitência:\*\* alternar \`K1\_in\` entre TRUE e FALSE antes dos 500 ms → debounce deve resetar.

\*\*Critério:\*\* \`K1\_in \= TRUE\` por ≥ 500 ms → \`INFO\_K1\_CONFIRMED\` no log → \`stState \= stWait\_K2\`.

\---

\#\#\# TS0.6 — stWait\_K2 (forçar via Watch Window)

\*\*O que testa:\*\* Se K2 (trip/religador) está confirmado aberto (condição de segurança inicial).

\*\*Como executar:\*\*

1\. Quando \`stState \= stWait\_K2\`:

2\. \*\*Forçar na Watch Window:\*\* \`GVL\_Main.K2\_in := TRUE\`

3\. Monitorar \`fbStart.TonDebounceK2.ET\` contando até 500 ms.

4\. Após 500 ms: \`INFO\_K2\_CONFIRMED\` → \`stState \= stDone\` → \`MachineState \= READ\`.

5\. \*\*Testar timeout:\*\* manter \`K2\_in \= FALSE\` → \`CRIT\_K2\_TIMEOUT\` após 5 s → \`stError\`.

\*\*Critério:\*\* \`K2\_in \= TRUE\` por ≥ 500 ms → \`INFO\_K2\_CONFIRMED\` → \`stState \= stDone\` → \`MachineState \= READ\`.

\---

\#\#\# TS0.7 — Startup completo de ponta a ponta

\*\*Como executar:\*\*

1\. Simulador em Loopback rodando.

2\. CLP power cycle (reiniciar do zero).

3\. Quando \`stState \= stWait\_K1\`: forçar \`K1\_in := TRUE\` na Watch Window.

4\. Quando \`stState \= stWait\_K2\`: forçar \`K2\_in := TRUE\` na Watch Window.

5\. Verificar que \`MachineState\` chega a READ e depois ao ciclo normal.

\*\*Sequência esperada de eventos no log:\*\*

\`\`\`

INFO\_STARTUP\_BEGIN

INFO\_RTC\_OK

INFO\_INSTALLED\_POWER       (rParam1 \= 120.0)

INFO\_SERIAL\_COM\_OK

INFO\_INVERTER\_COUNT        (uRespondedTotal \= 3\)

INFO\_INV\_CHECK\_OK

INFO\_K1\_CONFIRMED

INFO\_K2\_CONFIRMED

INFO\_STARTUP\_DONE

INFO\_CYCLE\_COMPLETE        (primeiro ciclo de controle)

