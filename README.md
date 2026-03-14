**Simulador de Usina Fotovoltaica**

Guia de Instalação e Uso — Version 3

Raspberry Pi 4  ·  RS485 Waveshare HAT  ·  Modbus RTU  ·  18 inversores \+ 1 medidor

# **1  Visão Geral e Estratégia de Implantação**

O simulador opera em três modos sequenciais, selecionados por um único campo no arquivo YAML. O mesmo binário Python suporta os três modos — basta trocar o arquivo de configuração e reiniciar.

| ETAPA 1 | loopback — Teste de comunicação Modbus RTU Servidores Modbus ativos. Medidor retorna valores fixos e conhecidos. Simulação física desligada. Objetivo: validar RS485, slave IDs e endereçamento. |
| :---: | :---- |

| ETAPA 2 | openloop — Teste das rotinas de controle (cenário fixo) Simulação física ativa (Thévenin \+ ZIP \+ dinâmica 1ª ordem). Carga e irradiância fixas. Perfis CSV e eventos ignorados. Objetivo: validar controlador em ambiente estável. |
| :---: | :---- |

| ETAPA 3 | full — Teste do conjunto completo com perturbações Simulação completa: perfis CSV ativos \+ eventos injetáveis em tempo real via events.json. Objetivo: testar o controlador sob variação de irradiância, carga e falhas de inversores. |
| :---: | :---- |

# **2  Hardware e Topologia RS485**

| Item | Especificação |
| ----- | ----- |
| Plataforma | Raspberry Pi 4  (Linux ARM) |
| Interface RS485 | Waveshare RS232/RS485/CAN HAT  (2 portas independentes) |
| COM1 | /dev/ttySC0  —  slave 100 (medidor) \+ slaves 101–109 (9 inversores, 245 kW) |
| COM2 | /dev/ttySC1  —  slaves 201–209 (9 inversores, 210 kW) |
| Total instalado | 455 kW  (2×60 kW \+ 1×50 kW \+ 3×35 kW \+ 12×15 kW) |
| Papel no Modbus | Simulador \= Slave  |  Controlador externo (SCRPI) \= Master |

# **3  Estrutura do Projeto**

simulador\_v3/

├── requirements.txt

├── configs/

│   ├── config.yaml                  ← arquivo ativo (copiar do template)

│   ├── config\_etapa1\_loopback.yaml  ← template Etapa 1

│   ├── config\_etapa2\_openloop.yaml  ← template Etapa 2

│   ├── config\_etapa3\_full.yaml      ← template Etapa 3

│   └── events.json                  ← injeção de falhas (Etapa 3\)

├── profiles/

│   ├── u\_profile.csv               (time\_s, u)

│   └── load\_profile.csv            (time\_s, P\_load\_kW, Q\_load\_kVAr)

└── simulator/

    ├── \_\_init\_\_.py

    ├── main.py

    ├── config.py

    ├── modbus\_server.py

    ├── profiles.py

    └── simulation.py

# **4  Pré-requisitos e Instalação**

## **4.1  Pacotes do sistema**

sudo apt update

sudo apt install \-y python3 python3-venv python3-pip

## **4.2  Verificar portas seriais**

ls \-l /dev/ttySC\*

\# Esperado: /dev/ttySC0  e  /dev/ttySC1

**NOTA**  Se as portas não aparecerem, verifique se o HAT Waveshare está corretamente instalado e se o driver está habilitado em /boot/config.txt.

## **4.3  Permissões de acesso à porta serial**

sudo usermod \-aG dialout $USER

\# Fazer logout e login para aplicar

## **4.4  Instalar dependências Python**

cd simulador\_v3

python3 \-m venv .venv

source .venv/bin/activate

pip install \-r requirements.txt

## **4.5  Primeiro uso — copiar template de configuração**

cp configs/config\_etapa1\_loopback.yaml configs/config.yaml

# **5  Etapa 1 — Loopback: Teste de Comunicação Modbus**

## **5.1  Objetivo**

Validar toda a cadeia de comunicação antes de ligar a simulação: cabeamento RS485 (A/B/GND), servidores Modbus RTU nas duas portas, endereçamento 0x0099, leitura FC03 do medidor e escrita FC16 nos inversores.

## **5.2  Configuração**

cp configs/config\_etapa1\_loopback.yaml configs/config.yaml

## **5.3  Valores fixos esperados no medidor (slave 100\)**

No modo loopback o medidor retorna grandezas no secundário dos instrumentos. O PLC multiplica por RTP e RTC para reconstruir as grandezas primárias.

| Registrador | Grandeza | Valor sec. | Codificação | U16 esperado | PLC reconstrói |
| ----- | ----- | ----- | ----- | ----- | ----- |
| 0x0099 | PF fase A | 0,92 | val × 16384 | 15073 | PF \= 0,92 |
| 0x009A | PF fase B | 0,92 | val × 16384 | 15073 | PF \= 0,92 |
| 0x009B | PF fase C | 0,92 | val × 16384 | 15073 | PF \= 0,92 |
| 0x009C–9F | Reservado | — | — | 0 | — |
| 0x00A0 | Ia | 2,5 A | val × 256 | 640 | 2,5 × 200 \= 500 A |
| 0x00A1 | Ib | 2,5 A | val × 256 | 640 | 2,5 × 200 \= 500 A |
| 0x00A2 | Ic | 2,5 A | val × 256 | 640 | 2,5 × 200 \= 500 A |
| 0x00A3 | Reservado | — | — | 0 | — |
| 0x00A4 | Ua (fn) | 66,4 V | val × 128 | 8499 | 66,4 × 120 \= 7968 V |
| 0x00A5 | Ub (fn) | 66,4 V | val × 128 | 8499 | 66,4 × 120 \= 7968 V |
| 0x00A6 | Uc (fn) | 66,4 V | val × 128 | 8499 | 66,4 × 120 \= 7968 V |
| 0x00A7–B4 | Reservado (14 regs) | — | — | 0 | — |

**NOTA**  Todos os valores cabem em U16 (0–65535). RTP \= 120 (TP 13800/115 V). RTC \= 200 (TC 200/5 A).

## **5.4  Execução**

source .venv/bin/activate

python \-m simulator.main \--config configs/config.yaml

Log esperado ao iniciar:

\=== ETAPA 1: LOOPBACK — teste de comunicação Modbus \===

  Medidor: PF=0.92, V\_sec=66.40 V, I\_sec=2.500 A (fixos)

  Inversores: aceitam FC16, logam setpoints recebidos

  Simulação física: DESLIGADA

## **5.5  Checklist da Etapa 1**

### **Teste 1 — Leitura do medidor (COM1, slave 100\)**

* PLC lê slave 100, start 0x0099, qty 28 — sem timeout

* PF em 0x0099–0x009B \= 15073

* Correntes em 0x00A0–0x00A2 \= 640

* Tensões em 0x00A4–0x00A6 \= 8499

* Registradores reservados (3–6, 10, 14–27) \= 0

### **Teste 2 — Escrita nos inversores COM1**

* FC16 slave 101, HR 256 \= 50 → log: LOOPBACK RX: inv 101 → setpoint P \= 50.0 %

* FC16 slave 101, HR 257 \= 95 → log: LOOPBACK RX: inv 101 → PF raw \= 95

* Repetir para slave 109 (último de COM1)

### **Teste 3 — Escrita nos inversores COM2**

* FC16 slave 201, HR 256 \= 100 → log confirma recepção

* Repetir para slave 209 (último de COM2)

### **Teste 4 — Slave ID inválido**

* Leitura de slave 150 → timeout (esperado)

**Critério de aprovação: todos os testes acima sem erros de comunicação.**

## **5.6  Problemas comuns na Etapa 1**

| Sintoma | Causa provável | Solução |
| ----- | ----- | ----- |
| Timeout em todos os slaves | Cabo RS485 desconectado ou A/B trocados | Verificar fiação e polaridade |
| Timeout só em COM2 | Porta /dev/ttySC1 incorreta | Conferir ls \-l /dev/ttySC\* |
| PF/I/V com valores errados | Offset ±1 no endereço (0-based vs 1-based) | Verificar driver do PLC |
| Permission denied | Usuário sem grupo dialout | sudo usermod \-aG dialout $USER |
| V ou I fora do esperado | RTP/RTC no YAML diferente do PLC | Conferir relações de transformação |

# **6  Etapa 2 — Openloop: Teste das Rotinas de Controle**

## **6.1  Objetivo**

Validar que o controlador calcula e distribui setpoints corretamente em um cenário estável: carga e irradiância fixas, sem perturbações. A simulação física está ativa (Thévenin, ZIP, dinâmica de 1ª ordem); perfis CSV e eventos são ignorados.

## **6.2  Pré-requisito**

Etapa 1 aprovada — comunicação Modbus funcionando nas duas portas.

## **6.3  Configuração**

cp configs/config\_etapa2\_openloop.yaml configs/config.yaml

Parâmetros-chave do cenário fixo (ajustar conforme necessidade):

| Parâmetro YAML | Valor padrão | Descrição |
| ----- | ----- | ----- |
| u\_default | 1,0 | Irradiância 100% — disponibilidade máxima |
| load\_p\_kw | 200,0 kW | Carga ativa fixa |
| load\_q\_kvar | 50,0 kVAr | Carga reativa fixa |
| tau\_p\_s | 1,0 s | Constante de tempo da potência ativa (por inversor) |
| tau\_q\_s | 1,0 s | Constante de tempo da potência reativa (por inversor) |

**NOTA**  Cenário de referência: com todos os inversores a 100%, P\_gen \= 455 kW \> P\_carga \= 200 kW → P\_PCC ≈ −255 kW (exportação). Tensão no PCC sobe acima de 380 V.

## **6.4  Execução**

source .venv/bin/activate

python \-m simulator.main \--config configs/config.yaml

Log esperado ao iniciar:

\=== ETAPA 2: OPENLOOP — teste do controlador (cenário fixo) \===

  tick=10 ms, inversores=18

  Carga fixa: P=200 kW, Q=50 kVAr

  Irradiância fixa: u=1.00

  Thévenin R=0.00283 X=0.01416 ohm

  Perfis CSV: IGNORADOS  |  Eventos: IGNORADOS

## **6.5  Checklist da Etapa 2**

### **Teste 1 — Medidor em repouso (inversores a 0%)**

* P\_PCC ≈ \+200 kW (importação), Q\_PCC ≈ \+50 kVAr

* Tensão no PCC ligeiramente abaixo de 380 V (queda Thévenin)

* Corrente e FP no medidor coerentes com a carga configurada

### **Teste 2 — Resposta a setpoints**

* Controlador comanda inversores a 44% → P\_PCC ≈ 0 (injeção zero), tensão ≈ 380 V

* Controlador comanda inversores a 100% → P\_PCC ≈ −255 kW, tensão sobe

* FP no medidor muda de sinal conforme a geração supera a carga

### **Teste 3 — Dinâmica dos inversores**

* Degrau 0% → 100%: potência sobe gradualmente em \~5τ \= 5 s (99% do valor final)

* Degrau 100% → 0%: potência desce gradualmente com mesma constante de tempo

### **Teste 4 — Controle de FP**

* Comando PF raw \= 95 (leading): inversores injetam reativos, Q\_PCC diminui

* Comando PF raw \= 5 (lagging): inversores consomem reativos, Q\_PCC aumenta

### **Teste 5 — Convergência em malha fechada**

* Ciclo completo: ler medidor → calcular → escrever setpoints

* Exportação converge para o limite configurado no controlador

* FP no PCC converge para a meta, sem oscilações

**Critério de aprovação: controlador converge em cenário estável sem oscilações.**

# **7  Etapa 3 — Full: Teste do Conjunto Completo**

## **7.1  Objetivo**

Testar o controlador sob condições dinâmicas: variação de irradiância, mudança de carga, falha de inversores, sombreamento parcial e travamento de firmware.

## **7.2  Pré-requisito**

Etapas 1 e 2 aprovadas.

## **7.3  Configuração**

cp configs/config\_etapa3\_full.yaml configs/config.yaml

## **7.4  O que muda em relação à Etapa 2**

* Perfis CSV ativos: u\_profile.csv e load\_profile.csv (piecewise-constant)

* events.json relido automaticamente a cada events\_poll\_s segundos (padrão: 2 s)

## **7.5  Injeção de eventos em tempo real**

Edite configs/events.json com qualquer editor de texto enquanto o simulador está rodando. A mudança é detectada automaticamente na próxima leitura.

| Campo | Tipo | Efeito | Restaurar |
| ----- | ----- | ----- | ----- |
| drop\_comms | lista de IDs | Inversor rampa P a zero em 5 s e para de aceitar setpoints | \[\] |
| freeze\_s | { ID: segundos } | P e Q ficam constantes, ignora setpoints (travamento) | {} |
| force\_u | { ID: 0.0..1.0 } | Sobrescreve irradiância daquele inversor (sombreamento) | {} |

### **Cenários de teste prontos**

T1 — Perda de inversor grande (60 kW):

{"drop\_comms": \[101\], "freeze\_s": {}, "force\_u": {}}

T2 — Nuvem passageira em toda a COM1:

{"drop\_comms": \[\], "freeze\_s": {},

 "force\_u": {"101":0.3,"102":0.3,"103":0.3,"104":0.3,

             "105":0.3,"106":0.3,"107":0.3,"108":0.3,"109":0.3}}

T3 — Travamento \+ perda de comunicação combinados:

{"drop\_comms": \[207\], "freeze\_s": {"103": 20.0, "208": 15.0}, "force\_u": {}}

T4 — Retorno à operação normal:

{"drop\_comms": \[\], "freeze\_s": {}, "force\_u": {}}

## **7.6  Checklist da Etapa 3**

### **Teste 1 — Perfil de irradiância**

* Com u\_profile.csv ativo, potência máxima varia conforme o perfil

* Quando u cai (nuvem), inversores saturam e controlador redistribui

### **Teste 2 — Perfil de carga**

* P\_PCC e Q\_PCC variam conforme load\_profile.csv

* Controlador acompanha sem overshoots excessivos

### **Teste 3 — Perda de comunicação (T1)**

* Inversor 101 rampa a zero em \~5 s

* Controlador redistribui para os demais inversores

* Restaurar → inversor 101 volta a aceitar setpoints

### **Teste 4 — Sombreamento parcial (T2)**

* Inversores 101–109 limitados a 30% da nominal

* Controlador redistribui para inversores da COM2

### **Teste 5 — Travamento de firmware (T3)**

* Inversor 103 congela por 20 s (P e Q constantes)

* Controlador mantém estabilidade durante o congelamento

### **Teste 6 — Cenário combinado (stress test)**

* Nuvem em COM1 \+ perda de inversor 207 \+ carga variável

* Controlador mantém exportação dentro dos limites

* FP no PCC permanece dentro da faixa aceitável

### **Teste 7 — Retorno à normalidade (T4)**

* events.json zerado → sistema converge de volta ao regime estável

# **8  Referência Rápida Modbus RTU**

## **8.1  Medidor — slave 100 (FC03)**

| Parâmetro | Valor |
| ----- | ----- |
| Função | FC03 (Read Holding Registers) |
| Start address | 0x0099 (decimal 153\) |
| Quantidade | 28 registradores U16 |
| Grandezas | Secundário TP/TC — PLC multiplica por RTP/RTC |
| FP com sinal | Positivo \= indutivo (Q \> 0\)  |  Negativo \= capacitivo (Q \< 0\) |

## **8.2  Inversores — slaves 101–109, 201–209 (FC16)**

| Registrador | Conteúdo | Faixa | Observação |
| ----- | ----- | ----- | ----- |
| HR 256 | Setpoint %P | 0 – 100 | Percentual da potência nominal |
| HR 257 | FP raw | 1–20 lagging | 80–100 leading | 100 \= unitário | 21–79 inválido → tratado como 100 |

### **Decodificação do FP raw**

| Faixa raw | Tipo | Cálculo do FP | Efeito em Q |
| ----- | ----- | ----- | ----- |
| 1 – 20 | Lagging (indutivo) | PF \= 1,00 − raw × 0,01 | Q \< 0  (consome reativo) |
| 80 – 99 | Leading (capacitivo) | PF \= raw / 100 | Q \> 0  (injeta reativo) |
| 100 | Unitário | PF \= 1,00 | Q \= 0 |
| 21 – 79 | Inválido | Tratado como 100 | Q \= 0 |

# **9  Troubleshooting**

## **9.1  Problemas de comunicação (Etapa 1\)**

| Sintoma | Causa | Solução |
| ----- | ----- | ----- |
| Timeout geral | Cabo RS485, A/B, GND ou baudrate | Verificar fiação e parâmetros |
| Permission denied | Usuário fora do grupo dialout | sudo usermod \-aG dialout $USER |
| Device busy | Outra instância usando a porta | sudo lsof /dev/ttySC0 |
| Valores deslocados ±1 | Offset 0-based vs 1-based no PLC | Ajustar endereço no driver do PLC |

## **9.2  Problemas de controle (Etapa 2\)**

| Sintoma | Causa | Solução |
| ----- | ----- | ----- |
| Medidor sempre em zero | mode: loopback ainda ativo | Verificar mode: openloop no YAML |
| Inversores não respondem | FC16 no endereço errado | Confirmar HR 256 e HR 257 |
| Controlador oscila | τ muito pequeno | Aumentar tau\_p\_s e tau\_q\_s no YAML |
| Exportação não converge | Lógica do PLC ou limites de setpoints | Revisar algoritmo de controle |

## **9.3  Problemas de simulação (Etapa 3\)**

| Sintoma | Causa | Solução |
| ----- | ----- | ----- |
| Overrun warnings frequentes | CPU sobrecarregada | Aumentar tick\_s para 0,02 ou 0,05 |
| Eventos sem efeito | JSON inválido | python3 \-m json.tool configs/events.json |
| Tensão estranha no medidor | RTP/RTC incorretos | Verificar relações de transformação |
| Inversores ignoram setpoints | mode: loopback ou openloop | Verificar mode: full no YAML |

# **10  Sequência de Operação Típica**

| Passo | Ação | Critério de avanço |
| ----- | ----- | ----- |
| 1 | Etapa 1 (loopback): validar comunicação RS485 | Checklist da seção 5.5 sem erros |
| 2 | cp config\_etapa2\_openloop.yaml config.yaml \+ reiniciar | — |
| 3 | Etapa 2 (openloop): validar rotinas de controle | Controlador converge sem oscilações (seção 6.5) |
| 4 | cp config\_etapa3\_full.yaml config.yaml \+ reiniciar | — |
| 5 | Etapa 3 (full): testar com perturbações | Todos os testes da seção 7.6 passam |
| 6 | Durante Etapa 3: injetar falhas via events.json | Sistema responde conforme esperado |
| 7 | Restaurar events.json (T4) e observar convergência | Regime estável restaurado |

*Simulador de Usina FV — Version 3  ·  Gerado em 2026-03-12*

# Descrição da instalação e funcionamento do simulador

# Impacto do tick_s na simulação — Windows vs RPi

O Euler explícito discretiza assim:

```
p_kw(k+1) = p_kw(k) + α × (p_ref − p_kw(k))
onde α = tick_s / τ_p
```

Com `τ = 1,0 s`:

- `tick=10 ms` → α = 0,01 → curva suave, 20 amostras por constante de tempo
- `tick=50 ms` → α = 0,05 → curva ainda suave, 20 amostras por constante de tempo

São exatamente 20 amostras por τ nos dois casos porque o controlador do SCRPI cicla a cada 2 s (`control_cycle_s`). O que importa para ele é o valor que lê no medidor — e esse valor converge corretamente nos dois casos.

O erro de Euler numa primeira ordem é proporcional a `α²`. Passando de 10 ms para 50 ms o erro sobe 25×, mas parte de um valor ínfimo:

- `tick=10 ms`: erro de regime ~0,005% por passo
- `tick=50 ms`: erro de regime ~0,125% por passo → ainda invisível para o controlador

## Único risco real: τ pequeno no futuro

Se você quiser testar inversores rápidos com `τ_p = 0,2 s`, com `tick=50 ms` teria `α = 0,25` — a resposta começa a parecer um degrau em vez de uma exponencial. A regra de estabilidade do Euler exige `α < 1,0` (ou seja, `tick < τ`), então tecnicamente não instabiliza, mas a fidelidade cai.

Solução para esse caso — duas linhas no topo de `main.py`:

```python
import sys, ctypes
if sys.platform == "win32":
    ctypes.windll.winmm.timeBeginPeriod(1)  # força timer Windows para 1 ms
```

Com isso `tick_s: 0.02` funciona de forma confiável no Windows para qualquer `τ ≥ 0,1 s`.

## Recomendação objetiva

| Situação | tick recomendado |
|---|---|
| Configuração atual (τ = 1,0 s) | 50 ms — sem nenhum impacto |
| Se quiser τ ≥ 0,5 s no futuro | 50 ms — ainda OK |
| Se quiser τ < 0,5 s | 20 ms + `timeBeginPeriod(1)` |
| Máxima fidelidade (idêntico ao RPi) | 10 ms + `timeBeginPeriod(1)` |

Para os cenários de teste atuais — loopback, openloop e full com os 18 inversores em τ = 1,0 s — **50 ms é matematicamente equivalente ao tick de 10 ms do RPi** do ponto de vista do controlador SCRPI.

## O que muda no YAML — Linux para Windows

Apenas 3 campos. Todo o resto é idêntico.

| Campo | Linux (RPi) | Windows |
|---|---|---|
| `simulation.tick_s` | `0.01` | `0.05` |
| `com1.serial.device` | `/dev/ttySC0` | `COM7` |
| `com2.serial.device` | `/dev/ttySC1` | `COM6` |

> Os números de porta COM podem variar. Confirme os valores corretos em **Gerenciador de Dispositivos → Portas (COM e LPT)** após conectar os conversores USB-485.

Exemplo — somente os blocos alterados:

```yaml
simulation:
  tick_s: 0.05           # era 0.01 — mínimo seguro no Windows

com1:
  serial:
    device: "COM7"       # era /dev/ttySC0

com2:
  serial:
    device: "COM6"       # era /dev/ttySC1
```

Inversores, medidor, parâmetros físicos (Thévenin, ZIP), perfis CSV e eventos — **copiados sem alteração** do config Linux.
