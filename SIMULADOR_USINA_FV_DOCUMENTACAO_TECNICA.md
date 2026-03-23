# Simulador de Usina Fotovoltaica — Documentação Técnica Consolidada

**Projeto:** Simulador de Usina FV com 18 inversores + 1 medidor  
**Plataformas:** Raspberry Pi 4 / Windows / Codesys (WAGO CC100)  
**Protocolo:** Modbus RTU RS485  
**Data:** Março de 2026  

---

## Índice

1. [Visão geral do projeto](#1-visão-geral-do-projeto)
2. [Arquitetura e topologia de hardware](#2-arquitetura-e-topologia-de-hardware)
3. [Estratégia de implantação em três etapas](#3-estratégia-de-implantação-em-três-etapas)
4. [Modelos físicos implementados](#4-modelos-físicos-implementados)
   - 4.1 [Equivalente de Thévenin](#41-equivalente-de-thévenin)
   - 4.2 [Modelo de carga ZIP](#42-modelo-de-carga-zip)
   - 4.3 [Dinâmica de 1ª ordem dos inversores](#43-dinâmica-de-1ª-ordem-dos-inversores)
   - 4.4 [Codificação Modbus dos registradores do medidor](#44-codificação-modbus-dos-registradores-do-medidor)
5. [Estrutura do código Python](#5-estrutura-do-código-python)
6. [Porte para Codesys (Structured Text)](#6-porte-para-codesys-structured-text)
   - 6.1 [Cenário com 4 portas RS485](#61-cenário-com-4-portas-rs485)
   - 6.2 [Matriz de migração Python → ST](#62-matriz-de-migração-python--st)
   - 6.3 [Arquivos ST gerados](#63-arquivos-st-gerados)
   - 6.4 [Configuração da task e mapeamento Modbus](#64-configuração-da-task-e-mapeamento-modbus)
7. [Eventos de falha injetáveis](#7-eventos-de-falha-injetáveis)
   - 7.1 [Perda de comunicação (drop_comms)](#71-perda-de-comunicação-drop_comms)
   - 7.2 [Congelamento de firmware (freeze_s)](#72-congelamento-de-firmware-freeze_s)
   - 7.3 [Sombreamento parcial (force_u)](#73-sombreamento-parcial-force_u)
8. [Fluxo de operação do código](#8-fluxo-de-operação-do-código)
9. [Origem e cálculo dos parâmetros de Thévenin](#9-origem-e-cálculo-dos-parâmetros-de-thévenin)
10. [Derivação da equação de queda de tensão](#10-derivação-da-equação-de-queda-de-tensão)
11. [Validação do simulador](#11-validação-do-simulador)
    - 11.1 [Camada 1 — Validação analítica](#111-camada-1--validação-analítica)
    - 11.2 [Camada 2 — Cenários com critério numérico](#112-camada-2--cenários-com-critério-numérico)
    - 11.3 [Camada 3 — Validação cruzada Python × Codesys ST](#113-camada-3--validação-cruzada-python--codesys-st)
    - 11.4 [Camada 4 — Limites honestos do simulador](#114-camada-4--limites-honestos-do-simulador)
12. [OpenDSS — o que adiciona ao estudo](#12-opendss--o-que-adiciona-ao-estudo)
    - 12.1 [Comparativo Thévenin × OpenDSS](#121-comparativo-thévenin--opendss)
    - 12.2 [Os três cenários onde o OpenDSS muda o resultado](#122-os-três-cenários-onde-o-opendss-muda-o-resultado)
    - 12.3 [O que o OpenDSS não substitui](#123-o-que-o-opendss-não-substitui)

---

## 1. Visão geral do projeto

O simulador reproduz o comportamento elétrico de uma usina fotovoltaica de 455 kW conectada em baixa tensão (380 V) com ponto de medição em média tensão (13,8 kV), para fins de teste laboratorial do controlador de exportação SCRPI.

O simulador atua como **escravo Modbus RTU**, respondendo às mesmas mensagens que os equipamentos reais responderiam. O controlador externo (SCRPI / WAGO CC100) opera como **mestre**, sem saber que está falando com um simulador.

**Premissa fundamental:** o simulador não precisa ser um gêmeo digital de alta fidelidade. Ele precisa ser simples, determinístico e suficiente para exercitar todas as funções do controlador.

**Potência instalada total:** 455 kW

| Porta | Slaves | Equipamentos | Potência |
|-------|--------|-------------|---------|
| COM1 | 100 | Medidor (slave único) | — |
| COM1 | 101–109 | 9 inversores | 245 kW |
| COM2 | 201–209 | 9 inversores | 210 kW |

Composição dos inversores:

| Quantidade | Potência unitária | Localização |
|-----------|------------------|-------------|
| 2 | 60 kW | COM1 (slaves 101, 102) |
| 1 | 50 kW | COM2 (slave 209) |
| 3 | 35 kW | COM1 (slave 103) + COM2 (slaves 207, 208) |
| 12 | 15 kW | COM1 (slaves 104–109) + COM2 (slaves 201–206) |

---

## 2. Arquitetura e topologia de hardware

```
┌─────────────────────────────────────────────────────────────┐
│  Controlador externo (SCRPI / WAGO CC100)                    │
│  Papel: Modbus RTU MASTER                                    │
│  ► Lê medidor (FC03, slave 100)                             │
│  ► Escreve setpoints nos inversores (FC16, slaves 101–209)  │
└────────────────┬────────────────────────────────────────────┘
                 │ RS485 (2 barramentos independentes)
     ┌───────────┴──────────────┐
     │                          │
  COM1 (/dev/ttySC0)        COM2 (/dev/ttySC1)
  slave 100  — medidor       slaves 201–209 — inversores
  slaves 101–109 — inversores
     │                          │
     └──────────────┬───────────┘
                    │
┌───────────────────▼─────────────────────────────────────────┐
│  Simulador (Raspberry Pi 4 / Windows / Codesys)              │
│  Papel: Modbus RTU SLAVE                                     │
│  ► Responde FC03 com grandezas do medidor (MW_Meter[0..27]) │
│  ► Aceita FC16 com setpoints dos inversores (HR256, HR257)  │
│  ► Executa física: Thévenin + ZIP + dinâmica 1ª ordem       │
└─────────────────────────────────────────────────────────────┘
```

**Parâmetros da comunicação serial:**

| Parâmetro | Valor |
|-----------|-------|
| Baudrate | 9600 bps |
| Paridade | N (nenhuma) |
| Stop bits | 1 |
| Byte size | 8 bits |
| Timeout | 0,2 s |

---

## 3. Estratégia de implantação em três etapas

O simulador opera em três modos sequenciais, selecionados por um único campo no arquivo de configuração (`mode`). O mesmo código suporta os três modos.

### Etapa 1 — Loopback (`mode: "loopback"`)

**Objetivo:** validar toda a cadeia de comunicação RS485 antes de ligar a física.

**Comportamento:**
- Medidor (slave 100): responde FC03 com valores **fixos e conhecidos**
- Inversores (slaves 101–109, 201–209): aceitam FC16 e **registram os setpoints recebidos**
- Simulação física: **desligada**

**Valores fixos esperados nos registradores do medidor:**

| Registrador | Grandeza | Valor sec. | Codificação | U16 esperado |
|-------------|---------|-----------|-------------|-------------|
| 0x0099 | PF fase A | 0,92 | val × 16384 | 15073 |
| 0x009A | PF fase B | 0,92 | val × 16384 | 15073 |
| 0x009B | PF fase C | 0,92 | val × 16384 | 15073 |
| 0x00A0 | Ia | 2,5 A | val × 256 | 640 |
| 0x00A1 | Ib | 2,5 A | val × 256 | 640 |
| 0x00A2 | Ic | 2,5 A | val × 256 | 640 |
| 0x00A4 | Ua (fn) | 66,4 V | val × 128 | 8499 |
| 0x00A5 | Ub (fn) | 66,4 V | val × 128 | 8499 |
| 0x00A6 | Uc (fn) | 66,4 V | val × 128 | 8499 |

**Critério de aprovação:** todos os slaves respondem sem timeout; registradores coincidem com os valores acima; FC16 nos inversores é registrado corretamente no log.

---

### Etapa 2 — Openloop (`mode: "openloop"`)

**Objetivo:** validar as rotinas de controle do SCRPI em cenário estável.

**Comportamento:**
- Simulação física: **ativa** (Thévenin + ZIP + dinâmica de 1ª ordem)
- Carga e irradiância: **fixas** (valores do YAML)
- Perfis CSV e eventos: **ignorados**

**Cenário de referência:**

```
P_gen (todos a 100%) = 455 kW
P_carga = 200 kW
P_pcc ≈ −255 kW  →  exportação para a rede
V_pcc > 380 V    →  tensão sobe acima do nominal
```

**Critério de aprovação:** controlador converge para o setpoint de exportação sem oscilações.

---

### Etapa 3 — Full (`mode: "full"`)

**Objetivo:** testar o controlador sob condições dinâmicas e perturbações.

**Comportamento:**
- Simulação física: **ativa**
- Perfis CSV: **ativos** (`u_profile.csv`, `load_profile.csv`)
- Eventos: **ativos** (relidos a cada `events_poll_s` segundos)

**Critério de aprovação:** todos os testes da seção 7 (eventos de falha) passam; sistema converge de volta ao regime estável após restauração dos eventos.

---

## 4. Modelos físicos implementados

### 4.1 Equivalente de Thévenin

A rede elétrica entre a subestação e o PCC é representada como uma fonte de tensão `Vth` em série com impedância `R + jX`.

**Equação de queda de tensão (aproximação linearizada de 1ª ordem):**

```
ΔV_fase ≈ (R · P_fase + X · Q_fase) / Vth_fase

onde:
  P_fase  = P_pcc × 1000 / 3    [W por fase]
  Q_fase  = Q_pcc × 1000 / 3    [VAr por fase]
  Vth_fase = Vth_LL / √3         [V fase-neutro]
```

**Tensão resultante no PCC:**

```
V_pcc_fase = Vth_fase − ΔV
V_pcc_LL   = V_pcc_fase × √3
```

**Convenção de sinais:**
- `P_pcc > 0` → importação da rede → tensão **cai**
- `P_pcc < 0` → exportação para a rede → tensão **sobe**

**Parâmetros padrão:**

| Parâmetro | Valor | Origem |
|-----------|-------|--------|
| `Vth_LL` | 380,0 V | Tensão nominal BT |
| `R` | 0,00283 Ω | Calculado (ver seção 9) |
| `X` | 0,01416 Ω | Calculado (ver seção 9) |
| `X/R` | 5,0 | Típico de MT urbana |

**Implementação em Python (`simulation.py`):**

```python
def v_pcc_ll(self, p_pcc_kw: float, q_pcc_kvar: float) -> float:
    vth_fase = self.vth_ll_v / sqrt(3.0)
    if vth_fase < 1.0:
        return 0.0
    p_fase_w  = p_pcc_kw   * 1000.0 / 3.0
    q_fase_var = q_pcc_kvar * 1000.0 / 3.0
    delta_v   = (self.r_ohm * p_fase_w + self.x_ohm * q_fase_var) / vth_fase
    return max(0.0, (vth_fase - delta_v) * sqrt(3.0))
```

**Implementação em Structured Text (`FB_Thevenin.st`):**

```pascal
vth_fase   := vth_ll_v / SQRT3;
p_fase_w   := p_pcc_kw   * 1000.0 / 3.0;
q_fase_var := q_pcc_kvar * 1000.0 / 3.0;
delta_v    := (r_ohm * p_fase_w + x_ohm * q_fase_var) / vth_fase;
v_pcc_ll_v := MAX(0.0, (vth_fase - delta_v) * SQRT3);
```

---

### 4.2 Modelo de carga ZIP

O modelo ZIP descreve como a potência consumida por uma carga elétrica varia quando a tensão muda. O nome vem das três componentes:

| Componente | Sigla | Dependência de V | Exemplo físico |
|-----------|-------|-----------------|----------------|
| Impedância constante | Z | P ∝ V² | Resistência, aquecedor |
| Corrente constante | I | P ∝ V | Algumas fontes controladas |
| Potência constante | P | P independe de V | Inversor, ar condicionado com drive |

**Equações:**

```
P_load = P₀ × (aZ·Vr² + aI·Vr + aP)
Q_load = Q₀ × (bZ·Vr² + bI·Vr + bP)

onde Vr = V_pcc / V_nominal
```

**Premissa ANEEL para perdas técnicas em alimentadores:**

> *"50% potência constante e 50% de impedância constante para a parte ativa,  
> e 100% de potência constante para a parte reativa."*

**Coeficientes adotados:**

| Coeficiente | Valor | Significado |
|-------------|-------|-------------|
| `aZ` (ZIP_P_Z) | 0,50 | 50% da carga ativa varia com V² |
| `aI` (ZIP_P_I) | 0,00 | 0% da carga ativa varia com V |
| `aP` (ZIP_P_P) | 0,50 | 50% da carga ativa é constante |
| `bZ` (ZIP_Q_Z) | 0,00 | — |
| `bI` (ZIP_Q_I) | 0,00 | — |
| `bP` (ZIP_Q_P) | 1,00 | 100% da carga reativa é constante |

**Consequência prática:** com V_pcc = 0,9 × 380 V (queda de 10%):

```
P_load = 200 × (0,5 × 0,81 + 0,5) = 200 × 0,905 = 181 kW  (cai 9,5%)
Q_load = 50  × 1,0               =  50 kVAr         (inalterado)
```

**Iteração dupla no simulador:**
O simulador aplica o ZIP em dois passos por ciclo. Primeiro calcula V_pcc com carga nominal para obter uma tensão estimada, depois corrige a carga pelo ZIP e recalcula V_pcc com a carga corrigida. Uma única iteração é suficiente para redes com `Scc >> S_carga`.

---

### 4.3 Dinâmica de 1ª ordem dos inversores

Cada inversor é modelado como dois filtros de 1ª ordem independentes (P e Q), com saturação na potência disponível e no limite de potência aparente nominal.

**Discretização por Euler explícito:**

```
α = Ts / τP
β = Ts / τQ

P[k+1] = P[k] + α × (P_ref  − P[k])    saturado em [0, u × P_nom]
Q[k+1] = Q[k] + β × (Q_ref  − Q[k])    saturado em [−Q_lim, +Q_lim]

onde:
  P_ref  = (setpoint_pct / 100) × P_nom
  Q_ref  = sign_Q × P[k] × tan(acos(PF_mag))
  Q_lim  = √(S_nom² − P[k]²)
  u      = irradiância normalizada [0..1]
```

**Estabilidade numérica:** α e β são saturados em 1,0 para evitar instabilidade quando `Ts ≥ τ`.

**Parâmetros padrão:** `τP = τQ = 1,0 s` para todos os inversores. Após um degrau de 0% → 100%:
- t = 1τ = 1 s → P = 63,2% de P_nom
- t = 5τ = 5 s → P = 99,3% de P_nom

**Decodificação do comando de fator de potência (HR 257):**

| Faixa raw | Tipo | Cálculo do FP | Efeito em Q |
|-----------|------|--------------|-------------|
| 1–20 | Lagging (indutivo) | FP = 1,00 − raw × 0,01 | Q < 0 (consome reativo) |
| 80–99 | Leading (capacitivo) | FP = raw / 100 | Q > 0 (injeta reativo) |
| 100 | Unitário | FP = 1,00 | Q = 0 |
| 21–79 | Inválido | Tratado como 100 | Q = 0 |

---

### 4.4 Codificação Modbus dos registradores do medidor

Todas as grandezas são reportadas no **secundário dos instrumentos de medição** (TP e TC). O controlador mestre multiplica por RTP e RTC para reconstruir as grandezas primárias.

**Parâmetros dos instrumentos:**

| Instrumento | Relação | Valor |
|-------------|---------|-------|
| TP (transformador de potencial) | RTP = 13800/115 | 120 |
| TC (transformador de corrente) | RTC = 200/5 | 200 |

**Fórmulas de codificação:**

```
Reg_PF  = round(PF_com_sinal × 16384)        [U16, com sinal via complemento]
Reg_I   = round(I_sec_A × 256)               [U16, resolução 1/256 A]
Reg_V   = round(V_sec_fn_V × 128)            [U16, resolução 1/128 V]
```

**Codificação do FP com sinal:**

```
PF ∈ [0, +1]  →  reg = round(PF × 16384)           → 0..16384
PF ∈ [-1, 0)  →  reg = 65535 − round(|PF| × 16384) → 49151..65535
```

**Mapa de registradores (FC03, base 0x0099, quantidade 28):**

| Offset | Endereço | Grandeza | Codificação |
|--------|---------|---------|-------------|
| 0 | 0x0099 | PF fase A | × 16384 |
| 1 | 0x009A | PF fase B | × 16384 |
| 2 | 0x009B | PF fase C | × 16384 |
| 3–6 | 0x009C–9F | Reservado | = 0 |
| 7 | 0x00A0 | Ia (A sec) | × 256 |
| 8 | 0x00A1 | Ib (A sec) | × 256 |
| 9 | 0x00A2 | Ic (A sec) | × 256 |
| 10 | 0x00A3 | Reservado | = 0 |
| 11 | 0x00A4 | Ua fn (V sec) | × 128 |
| 12 | 0x00A5 | Ub fn (V sec) | × 128 |
| 13 | 0x00A6 | Uc fn (V sec) | × 128 |
| 14–27 | 0x00A7–B4 | Reservado | = 0 |

**Mapa de registradores dos inversores (FC16):**

| HR | Conteúdo | Faixa |
|----|---------|-------|
| 256 | Setpoint %P | 0–100 |
| 257 | FP raw | 1–100 |

---

## 5. Estrutura do código Python

```
simulador_v3/
├── requirements.txt          pymodbus==3.7.4, pyyaml==6.0.2, pyserial==3.5
├── configs/
│   ├── config.yaml           ← arquivo ativo
│   ├── config_etapa1_loopback.yaml
│   ├── config_etapa2_openloop.yaml
│   ├── config_etapa3_full.yaml
│   └── events.json           ← injeção de falhas (Etapa 3)
├── profiles/
│   ├── u_profile.csv         (time_s, u)
│   └── load_profile.csv      (time_s, P_load_kW, Q_load_kVAr)
└── simulator/
    ├── __init__.py
    ├── main.py               orquestração de tasks assíncronas
    ├── config.py             leitura do YAML → dataclasses
    ├── modbus_server.py      servidores RTU slave (pymodbus)
    ├── profiles.py           perfis piecewise-constant
    └── simulation.py         núcleo físico
```

**Responsabilidades de cada módulo:**

| Módulo | Equivalente ST | Responsabilidade |
|--------|---------------|-----------------|
| `main.py` | Task cíclica Codesys | Orquestra tasks async, melhora timer Windows |
| `config.py` | `GVL_SimConfig.st` | Lê YAML, popula dataclasses |
| `modbus_server.py` | Driver Modbus Slave nativo | Servidores RTU, callbacks FC16, atualiza registradores |
| `simulation.py` | `FB_Simulator.st` + FBs auxiliares | Toda a física: Thévenin, ZIP, dinâmica |
| `profiles.py` | `FC_ProfileStep.st` | Perfis piecewise-constant |

**Ciclo de tempo:**

| Plataforma | `tick_s` | Observação |
|------------|---------|-----------|
| Raspberry Pi 4 (Linux) | 0,01 s | Scheduler tempo real disponível |
| Windows | 0,05 s | Mínimo seguro com `timeBeginPeriod(1)` |
| Codesys | 0,05 s | Período da task cíclica |

---

## 6. Porte para Codesys (Structured Text)

### 6.1 Cenário com 4 portas RS485

O contexto descrito utiliza um computador rodando Codesys como simulador escravo, com 4 portas RS485 físicas:

```
Computador com Codesys (simulador — slave)
├── COM1-A → slave 100  (medidor — FC03, 28 regs a partir de 0x0099)
├── COM1-B → slave 101  (inversor 0 — FC16, HR256/257)
├── COM2-A → slave 201  (inversor 9  — FC16, HR256/257)
└── COM2-B → slave 202  (inversor 10 — FC16, HR256/257)

WAGO CC100 (SCRPI — master)
└── Lê slave 100 / escreve slaves 101, 201, 202
```

**Observação importante:** o código ST suporta todos os 18 inversores. Para o cenário com apenas 3 inversores ativos, os demais permanecem com P = 0 e Q = 0 (setpoints não recebidos do master) e contribuem zero para a geração. O comportamento é fisicamente correto.

### 6.2 Matriz de migração Python → ST

| Arquivo Python | Ação no Codesys | Motivo |
|----------------|----------------|--------|
| `modbus_server.py` | Descartado | Substituído pelo driver Modbus RTU Slave nativo |
| `simulation.py` | Reescrito em ST | Núcleo físico — trabalho principal de portagem |
| `profiles.py` | Reescrito em ST | Arrays constantes em `GVL_SimState` |
| `main.py` | Descartado | Substituído pelo scheduler de tasks do Codesys |
| `config.py` | Virou `GVL_SimConfig.st` | `VAR_GLOBAL CONSTANT` |
| `events.json` | Virou variáveis `g_Ev_*` | Editáveis via Watch Window ou HMI |
| `config_etapa*.yaml` | Fundidos em `GVL_SimConfig.st` | Seleção por `g_SimMode` em runtime |

### 6.3 Arquivos ST gerados

| Arquivo | Papel |
|---------|-------|
| `GVL_SimConfig.st` | Parâmetros constantes (equivale aos 3 YAMLs) |
| `GVL_SimState.st` | Estado runtime: inversores, medidor, eventos, perfis |
| `GVL_Events_DOC.st` | Documentação da injeção de falhas via variáveis |
| `FC_EncodePF.st` | Codifica FP com sinal → U16 |
| `FC_EncodeIV.st` | Codifica corrente e tensão → U16 |
| `FC_DecodePF.st` | Decodifica FP raw do master |
| `FC_ProfileStep.st` | Perfil piecewise-constant |
| `FB_Thevenin.st` | Modelo de Thévenin |
| `FB_ZipLoad.st` | Modelo de carga ZIP |
| `FB_InverterDyn.st` | Dinâmica de 1ª ordem de cada inversor |
| `FB_Simulator.st` | Núcleo — equivale a `PlantSimulation.step()` |
| `PRG_Main.st` | Programa principal chamado pela task cíclica |

### 6.4 Configuração da task e mapeamento Modbus

**Task cíclica:**

| Campo | Valor |
|-------|-------|
| Nome | `Task_Simulator` |
| Tipo | Cíclica |
| Período | **50 ms** (= `TICK_S`) |
| Prioridade | 2 (abaixo do Modbus Slave, acima do HMI) |

**Mapeamento I/O — slave 100 (medidor):**

| Parâmetro | Valor |
|-----------|-------|
| Função suportada | FC03 |
| Endereço base | 153 (= 0x0099) |
| Quantidade | 28 registradores UINT |
| Variável mapeada | `MW_Meter[0..27]` |

**Mapeamento I/O — slaves 101, 201, 202 (inversores):**

| HR | Variável mapeada | Tipo |
|----|-----------------|------|
| 256 | `MW_Inv_P_Raw[i]` | UINT → convertido para REAL em `PRG_Main` |
| 257 | `MW_Inv_PF_Raw[i]` | UINT → convertido para INT em `PRG_Main` |

**Seleção de modo em runtime** — alterar `g_SimMode` via Watch Window:

| `g_SimMode` | Constante | Comportamento |
|-------------|-----------|--------------|
| 0 | `SIM_MODE_LOOPBACK` | Medidor fixo, sem física |
| 1 | `SIM_MODE_OPENLOOP` | Física ativa, carga/u fixas |
| 2 | `SIM_MODE_FULL` | Física + perfis + eventos |

---

## 7. Eventos de falha injetáveis

Os eventos são usados exclusivamente no **modo FULL (Etapa 3)**. No Python, são lidos do arquivo `configs/events.json` a cada `events_poll_s` segundos. No Codesys ST, são variáveis globais `g_Ev_*` editáveis em runtime via Watch Window ou HMI.

### 7.1 Perda de comunicação (`drop_comms`)

**O que representa fisicamente:** cabo RS485 desconectado ou inversor que parou de responder ao Modbus. O master continua tentando escrever setpoints, mas as mensagens não chegam.

**Comportamento do simulador:** o inversor entra em modo de segurança autônomo — a potência rampa de `P_atual` para zero em exatamente **5 segundos**, simulando o comportamento típico de firmware de inversores ao perder comunicação com o controlador externo.

**O que o controlador deve fazer:** detectar a mudança de potência no PCC e redistribuir setpoints para os demais inversores.

**Diferença para o controlador:** a falha é **explícita** — o master recebe timeout nas respostas Modbus.

**Como ativar no Python (`events.json`):**

```json
{"drop_comms": [101], "freeze_s": {}, "force_u": {}}
```

**Como ativar no Codesys ST:**

```pascal
g_Ev_DropComms[0] := TRUE;   // índice 0 = slave 101
```

**Como restaurar:**

```json
{"drop_comms": [], "freeze_s": {}, "force_u": {}}
```

```pascal
g_Ev_DropComms[0] := FALSE;
```

---

### 7.2 Congelamento de firmware (`freeze_s`)

**O que representa fisicamente:** o inversor continua respondendo ao Modbus normalmente (sem timeout), mas **ignora os setpoints recebidos** — P e Q ficam travados no último valor. Simula um bug de firmware onde o inversor acusa recepção do FC16 mas não aplica o novo valor internamente.

**Comportamento do simulador:** P e Q permanecem constantes pelo número de segundos especificado. O timer decrementa a cada tick.

**O que o controlador deve fazer:** manter estabilidade mesmo com um inversor "surdo". Risco específico: **windup do integrador** tentando forçar um inversor que não responde.

**Diferença para o controlador:** a falha é **silenciosa** — o master não recebe nenhum erro, a resposta Modbus parece normal, mas a potência não muda.

**Como ativar no Python (`events.json`):**

```json
{"drop_comms": [], "freeze_s": {"103": 20.0, "208": 15.0}, "force_u": {}}
```

**Como ativar no Codesys ST:**

```pascal
g_Ev_Freeze_s[2]  := 20.0;   // índice 2 = slave 103, congela por 20 s
g_Ev_Freeze_s[16] := 15.0;   // índice 16 = slave 208, congela por 15 s
```

**Nota:** o comportamento é acumulativo — o simulador usa `MAX(tempo_restante, novo_valor)`.

---

### 7.3 Sombreamento parcial (`force_u`)

**O que representa fisicamente:** passagem de nuvem, sujeira em painéis ou falha de string. Sobrescreve a irradiância normalizada de um inversor específico, independente do perfil global.

**Comportamento do simulador:** a potência disponível do inversor afetado é reduzida para `force_u × P_nom`. O inversor ainda aceita setpoints, mas fica limitado pela disponibilidade de energia.

**Como ativar no Python (`events.json`) — nuvem em COM1:**

```json
{
  "drop_comms": [],
  "freeze_s": {},
  "force_u": {"101":0.3,"102":0.3,"103":0.3,"104":0.3,
               "105":0.3,"106":0.3,"107":0.3,"108":0.3,"109":0.3}
}
```

**Como ativar no Codesys ST:**

```pascal
g_Ev_Force_U[0] := 0.3;   // slave 101 → 30% de irradiância
g_Ev_Force_U[1] := 0.3;   // slave 102
// ... repetir para índices 2..8 (slaves 103..109)
```

**Como restaurar (−1,0 = usa irradiância global do perfil):**

```pascal
g_Ev_Force_U[0] := -1.0;
```

---

### Tabela de comparação dos eventos

| | `drop_comms` | `freeze_s` | `force_u` |
|--|-------------|------------|-----------|
| Modbus responde? | Não (timeout) | Sim (normal) | Sim (normal) |
| P e Q mudam? | Sim — rampa a zero | Não — congelados | Sim — limitados por u |
| Master sabe que algo errado? | Sim (timeout explícito) | Não (falha silenciosa) | Não (falha silenciosa) |
| Dificuldade para o controlador | Média | Alta | Média |

---

### Cenários de teste prontos (Etapa 3)

**T1 — Perda de inversor grande (60 kW):**

```json
{"drop_comms": [101], "freeze_s": {}, "force_u": {}}
```

**T2 — Nuvem passageira em toda a COM1:**

```json
{"drop_comms": [], "freeze_s": {},
 "force_u": {"101":0.3,"102":0.3,"103":0.3,"104":0.3,
             "105":0.3,"106":0.3,"107":0.3,"108":0.3,"109":0.3}}
```

**T3 — Travamento + perda de comunicação combinados:**

```json
{"drop_comms": [207], "freeze_s": {"103": 20.0, "208": 15.0}, "force_u": {}}
```

**T4 — Retorno à operação normal:**

```json
{"drop_comms": [], "freeze_s": {}, "force_u": {}}
```

---

## 8. Fluxo de operação do código

A cada ciclo de 50 ms, a seguinte sequência é executada:

```
1. PRG_Main
   ├── Primeiro scan? → inicializa g_SimMode = LOOPBACK, g_Reset = TRUE
   ├── Copia registradores Modbus → variáveis de simulação
   │     MW_Inv_P_Raw[i]  → g_Inv_P_Ref_Pct[i]  (UINT → REAL, saturado 0..100)
   │     MW_Inv_PF_Raw[i] → g_Inv_PF_Cmd_Raw[i] (UINT → INT)
   └── Chama FB_Simulator()

2. FB_Simulator
   ├── g_Reset = TRUE?  → zera t_s, P, Q, flags de todos os inversores
   ├── Modo mudou?      → reinicializa medidor (loopback: preenche MW_Meter fixo)
   ├── Avança tempo     → g_T_s += TICK_S
   │
   ├── [LOOPBACK] → RETURN (sem física, MW_Meter já preenchido)
   │
   └── [OPENLOOP / FULL]
       ├── Lê perfis (FC_ProfileStep)
       │     FULL:     u_global ← U_Profile, load_p0 ← Load_Profile
       │     OPENLOOP: u_global = U_DEFAULT, load_p0 = LOAD_P_KW_DEFAULT
       │
       ├── Loop para cada inversor i = 0..N-1
       │   ├── Define u_inv (force_u ou u_global)
       │   ├── Aplica drop_comms (rampa P → 0 em 5 s)
       │   ├── frozen_s > 0? → P e Q congelados, decrementa timer, CONTINUE
       │   └── FB_InverterDyn (Euler 1ª ordem)
       │         P[k+1] = P + α·(Pref − P)   saturado em [0, u·Pnom]
       │         Q[k+1] = Q + β·(Qref − Q)   saturado em [−Qlim, +Qlim]
       │
       ├── Agrega PCC
       │     p_gen = ΣP[i],  q_gen = ΣQ[i]
       │     p_pcc = p_carga − p_gen
       │     q_pcc = q_carga − q_gen
       │
       ├── 1ª iteração Thévenin → V_pcc_0  (com carga nominal)
       ├── Correção ZIP         → load_p, load_q  (com V_pcc_0)
       ├── 2ª iteração Thévenin → V_pcc_ll  (com carga corrigida)
       │
       ├── Calcula FP com sinal, tensão e corrente nos secundários dos instrumentos
       │
       └── Codifica MW_Meter[0..27]
             FC_EncodePF → PF das três fases
             FC_EncodeI  → correntes secundárias
             FC_EncodeV  → tensões secundárias

3. Driver Modbus Slave
   ├── Master faz FC03 ao slave 100 → responde com MW_Meter[]
   └── Master faz FC16 aos slaves inversores → escreve em MW_Inv_*_Raw[]
```

---

## 9. Origem e cálculo dos parâmetros de Thévenin

Os valores `R = 0,00283 Ω` e `X = 0,01416 Ω` **não foram medidos em campo**. Foram calculados a partir de premissas típicas de alimentadores de distribuição urbana de 13,8 kV.

**Premissa adotada:** `Scc = 10 MVA` no ponto de conexão (valor conservador para MT urbana de médio porte).

### Passo 1 — Impedância na MT

```
|Z_MT| = V² / Scc = 13800² / 10.000.000 = 190.440.000 / 10.000.000 = 19,044 Ω
```

### Passo 2 — Referir ao BT (380 V)

A relação de transformação do transformador MT/BT é `a = 13800 / 380 = 36,316`.

```
|Z_BT| = |Z_MT| / a² = 19,044 / (36,316²) = 19,044 / 1318,9 = 0,01445 Ω
```

### Passo 3 — Decompor com X/R = 5 (típico de MT urbana)

```
|Z| = √(R² + X²)   e   X = 5R

0,01445 = √(R² + 25R²) = R × √26 = R × 5,0990

R = 0,01445 / 5,0990 = 0,00283 Ω  ✓
X = 5 × 0,00283     = 0,01416 Ω  ✓
```

### Sensibilidade dos parâmetros

| Scc real | R (BT) | X (BT) | X/R | Efeito na tensão |
|---------|--------|--------|-----|-----------------|
| 5 MVA (ramal longo) | 0,00566 Ω | 0,02832 Ω | 5,0 | Variação 2× maior |
| 10 MVA (padrão adotado) | 0,00283 Ω | 0,01416 Ω | 5,0 | Referência |
| 20 MVA (próximo à SE) | 0,00141 Ω | 0,00708 Ω | 5,0 | Variação 2× menor |
| 50 MVA (SE de grande porte) | 0,00057 Ω | 0,00283 Ω | 5,0 | Tensão praticamente constante |

### Como obter os valores corretos da rede real

| Caminho | Método | Precisão |
|---------|--------|---------|
| 1 | Solicitar à concessionária o nível de curto-circuito trifásico no ponto de conexão (em MVA ou kA) e recalcular | Alta |
| 2 | Medir empiricamente: ligar/desligar carga conhecida, registrar ΔV, calcular `R ≈ ΔV × Vth / ΔP_fase` | Média |
| 3 | Extrair do estudo de conexão à rede (exigido pela ANEEL para GD > 75 kW) | Alta |

**Recomendação para testes com confiança:** executar o simulador com o intervalo de Scc esperado (ex: 5 MVA a 20 MVA) e verificar que o controlador converge nos dois extremos.

---

## 10. Derivação da equação de queda de tensão

### Circuito equivalente

```
     R          X
Vth ──┤├──────┤├──── PCC ──── Carga (P + jQ)
      └───────────────────────┘
```

A rede é uma fonte `Vth` em série com `R + jX`. A corrente de carga tem duas componentes: ativa (em fase com V, associada a P) e reativa (90° defasada, associada a Q).

### Aproximação linearizada

A equação exata da queda de tensão é fasorial e não-linear. Para redes de distribuição onde `ΔV << Vth` (tipicamente menos de 5%), existe uma aproximação amplamente usada em estudos de fluxo de carga simplificados:

```
ΔV_fase ≈ (R · P_fase + X · Q_fase) / Vth_fase
```

Esta aproximação:
- É exata quando o ângulo de carga é pequeno
- Tem erro < 0,5% para quedas de tensão abaixo de 5%
- É a base do método de Newton-Raphson desacoplado rápido

### Exemplo numérico — carga 200 kW + 50 kVAr, sem geração

**Passo 1 — Grandezas por fase:**

```
Vth_fase = 380 / √3        = 380 / 1,7321 = 219,4 V
P_fase   = 200.000 / 3     = 66.667 W
Q_fase   = 50.000 / 3      = 16.667 VAr
```

**Passo 2 — Queda de tensão:**

```
ΔV = (R · P_fase  +  X · Q_fase) / Vth_fase
   = (0,00283 × 66.667  +  0,01416 × 16.667) / 219,4
   = (    188,6          +      235,9        ) / 219,4
   =  424,5 / 219,4
   =  1,935 V
```

Observação sobre a proporção: a queda resistiva (188,6 V·W/V = 188,6 W) e a queda reativa (235,9 VAr) têm magnitudes comparáveis porque X/R = 5, mas Q é apenas 25% de P. Em redes com X/R maior, a parcela reativa dominaria.

**Passo 3 — Tensão no PCC:**

```
V_pcc_fase = 219,4 − 1,935 = 217,5 V
V_pcc_LL   = 217,5 × √3    = 376,6 V
```

### Comportamento com geração fotovoltaica

Quando os inversores geram, `P_pcc` fica negativo (exportação). A queda ΔV também fica negativa — tornando-se uma **elevação** de tensão:

```
P_pcc < 0  →  ΔV < 0  →  V_pcc > Vth  →  tensão sobe acima do nominal
```

Este é exatamente o fenômeno que o controlador SCRPI limita. Com geração plena (455 kW) e carga de 200 kW:

```
P_pcc ≈ −255 kW
ΔV ≈ (0,00283 × (−85.000) + 0,01416 × (−5.556)) / 219,4
   ≈ (−240,6 − 78,7) / 219,4
   ≈ −1,456 V
V_pcc ≈ (219,4 + 1,456) × √3 ≈ 383,0 V
```

---

## 11. Validação do simulador

### 11.1 Camada 1 — Validação analítica

Verificar que o código produz exatamente o número que a matemática prevê para casos com resposta conhecida.

**Caso 1 — Thévenin estático:**

Com todos os inversores a 0%, carga 200 kW + 50 kVAr:

```
Resultado esperado: V_pcc = 376,6 V
```

Executar o simulador em modo openloop com setpoints a 0% e verificar `g_Meter_V_PCC_LL_V`.

**Caso 2 — Codificação loopback:**

Com PF = 0,92:

```
Resultado esperado: MW_Meter[0] = round(0,92 × 16384) = 15073
```

Ler o registrador bruto via Modbus e conferir o valor U16.

**Caso 3 — Dinâmica de 1ª ordem:**

Após degrau 0% → 100% com τ = 1,0 s e tick = 50 ms (α = 0,05):

```
t = 1,0 s (20 ciclos):  P = P_nom × (1 − e^{−1}) = 63,2% de P_nom
t = 5,0 s (100 ciclos): P = P_nom × (1 − e^{−5}) = 99,3% de P_nom
```

Pode-se verificar na planilha, calculando cada passo do Euler: `P[k+1] = P[k] + 0,05 × (P_nom − P[k])`.

---

### 11.2 Camada 2 — Cenários com critério numérico

| Cenário | Condição de entrada | Resultado esperado |
|---------|--------------------|--------------------|
| C1 — Repouso | Todos inv. a 0%, carga 200+j50 kVA | V_pcc = 376,6 V, PF = +0,970 indutivo |
| C2 — Geração plena | Todos inv. a 100%, u=1,0, carga 200+j50 | P_pcc ≈ −255 kW, V_pcc > 380 V, PF negativo |
| C3 — Ponto neutro | Setpoint tal que P_gen = P_carga | P_pcc ≈ 0, V_pcc ≈ 380 V |
| C4 — Degrau τ | Degrau 0%→100%, τ=1 s | P(1s) = 63,2% P_nom, P(5s) = 99,3% P_nom |
| C5 — ZIP tensão | V_pcc = 0,9×380 V, coef. ANEEL | P_load = 181 kW, Q_load = 50 kVAr (inalterado) |
| C6 — FP lagging | PF raw = 10, P = 100 kW | FP = 0,90, Q = −48,4 kVAr |
| C7 — FP leading | PF raw = 90, P = 100 kW | FP = 0,90, Q = +48,4 kVAr |
| C8 — Drop comms | drop_comms ativado em t = 0 | P rampa → 0 em exatamente 5 s |
| C9 — Freeze | freeze_s = 10, novo setpoint enviado | P e Q congelados por 10 s |
| C10 — Loopback regs | Modo loopback padrão | MW[0]=15073, MW[7]=640, MW[11]=8499 |

---

### 11.3 Camada 3 — Validação cruzada Python × Codesys ST

Python e Codesys ST implementam o mesmo modelo matemático em linguagens diferentes. Executar ambos com os mesmos parâmetros e comparar as saídas tick a tick. Convergência indica ausência de bugs; divergência aponta erro em um dos dois.

**Script de referência para extração de dados do Python:**

```python
# validacao_cruzada.py — roda sem hardware, sem Modbus
from simulator.simulation import (
    PlantSimulation, InverterState, MeterState,
    TheveninModel, ZipLoadModel
)

inv = [InverterState(
    slave_id=101, p_nom_kw=60, s_nom_kva=60,
    tau_p_s=1.0, tau_q_s=1.0
)]
meter = MeterState(slave_id=100)
sim = PlantSimulation(
    inverters=inv, meter=meter,
    tick_s=0.05, v_ll_v=380.0,
    load_p_kw=200.0, load_q_kvar=50.0,
    thevenin=TheveninModel(),
    zip_load=ZipLoadModel(),
    mode="openloop"
)
sim.set_inverter_setpoint_pct(101, 100.0)  # degrau 0→100%

print("t_s, P_kW, Q_kVAr, V_pcc_LL, PF")
for _ in range(200):  # 10 segundos
    sim.step()
    if abs(sim.t_s % 1.0) < 0.026:
        m = sim.meter
        print(f"{sim.t_s:.1f}, {inv[0].p_kw:.4f}, {inv[0].q_kvar:.4f}, "
              f"{m.v_pcc_ll_v:.4f}, {m.pfa:.6f}")
```

Comparar a saída com as variáveis `g_Inv_P_kW[0]`, `g_Meter_V_PCC_LL_V`, `g_Meter_PFa` no Codesys. A diferença aceitável é < 0,01% (float64 Python vs float32 Codesys).

---

### 11.4 Camada 4 — Limites honestos do simulador

O simulador é um modelo matemático simplificado, não um gêmeo digital de alta fidelidade. As simplificações foram feitas conscientemente e são adequadas para o objetivo de homologar o controlador SCRPI.

| Limitação | O que o simulador não modela | Impacto real |
|-----------|------------------------------|-------------|
| Rede monofásica equivalente | Desequilíbrio de fases, harmônicos, flicker, transitórios de chaveamento | Funções de qualidade de energia e proteção diferencial não podem ser testadas |
| Inversores sem saturação de corrente de pico | Proteção de sobrecorrente interna, comportamento durante afundamentos de tensão (LVRT) | Inversor real pode se desconectar em condições que o simulador atravessa sem problema |
| Dinâmica de 1ª ordem simplificada | Controladores PI internos do inversor, anti-islanding, rampa de partida, tempo de sincronização | Captura apenas a constante de tempo de resposta de potência, suficiente para testar o controlador externo |
| Sem atraso de comunicação Modbus | Latência real de resposta, timeouts, colisão no barramento | drop_comms simula a perda total, mas não o comportamento intermitente |
| ZIP sem dinâmica de tensão | Inércia térmica e mecânica de cargas reais | Resposta da carga é instantânea no modelo |
| Iteração única no ZIP/Thévenin | Convergência iterativa completa | Erro < 0,5% para redes com Scc >> S_carga (condição satisfeita) |

**O que o simulador garante com estas camadas de validação:**
- Controle de exportação ativa e reativa
- Resposta a perturbações dinâmicas (perfis de irradiância e carga)
- Redistribuição de setpoints após falha de inversor
- Estabilidade do controlador com carga variável e falhas combinadas
- Conformidade do protocolo Modbus RTU (endereçamento, FC03, FC16, codificação)

---

## 12. OpenDSS — o que adiciona ao estudo

### 12.1 Comparativo Thévenin × OpenDSS

| Capacidade | Thévenin (simulador atual) | OpenDSS |
|-----------|---------------------------|---------|
| **Tensão e fluxo de potência** | | |
| Tensão no PCC (barra única) | ✓ completo | ✓ completo |
| Tensão em cada barra do alimentador | ✗ não modela | ✓ completo |
| Fluxo de potência em cada trecho de cabo | ✗ não modela | ✓ completo |
| Efeito de outras GDs no mesmo alimentador | ✗ não modela | ✓ completo |
| **Desequilíbrio e qualidade de energia** | | |
| Desequilíbrio de fases (trifásico real) | ✗ monofásico equiv. | ✓ trifásico completo |
| Harmônicos de corrente | ✗ não modela | ~ com módulo extra |
| Flicker (variação rápida de tensão) | ✗ não modela | ~ com série temporal |
| **Proteção e coordenação** | | |
| Corrente de curto-circuito | ✗ não modela | ✓ análise de falta |
| Coordenação de proteção (relé + fusível) | ✗ não modela | ✓ com elementos de proteção |
| Anti-ilhamento (detecção de ilha) | ✗ não modela | ✓ simulável |
| **Estudos regulatórios** | | |
| Conformidade com PRODIST Módulo 8 | ~ tensão no PCC apenas | ✓ todas as barras |
| Relatório de fluxo de potência para ANEEL | ✗ não gera | ✓ exporta CSV/JSON |

### 12.2 Os três cenários onde o OpenDSS muda o resultado

**Cenário 1 — Tensão em outras barras (o mais relevante)**

O Thévenin responde apenas para a barra do PCC. Quando a usina exporta 455 kW, a tensão no PCC pode estar dentro do limite PRODIST (+5% = 399 V), mas barras mais distantes do alimentador podem violar o limite — e o Thévenin não as vê. O OpenDSS calcula a tensão em todas as barras simultaneamente.

**Cenário 2 — Interação com outras GDs no alimentador**

Se há outras usinas fotovoltaicas no mesmo alimentador, o Thévenin trata a rede como se a usina analisada fosse a única perturbação. O OpenDSS modela todas as GDs simultaneamente e captura o efeito combinado, que pode ser significativamente diferente do efeito individual.

**Cenário 3 — Coordenação de proteção**

Com inversores conectados, a corrente de curto-circuito no alimentador muda. O relé da subestação foi ajustado para uma rede sem GD. O OpenDSS permite verificar se os ajustes ainda funcionam corretamente — requisito exigido pela concessionária no processo de conexão de GD de médio/grande porte.

### 12.3 O que o OpenDSS não substitui

O OpenDSS **não substitui** o simulador construído neste projeto para o objetivo de homologar o controlador SCRPI. O OpenDSS não modela:

- O protocolo Modbus RTU e a comunicação com o controlador
- A dinâmica interna dos inversores (constante de tempo, saturação de Q)
- Os cenários de falha injetáveis (drop_comms, freeze, force_u)
- O comportamento do SCRPI em malha fechada

**Relação complementar:**

```
OpenDSS  →  usado ANTES ou DEPOIS do simulador
             ANTES:  dimensionar a usina, verificar impacto na rede
             DEPOIS: elaborar relatório de conformidade para a concessionária

Simulador Python/Codesys  →  usado DURANTE o desenvolvimento e homologação
                               do controlador SCRPI
```

Com os valores de R e X já medidos no ponto de conexão, o que falta para completar o estudo de impacto de rede é o modelo do alimentador em OpenDSS — comprimentos de cabo, seção transversal, posição das cargas, posição das outras GDs. Com isso é possível:

1. Confirmar que nenhuma barra viola tensão no pior caso de geração
2. Gerar o relatório de fluxo de potência para a concessionária
3. Verificar a coordenação de proteção com a GD conectada

---

*Documento gerado em 23 de março de 2026*  
*Baseado na discussão técnica completa sobre o Simulador de Usina FV — Version 3*
