# Guia de Instalação e Uso — Simulador de Usina Fotovoltaica V3

**Data:** 2026-03-11 (Version 3 — implantação em etapas)  
**Plataforma alvo:** Raspberry Pi 4 (Linux ARM)  
**RS485:** Waveshare RS232/RS485/CAN HAT (duas portas independentes)  
**Portas seriais:**
- **COM1:** `/dev/ttySC0`
- **COM2:** `/dev/ttySC1`

---

## 1) Visão geral e estratégia de implantação

O simulador possui **dois modos de operação**, controlados por um único campo no YAML:

| Modo | Campo no YAML | O que faz | Quando usar |
|------|---------------|-----------|-------------|
| **Etapa 1 — Loopback** | `mode: "loopback"` | Servidores Modbus ativos, medidor com valores fixos, simulação desligada | Validar comunicação RS485, slave IDs, endereçamento |
| **Etapa 2 — Full** | `mode: "full"` | Simulação completa (Thévenin, ZIP, dinâmica, eventos) | Testar o controlador de exportação |

**Para avançar de etapa:** basta mudar `mode: "loopback"` para `mode: "full"` no YAML e reiniciar o simulador. O mesmo código roda nos dois modos.

---

## 2) Estrutura do projeto

```
.
├─ requirements.txt
├─ configs/
│  ├─ config.yaml                  ← arquivo ativo (copiar de etapa1 ou etapa2)
│  ├─ config_etapa1_loopback.yaml  ← template Etapa 1
│  ├─ config_etapa2_full.yaml      ← template Etapa 2
│  └─ events.json                  ← injeção de falhas (Etapa 2)
├─ profiles/
│  ├─ u_profile.csv
│  └─ load_profile.csv
└─ simulator/
   ├─ __init__.py
   ├─ main.py
   ├─ config.py
   ├─ modbus_server.py
   ├─ profiles.py
   └─ simulation.py
```

---

## 3) Pré-requisitos e instalação

### 3.1 Pacotes
```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
```

### 3.2 Verificar portas seriais
```bash
ls -l /dev/ttySC*
```

### 3.3 Instalar dependências
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

---

## 4) ETAPA 1 — Loopback: teste de comunicação Modbus

### 4.1 Objetivo
Validar que **toda a cadeia de comunicação funciona** antes de ligar a simulação:
- RS485 físico (cabos, A/B, GND)
- Servidores Modbus RTU nas duas portas
- PLC consegue ler o medidor (FC03, slave 100, start 0x0099, qty 28)
- PLC consegue escrever nos inversores (FC16, slaves 101-209, HR 256 e 257)
- Endereçamento correto (sem offset de ±1)

### 4.2 Configuração
```bash
cp configs/config_etapa1_loopback.yaml configs/config.yaml
```

O campo chave é:
```yaml
simulation:
  mode: "loopback"
```

### 4.3 Valores fixos no medidor (para conferência)
No modo loopback, o medidor retorna valores fixos e conhecidos no **secundário dos instrumentos** (como o medidor real faz). O PLC multiplica por RTP/RTC para obter grandezas primárias.

Configuráveis no YAML:
```yaml
loopback_pf: 0.92            # PF (positivo = indutivo)
loopback_v_mt_ln_v: 66.4     # tensão fase-neutro secundário TP (V)
loopback_i_mt_a: 2.5         # corrente secundário TC (A)
```

**Valores U16 esperados nos registradores do medidor:**

| Registrador | Grandeza | Valor secundário | Codificação | U16 esperado | PLC reconstrói |
|-------------|----------|-----------------|-------------|--------------|----------------|
| 0x0099 | PF fase A | 0.92 | valor × 16384 | **15073** | 0.92 |
| 0x009A | PF fase B | 0.92 | valor × 16384 | **15073** | 0.92 |
| 0x009B | PF fase C | 0.92 | valor × 16384 | **15073** | 0.92 |
| 0x00A0 | Ia | 2.5 A | valor × 256 | **640** | 2.5 × RTC = 500 A |
| 0x00A1 | Ib | 2.5 A | valor × 256 | **640** | 2.5 × RTC = 500 A |
| 0x00A2 | Ic | 2.5 A | valor × 256 | **640** | 2.5 × RTC = 500 A |
| 0x00A4 | Ua | 66.4 V | valor × 128 | **8499** | 66.4 × RTP = 7968 V |
| 0x00A5 | Ub | 66.4 V | valor × 128 | **8499** | 66.4 × RTP = 7968 V |
| 0x00A6 | Uc | 66.4 V | valor × 128 | **8499** | 66.4 × RTP = 7968 V |

> Todos os valores cabem em U16 (0–65535). O PLC reconstrói as grandezas primárias aplicando RTP=120 e RTC=200.

### 4.4 Execução
```bash
source .venv/bin/activate
python -m simulator.main --config configs/config.yaml
```

O log mostrará:
```
=== ETAPA 1: LOOPBACK — teste de comunicação Modbus ===
  Medidor: PF=0.92, V_sec=66.40 V, I_sec=2.500 A (fixos)
  Inversores: aceitam FC16, logam setpoints recebidos
  Simulação física: DESLIGADA
```

### 4.5 Checklist da Etapa 1

**Teste 1 — Leitura do medidor (COM1):**
- [ ] PLC lê slave 100, start 0x0099, qty 28 — sem erro de timeout
- [ ] PF nos registradores 0x0099–0x009B = 15073 (ou o valor esperado)
- [ ] Correntes nos registradores 0x00A0–0x00A2 = 640 (2.5 A × 256)
- [ ] Tensões nos registradores 0x00A4–0x00A6 = 8499 (66.4 V × 128)
- [ ] PLC reconstrói: V = 66.4 × RTP = 7968 V, I = 2.5 × RTC = 500 A
- [ ] Registradores reservados (3–6, 10, 14–27) = 0

**Teste 2 — Escrita em inversor COM1:**
- [ ] PLC escreve FC16 em slave 101, HR 256 = 50 → log do simulador mostra `LOOPBACK RX: inv 101 → setpoint P = 50.0 %`
- [ ] PLC escreve FC16 em slave 101, HR 257 = 95 → log mostra `LOOPBACK RX: inv 101 → PF raw = 95`
- [ ] Repetir para slave 109 (último de COM1)

**Teste 3 — Escrita em inversor COM2:**
- [ ] PLC escreve FC16 em slave 201, HR 256 = 100 → log mostra setpoint recebido
- [ ] Repetir para slave 209 (último de COM2)

**Teste 4 — Slave ID inválido:**
- [ ] PLC tenta ler slave 150 → timeout (esperado, slave não existe)

**Critério de aprovação:** todos os testes acima passam sem erros.

### 4.6 Problemas comuns na Etapa 1

| Sintoma | Causa provável | Solução |
|---------|----------------|---------|
| Timeout em todos os slaves | Cabo RS485 desconectado ou A/B trocados | Verificar fiação |
| Timeout só em COM2 | COM2 não está na porta correta | Verificar `/dev/ttySC1` |
| PF/I/V com valores errados | Offset de endereço (±1) | Verificar se PLC usa 0-based ou 1-based |
| "Permission denied" | Usuário não está no grupo dialout | `sudo usermod -aG dialout $USER` |
| V ou I com valores fora do esperado | RTP/RTC no YAML não correspondem ao PLC | Conferir relações de transformação |

---

## 5) ETAPA 2 — Full: teste do controlador

### 5.1 Pré-requisito
**Etapa 1 aprovada** — comunicação Modbus funcionando nas duas portas.

### 5.2 Configuração
```bash
cp configs/config_etapa2_full.yaml configs/config.yaml
```

Ou simplesmente edite o YAML existente e mude:
```yaml
simulation:
  mode: "full"       # ← mudar de "loopback" para "full"
```

### 5.3 Parâmetros importantes da Etapa 2

**Thévenin (rede no PCC):**
```yaml
thevenin_vth_ll_v: 380.0   # tensão LL de Thévenin
thevenin_r_ohm: 0.00283    # R por fase (derivado de Scc=10 MVA, X/R=5)
thevenin_x_ohm: 0.01416    # X por fase
```

**Carga ZIP (ANEEL):**
```yaml
zip_p_Z: 0.50   # 50% impedância constante (P)
zip_p_P: 0.50   # 50% potência constante (P)
zip_q_P: 1.00   # 100% potência constante (Q)
```

**Inversores:**
```yaml
tau_p_s: 1.0   # constante de tempo P (segundos)
tau_q_s: 1.0   # constante de tempo Q (segundos)
```

**Medição MT:**
```yaml
v_mt_ll_v: 13800.0
rtp: 120.0
rtc: 200.0
```

### 5.4 Execução
```bash
source .venv/bin/activate
python -m simulator.main --config configs/config.yaml
```

O log mostrará:
```
=== ETAPA 2: FULL — simulação completa ===
  tick=10 ms, inversores=18
  Thévenin R=0.00283 X=0.01416 ohm
  ZIP P: Z=50% I=0% P=50%
  ZIP Q: Z=0% I=0% P=100%
```

### 5.5 Checklist da Etapa 2

**Teste 1 — Medidor dinâmico:**
- [ ] Com todos os inversores a 0%, medidor mostra PF e corrente correspondentes à carga configurada
- [ ] Ao comandar inversores a 100%, medidor mostra redução de corrente e variação de PF

**Teste 2 — Variação de tensão (Thévenin):**
- [ ] Com geração > carga (exportação), tensão no PCC sobe acima de 380 V
- [ ] Com geração < carga (importação), tensão no PCC cai abaixo de 380 V

**Teste 3 — PF com sinal:**
- [ ] Com carga reativa alta e pouca geração: PF positivo (indutivo)
- [ ] Com geração alta e carga leve: PF negativo (capacitivo)

**Teste 4 — Dinâmica dos inversores:**
- [ ] Ao comandar degrau de 0% para 100%, potência sobe gradualmente (~5τ = 5 s para 99%)
- [ ] Ao reduzir de 100% para 0%, potência desce gradualmente

**Teste 5 — Perfil de irradiância:**
- [ ] Com `u_profile.csv` ativo, potência máxima dos inversores varia conforme o perfil
- [ ] Inversores saturam quando P_ref > u × P_nom

**Teste 6 — Eventos (falhas em tempo real):**
- [ ] Editar `events.json` com `"drop_comms": [101]` → inversor 101 rampa a zero em ~5 s
- [ ] Editar com `"force_u": {"101": 0.0}` → inversor 101 perde disponibilidade
- [ ] Editar com `"freeze_s": {"103": 15.0}` → inversor 103 congela por 15 s
- [ ] Restaurar: `{"drop_comms": [], "freeze_s": {}, "force_u": {}}` → operação normal

**Teste 7 — Controlador em malha fechada:**
- [ ] PLC executa ciclo completo (ler medidor → calcular → escrever setpoints)
- [ ] Exportação converge para o limite configurado no controlador
- [ ] PF no PCC converge para a meta do controlador

---

## 6) Endereçamento Modbus (referência rápida)

### 6.1 Medidor (slave 100) — FC03
- Start: **153 (0x0099)**
- Qty: **28 registradores U16**
- Grandezas em MT (lado de média tensão)
- PF com sinal: positivo = indutivo, negativo = capacitivo

### 6.2 Inversores (slaves 101-209) — FC16
- HR **256**: setpoint %P (0–100)
- HR **257**: PF raw (1–20 lagging, 80–100 leading, 100 = unitário)
- Apenas 1 registrador por acesso (primeiro valor da requisição FC16)

---

## 7) Arquivo de eventos (`configs/events.json`)

Permite injetar falhas em tempo real sem reiniciar. O simulador relê a cada 2 s.

```json
{
    "drop_comms": [],
    "freeze_s": {},
    "force_u": {}
}
```

Detalhes de cada campo e cenários prontos: ver comentários dentro do arquivo `events.json`.

---

## 8) Troubleshooting

### 8.1 Problemas de comunicação (Etapa 1)
- **Timeout geral:** cabo RS485, A/B, GND, baudrate
- **Permission denied:** `sudo usermod -aG dialout $USER`
- **Device busy:** `sudo lsof /dev/ttySC0`
- **Valores deslocados:** offset 0-based vs 1-based no driver do PLC

### 8.2 Problemas de simulação (Etapa 2)
- **Overrun warnings:** CPU sobrecarregada → aumentar tick_s para 0.02 ou 0.05
- **Eventos sem efeito:** validar JSON (`python3 -m json.tool configs/events.json`)
- **Tensão estranha no medidor:** verificar RTP/RTC e escala de codificação
- **Inversores não respondem a setpoints:** verificar se `mode: "full"` (não "loopback")

---

## 9) Operação típica (exemplo de ensaio completo)

1. **Etapa 1:** subir com `mode: "loopback"`, validar comunicação (checklist 4.5)
2. **Transição:** mudar para `mode: "full"`, reiniciar
3. **Etapa 2:** configurar perfis de carga e irradiância, rodar controlador
4. **Durante ensaio:** injetar falhas via `events.json` (nuvem, perda de inversor, travamento)
5. **Observar:** convergência do controlador, variação de tensão, resposta a perturbações
