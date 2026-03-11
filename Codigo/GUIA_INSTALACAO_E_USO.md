# Guia de Instalação e Uso — Simulador de Usina Fotovoltaica (18 inversores + 1 medidor) — Modbus RTU (Raspberry Pi 4)

**Data:** 2026-03-11  
**Plataforma alvo:** Raspberry Pi 4 (Linux ARM)  
**RS485:** Waveshare RS232/RS485/CAN HAT (duas portas independentes)  
**Portas seriais (consolidado):**
- **COM1:** `/dev/ttySC0`
- **COM2:** `/dev/ttySC1`

---

## 1) Visão geral do simulador

Este simulador emula uma usina fotovoltaica com:

- **18 inversores** (slaves Modbus RTU)
  - COM1: slave IDs **101–109**
  - COM2: slave IDs **201–209**
- **1 medidor no PCC** (slave Modbus RTU)
  - COM1: slave ID **100**
- Um **controlador real** (PLC) atua como **Modbus Master** e executa o ciclo:
  1. **FC03**: lê o medidor (slave 100)
  2. calcula o controle
  3. **FC16**: escreve setpoints nos inversores (slaves 101–109 e 201–209)

### Requisitos temporais consolidados
- **Taxa do PLC:** 10 ms (scan interno)
- **Ciclo de controle / Modbus:** ~2 s
- **Passo do simulador (tick):** **2 s** (tempo real)

---

## 2) Endereçamento Modbus e compatibilidade com o PLC (consolidado)

### 2.1 Medidor (slave ID 100) — FC03
- **Endereço inicial:** **153 (0x0099) direto** (confirmado)
- **Quantidade:** **28 registradores (28 × U16)**

> Observação: os **primeiros 14** registradores possuem valores úteis (PF, I, V conforme mapeamento).  
> Os **demais 14** (15..28) estão como **reservados = 0** nesta versão, mantendo compatibilidade de “tamanho de leitura” do PLC.

### 2.2 Inversores (18 slaves) — FC16
Para qualquer inversor (slave id específico), o PLC escreve:
- **HR 256:** setpoint de potência ativa em **%** do nominal (0..100), **U16**
- **HR 257:** comando de fator de potência (U16):
  - **1..20**  → **lagging (indutivo)**, PF ≈ 1.00 − (valor×0.01)  → 0.99..0.80  
  - **80..100** → **leading (capacitivo)**, PF = valor/100 → 0.80..1.00  
  - **21..79 inválido** → tratado como **PF=1.00**

**Regra importante:** embora a função seja **FC16 (Write Multiple Registers)**, o simulador **aplica apenas 1 registrador por acesso** (usa o primeiro valor escrito na requisição).

---

## 3) Pré-requisitos no Raspberry Pi

### 3.1 Sistema operacional
- Raspberry Pi OS (ou outra distro Debian-based)

### 3.2 Pacotes necessários
```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
```

### 3.3 Verificar as portas seriais
Você já consolidou as portas como:
- `/dev/ttySC0`
- `/dev/ttySC1`

Mesmo assim, recomenda-se confirmar:
```bash
ls -l /dev/ttySC*
dmesg | tail -n 100
```

---

## 4) Estrutura do projeto (esperada)

Uma estrutura típica do projeto:
```
.
├─ requirements.txt
├─ configs/
│  └─ config.yaml
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

## 5) Instalação (venv)

Na raiz do projeto:

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Para sair do ambiente virtual:
```bash
deactivate
```

---

## 6) Configuração do simulador

### 6.1 Arquivo principal: `configs/config.yaml`
Pontos críticos a conferir:
- Portas seriais:
  - `com1.serial.device: "/dev/ttySC0"`
  - `com2.serial.device: "/dev/ttySC1"`
- Medidor:
  - `slave_id: 100`
  - `base_address: 0x0099`
  - `quantity_u16: 28`
- Passo de simulação:
  - `simulation.tick_s: 2.0`
- Perfis CSV (opcionais):
  - `simulation.u_profile_csv`
  - `simulation.load_profile_csv`

### 6.2 Perfil de disponibilidade FV (opcional): `profiles/u_profile.csv`
Formato:
```csv
time_s,u
0,1.0
60,0.7
120,0.3
```

Interpretação:
- Perfil **por degraus** (piecewise constant): o último valor definido vale até o próximo tempo.

### 6.3 Perfil de carga (opcional): `profiles/load_profile.csv`
Formato:
```csv
time_s,P_load_kW,Q_load_kVAr
0,200,50
60,180,110
```

---

## 7) Execução do simulador

Com o venv ativado:

```bash
source .venv/bin/activate
python -m simulator.main --config configs/config.yaml
```

O simulador iniciará:
- 1 servidor Modbus RTU na COM1
- 1 servidor Modbus RTU na COM2
- 1 loop de simulação em tempo real (tick de 2 s)

---

## 8) Sequência de operação no PLC (resumo)

1. **Leitura do medidor (FC03)**  
   - slave: **100**
   - start: **153 (0x0099)**
   - qty: **28**

2. **Cálculo do controle** (no PLC)

3. **Escrita nos inversores (FC16)**  
   - slave: **101..109** (COM1) e **201..209** (COM2)
   - HR **256**: setpoint %P
   - HR **257**: PF raw conforme tabela

---

## 9) Observações importantes (para evitar “pegadinhas” em campo)

### 9.1 Offset 0-based vs 1-based
Você confirmou: **start=153 (0x0099) direto**.  
O simulador foi configurado para trabalhar com **endereçamento direto** (sem “-1”).

Se algum driver Modbus do PLC internamente aplicar offset, o sintoma típico será:
- PF/I/V “deslocados” (valores sem sentido) porque o bloco começará no registrador errado.

### 9.2 Reservados (registradores 15..28)
Nesta versão:
- continuam **= 0**
- mantendo compatibilidade com a leitura de 28 palavras do PLC

Se você decidir usar esses registradores para P/Q/S/energia etc., dá para expandir o mapa sem mudar a leitura.

### 9.3 Taxa de PLC vs passo do simulador
Mesmo que o PLC execute a 10 ms internamente, o controle por Modbus (~2 s) é o que governa:
- atualização de P/Q dos inversores simulados
- atualização das medições do medidor

---

## 10) Troubleshooting (rápido)

### 10.1 “Permission denied” ao abrir `/dev/ttySC0`
Tente:
```bash
groups
```
Se seu usuário não estiver em `dialout`, adicione:
```bash
sudo usermod -aG dialout $USER
```
Depois faça logout/login (ou reboot).

### 10.2 “Device busy”
Verifique se não há outro serviço usando a serial:
```bash
sudo lsof /dev/ttySC0
sudo lsof /dev/ttySC1
```

### 10.3 PLC não consegue comunicar
Checar:
- parâmetros seriais: **9600, N, 8, 1**
- A/B do RS485 (troca A/B é causa comum)
- GND de referência (dependendo do HAT e do PLC)
- termination/bias (rede RS485 longa pode exigir)

---

## 11) Checklist de validação funcional (recomendado)

1. Subir o simulador no Raspberry.
2. No PLC:
   - realizar FC03 no slave 100 (start=153, qty=28)
   - verificar se PF/I/V retornam valores coerentes (não “0” o tempo todo).
3. Escrever em um inversor:
   - HR256 = 50 (%)
   - HR257 = 100 (PF unitário)
4. Verificar no medidor:
   - mudança em correntes e PF (dependendo do perfil de carga configurado).
5. Aplicar perfil `u_profile.csv` reduzindo u e observar saturação (P_avail reduz).

---

## 12) Operação típica (exemplo de ensaio)

- `u_profile.csv`: simula passagem de nuvens (u cai e volta).
- `load_profile.csv`: adiciona carga reativa para “forçar” atuação do controle de PF.
- PLC tenta manter exportação limitada e PF conforme meta, distribuindo setpoints por inversor.

---

Se você quiser, eu também consigo gerar:
- um arquivo `systemd` para iniciar o simulador no boot do Raspberry, e
- um “modo debug” que registra em log (CSV) os valores de P/Q por inversor e PCC a cada tick (2 s).