# **Simulação de Usina com Controlador Real de Exportação usando PLC \+ RS485 \+ Linux \+ OpenDSS**

## **1\. Objetivo do Sistema**

Construir um ambiente de simulação onde:

* Um **PLC real** executa os algoritmos de controle de exportação.  
* O PLC envia **setpoints de potência e fator de potência via RS485 (Modbus RTU)**.  
* Um **computador Linux** recebe esses comandos.  
* Nesse computador roda uma **simulação completa da planta elétrica**, incluindo:  
  * Usina solar com múltiplos inversores  
  * Radiância variável  
  * Carga local  
  * Conexão com rede de distribuição  
* A simulação calcula o comportamento elétrico da rede e **retorna medições ao PLC**.

Esse arranjo cria um sistema **Hardware-in-the-Loop (HIL)** simplificado.

---

# **2\. Arquitetura Geral do Sistema**

PLC real (controlador de exportação)  
        │  
        │ RS485 / Modbus RTU  
        │  
Computador Linux (simulador da planta)  
        │  
        ├── Interface Modbus  
        ├── Lógica de integração  
        └── Simulação elétrica (OpenDSS)

Fluxo de controle:

PLC calcula controle  
        ↓  
envia setpoint (potência / FP)  
        ↓  
Linux recebe via RS485  
        ↓  
Atualiza usina no OpenDSS  
        ↓  
OpenDSS resolve fluxo de carga  
        ↓  
Linux mede potência no PCC  
        ↓  
Linux envia medição ao PLC  
        ↓  
PLC recalcula controle

---

# **3\. Papel do OpenDSS**

O simulador da rede é o **OpenDSS**.

Ele permite modelar:

* Linhas de distribuição  
* Transformadores  
* Cargas  
* Usinas fotovoltaicas  
* Controle de potência e fator de potência  
* Fluxo reverso  
* Rede trifásica desequilibrada

A rede é modelada por arquivos `.dss`.

Exemplo simplificado:

New Circuit.Alimentador basekv=13.8

New Line.Lrede bus1=Subestacao bus2=PCC length=0.5 units=km

New Load.CargaLocal  
 bus1=PCC  
 phases=3  
 kv=13.8  
 kw=1500  
 kvar=300

New PVSystem.Usina  
 bus1=PCC  
 phases=3  
 kv=13.8  
 kva=3000  
 pmpp=2800  
 pf=1

Depois a rede é resolvida com:

Solve

---

# **4\. Importância da Carga na Simulação**

Para testar **controle de exportação**, é obrigatório ter **carga local**.

A potência no ponto de conexão (PCC) é:

\[  
P\_{PCC} \= P\_{geração} \- P\_{carga}  
\]

Sem carga:

exportação \= geração total

O controle não faria sentido.

Portanto o modelo correto é:

Rede da concessionária  
        │  
        PCC  
       /   \\  
    Carga   Usina

---

# **5\. Medição da Exportação**

O controlador deve usar a potência no **PCC**, não a geração.

A medição pode ser feita em:

* Linha que conecta ao alimentador  
* Monitor no OpenDSS  
* Leitura via API

Exemplo:

New Monitor.MedPCC element=Line.Lrede terminal=1 mode=1

Ou via Python.

---

# **6\. Interface de Integração**

O OpenDSS permite controle externo através de interfaces de programação.

A versão tradicional usa **COM (Component Object Model)**.

COM é uma tecnologia da Microsoft que permite que um software controle outro.

Exemplo em Python (Windows):

import win32com.client

dss \= win32com.client.Dispatch("OpenDSSEngine.DSS")  
dss.Start(0)

dss.Text.Command \= "compile master.dss"

Depois é possível executar comandos:

dss.Text.Command \= "solve"

E ler resultados:

P \= dss.Circuit.TotalPower()

---

# **7\. Limitação do COM**

COM funciona apenas no **Windows**.

No **Linux**, as alternativas são:

* DSS C-API  
* OpenDSSDirect  
* OpenDSS compilado nativamente

Para integração com Python no Linux, o mais simples é:

**OpenDSSDirect.py**

---

# **8\. Arquitetura de Software no Linux**

No computador Linux existirão três camadas:

Camada 1 — Comunicação RS485 (Modbus RTU)  
Camada 2 — Lógica de integração (Python)  
Camada 3 — Simulação elétrica (OpenDSS)

Bibliotecas usadas:

* `pyserial`  
* `pymodbus`  
* `OpenDSSDirect.py`

---

# **9\. Comunicação com o PLC**

O PLC envia dados via Modbus RTU.

Exemplo de registradores:

40001 → Setpoint de potência  
40002 → Fator de potência

Leitura em Python:

P\_ref \= read\_modbus\_register(40001)  
FP\_ref \= read\_modbus\_register(40002)

---

# **10\. Atualização da Usina no OpenDSS**

Após receber os comandos:

dss.run\_command(f"edit PVSystem.Usina pmpp={P\_ref}")  
dss.run\_command(f"edit PVSystem.Usina pf={FP\_ref}")

---

# **11\. Resolução da Rede**

Depois da atualização:

dss.run\_command("solve")

---

# **12\. Medição da Potência no PCC**

A potência da interface com a rede é medida:

P\_pcc \= dss.Circuit.TotalPower()\[0\]

Esse valor representa importação ou exportação.

---

# **13\. Envio da Medição ao PLC**

A medição simulada pode ser enviada ao PLC:

write\_modbus\_register(30001, P\_pcc)

O PLC então usa essa medição no algoritmo de controle.

---

# **14\. Simulação de Radiância**

A geração solar pode variar com irradiância.

No OpenDSS isso pode ser feito com **Loadshape**:

New Loadshape.SolarShape npts=3600 interval=1 mult=(...)  
New PVSystem.Usina daily=SolarShape

Ou atualizando via Python.

---

# **15\. Simulação de Múltiplos Inversores**

A usina pode ser modelada como:

### **1 inversor equivalente**

mais simples.

### **vários inversores individuais**

mais realista.

Exemplo:

PVSystem.Inv1  
PVSystem.Inv2  
PVSystem.Inv3

---

# **16\. Sincronização Temporal**

O simulador deve respeitar o **tempo de ciclo do PLC**.

Exemplo:

PLC ciclo \= 500 ms

O loop da simulação também deve rodar a cada 500 ms.

Caso contrário a dinâmica do controle será irreal.

---

# **17\. Estrutura do Loop de Simulação**

loop:

1 ler setpoint do PLC  
2 atualizar usina no OpenDSS  
3 resolver rede  
4 medir potência no PCC  
5 enviar medição ao PLC  
6 aguardar próximo ciclo

---

# **18\. Estrutura de Controle de Exportação**

O controlador normalmente usa:

\[  
P\_{export} \= P\_{geração} \- P\_{carga}  
\]

Erro:

\[  
e \= P\_{PCC} \- P\_{limite}  
\]

Controle proporcional-integral:

\[  
P\_{novo} \= P\_{atual} \- (K\_p e \+ K\_i \\int e dt)  
\]

Esse algoritmo roda no PLC.

---

# **19\. Simulação de Comportamento Real**

Para fidelidade é importante incluir:

* variação de carga  
* variação de irradiância  
* rampa de potência do inversor  
* atraso de comunicação  
* filtragem de medição

Sem isso o controle parecerá artificialmente estável.

---

# **20\. Pontos Técnicos Críticos**

É necessário garantir:

1. Limite de rampa de potência dos inversores  
2. Simulação de atraso de resposta do inversor  
3. Filtro de medição de potência  
4. Tempo de resolução do OpenDSS menor que o ciclo do PLC

Se o `solve` demorar mais que o ciclo do PLC, a simulação perde validade.

---

# **21\. Resultado Final**

O sistema completo se comporta como um **gêmeo digital da usina** conectado ao controlador real.

Ele permite testar:

* controle de exportação  
* variação rápida de carga  
* saturação de inversores  
* perda de comunicação  
* instabilidade de controle  
* limites de exportação

Tudo **sem necessidade de uma usina real em campo**.

---

# **22\. Conclusão**

Sim, é totalmente possível:

* Receber setpoints do PLC via RS485  
* Simular uma usina completa em Linux  
* Usar OpenDSS para resolver a rede  
* Medir potência no PCC  
* Enviar medições de volta ao PLC

Esse arranjo constitui um **simulador de planta elétrica conectado ao controlador real**, permitindo validar o algoritmo de controle de exportação com alta fidelidade antes da implantação em campo.

