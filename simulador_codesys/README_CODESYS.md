# Simulador de Usina FV — Porte para Codesys (ST)

## Estrutura dos arquivos gerados

| Arquivo ST | Equivalente Python | Papel |
|---|---|---|
| `GVL_SimConfig.st` | `config.py` + `config_etapa*.yaml` | Parâmetros constantes |
| `GVL_SimState.st` | `InverterState`, `MeterState` (dataclasses) + `events.json` + perfis CSV | Estado em runtime |
| `GVL_Events_DOC.st` | `events.json` | Documentação da injeção de falhas |
| `FC_EncodePF.st` | `modbus_server.py → encode_pf_u16()` | Codifica FP → U16 |
| `FC_EncodeIV.st` | `modbus_server.py → encode_i_u16(), encode_v_u16()` | Codifica I/V → U16 |
| `FC_DecodePF.st` | `simulation.py → _decode_pf()` | Decodifica FP raw do master |
| `FC_ProfileStep.st` | `profiles.py → StepProfile.value()` | Perfil piecewise-constant |
| `FB_Thevenin.st` | `simulation.py → TheveninModel` | Modelo de Thévenin |
| `FB_ZipLoad.st` | `simulation.py → ZipLoadModel` | Modelo de carga ZIP |
| `FB_InverterDyn.st` | `simulation.py → loop de inversores` | Dinâmica 1ª ordem |
| `FB_Simulator.st` | `simulation.py → PlantSimulation.step()` | Núcleo da simulação |
| `PRG_Main.st` | `main.py` | Programa principal |

---

## Topologia das 4 portas RS485 no cenário descrito

```
Computador com Codesys (simulador — slave)
├── COM1-A → slave 100  (medidor FC03, 28 regs a partir de 0x0099)
├── COM1-B → slave 101  (inversor 0 — FC16, HR256/257)
├── COM2-A → slave 201  (inversor 9  — FC16, HR256/257)
└── COM2-B → slave 202  (inversor 10 — FC16, HR256/257)

WAGO CC100 (SCRPI — master)
└── Lê slave 100 / escreve slaves 101, 201, 202
```

> **Nota:** O código ST suporta todos os 18 inversores. Para o cenário de 4 portas  
> com apenas 3 inversores ativos, os demais permanecem em P=0, Q=0 (setpoints não  
> recebidos do master) e contribuem zero para a geração. O comportamento é correto.

---

## Configuração da Task no Codesys

| Campo | Valor |
|---|---|
| Nome | `Task_Simulator` |
| Tipo | Cíclica |
| Período | **50 ms** (deve coincidir com `TICK_S = 0.05`) |
| Prioridade | 2 (abaixo do Modbus Slave, acima do HMI) |

A task chama `PRG_Main` a cada ciclo. O `FB_Simulator` avança `g_T_s` em `TICK_S` por chamada.

---

## Configuração do driver Modbus RTU Slave

### Slave 100 (medidor) — COM1-A

| Parâmetro | Valor |
|---|---|
| Slave ID | 100 |
| Função suportada | FC03 (Read Holding Registers) |
| Endereço base | 153 (= 0x0099 decimal) |
| Quantidade | 14 registradores UINT |
| Mapeamento | `MW_Meter[0..13]` (GVL_SimState) |

O driver lê `MW_Meter[]` e responde ao master sem intervenção do programa.  
O `FB_Simulator` atualiza `MW_Meter[]` a cada ciclo de 50 ms.

### Slaves 101, 201, 202 (inversores) — COM1-B, COM2-A, COM2-B

| Parâmetro | Valor |
|---|---|
| Função suportada | FC16 (Write Multiple Registers) |
| HR 256 | Setpoint %P (0..100), mapeado em `MW_Inv_P_Raw[i]` |
| HR 257 | FP raw (1..100), mapeado em `MW_Inv_PF_Raw[i]` |

O driver escreve em `MW_Inv_P_Raw[]` e `MW_Inv_PF_Raw[]` quando o master faz FC16.  
`PRG_Main` copia esses valores para `g_Inv_P_Ref_Pct[]` e `g_Inv_PF_Cmd_Raw[]`  
antes de chamar `FB_Simulator`.

#### Mapeamento índice ↔ slave ID ↔ porta

| Índice | Slave ID | Porta | P_nom |
|---|---|---|---|
| 0 | 101 | COM1-B | 60 kW |
| 9 | 201 | COM2-A | 15 kW |
| 10 | 202 | COM2-B | 15 kW |
| (outros) | — | não conectados | 0 kW efetivo |

---

## Seleção de Etapa (modo de simulação)

Altere `g_SimMode` em runtime via Watch Window ou HMI:

| `g_SimMode` | Constante | Comportamento |
|---|---|---|
| 0 | `SIM_MODE_LOOPBACK` | Medidor com valores fixos. Sem física. Valida comunicação. |
| 1 | `SIM_MODE_OPENLOOP` | Física ativa. Carga e irradiância fixas (`LOAD_P_KW_DEFAULT`, `U_DEFAULT`). |
| 2 | `SIM_MODE_FULL` | Física + perfis CSV (`U_Profile_*`, `Load_Profile_*`) + eventos (`g_Ev_*`). |

Ao mudar o modo, o `FB_Simulator` detecta automaticamente via `_prev_mode`.

---

## Injeção de falhas (Etapa 3 — modo FULL)

Edite diretamente as variáveis `g_Ev_*` na Watch Window ou HMI:

### T1 — Perda de inversor 101 (índice 0)
```
g_Ev_DropComms[0] := TRUE
```

### T2 — Nuvem em toda a COM1 (índices 0..8)
```
g_Ev_Force_U[0..8] := 0.3
```

### T3 — Travamento + perda combinados
```
g_Ev_DropComms[15] := TRUE       // slave 207
g_Ev_Freeze_s[2]   := 20.0       // slave 103 por 20 s
g_Ev_Freeze_s[16]  := 15.0       // slave 208 por 15 s
```

### T4 — Retorno ao normal
```
g_Ev_DropComms[0..17] := FALSE
g_Ev_Freeze_s[0..17]  := 0.0
g_Ev_Force_U[0..17]   := -1.0
```

---

## Valores esperados no Loopback (verificação)

| Registrador | Grandeza | Valor sec. | U16 esperado |
|---|---|---|---|
| 0x0099 (offset 0) | PF fase A | 0,92 | 15073 |
| 0x009A (offset 1) | PF fase B | 0,92 | 15073 |
| 0x009B (offset 2) | PF fase C | 0,92 | 15073 |
| 0x00A0 (offset 7) | Ia | 2,5 A | 640 |
| 0x00A1 (offset 8) | Ib | 2,5 A | 640 |
| 0x00A2 (offset 9) | Ic | 2,5 A | 640 |
| 0x00A4 (offset 11) | Ua fn | 66,4 V | 8499 |
| 0x00A5 (offset 12) | Ub fn | 66,4 V | 8499 |
| 0x00A6 (offset 13) | Uc fn | 66,4 V | 8499 |

---

## Verificação rápida dos perfis

Os perfis padrão em `GVL_SimState` cobrem 1200 s (20 min):

### Perfil de irradiância (`U_Profile_*`)
| t (s) | u |
|---|---|
| 0 | 1,0 |
| 300 | 0,7 |
| 600 | 0,4 |
| 900 | 0,8 |
| 1200 | 1,0 |

### Perfil de carga (`Load_Profile_*`)
| t (s) | P (kW) | Q (kVAr) |
|---|---|---|
| 0 | 200 | 50 |
| 300 | 250 | 60 |
| 600 | 180 | 45 |
| 900 | 220 | 55 |
| 1200 | 200 | 50 |

Para alterar os perfis: edite os arrays `U_Profile_T_s`, `U_Profile_Val`,  
`Load_Profile_T_s`, `Load_Profile_P_kW`, `Load_Profile_Q_kVAr` em `GVL_SimState`  
e ajuste `U_PROFILE_N` e `LOAD_PROFILE_N` para o número de pontos.
