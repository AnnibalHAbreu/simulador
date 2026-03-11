## **Simulador de Usina Fotovoltaica – Contexto Completo**

# **1\. Arquitetura Física**

## **Hardware**

* Raspberry Pi 4 com Linux

* Placa Waveshare RS232/RS485/CAN HAT

* Duas portas RS485 independentes:

* Comunicação serial 9600 sem paridade, 1 stop bit

### **RS485 COM1**

* 1 medidor (Modbus slave)

* 9 inversores (Modbus slave)

### **RS485 COM2**

* 9 inversores (Modbus slave)

Total: 18 inversores \+ 1 medidor  
O controlador real é o Master.  
Todos os dispositivos simulados são Slaves Modbus RTU.

**Modelo elétrico**  
\- Sistema trifásico em 380 V LL em baixa tensão e 13800V no lado de média tensão.  
\- medição por fase de tensões, correntes e cosseno phi no ponto de conexão do lado de MT.  
\- Rede upstream no ponto de conexão modelada por equivalente de Thévenin trifásico (Vth \+ Zth por fase), com opção de desbalanceamento.  
\- Como não há dados de campo, adote valores típicos (e parametrizáveis) de nível de curto-circuito e X/R; documente claramente as suposições.  
\- Carga local modelada como ZIP trifásica parametrizável:  
  \- composição padrão: 30% Z, 30% I, 40% P;  
  \- permitir parametrizar magnitude e fator de potência (ou P/Q) de cada parcela Z, I e P.

**Requisitos temporais**  
\- Simulação com passo de 10 ms (Ts \= 10 ms).  
\- Ciclo de controle do controlador: 2 s (atualização de setpoints/objetivos e lógicas de maior nível).  
\- Incluir atrasos/filtros mínimos de medição e atuação quando necessários para evitar “controlador perfeito”.  
\- considerar modelo de primeira ordem para os inversores com atraso típico de inversores de potência abaixo de 300 kW

\#\# Dinâmica por inversor  
\- Ativo: \`P\[k\] \= sat(P\[k-1\] \+ α(P\_ref \- P\[k-1\]), 0, u·P\_nom)\`  
\- Reativo: \`Q\[k\] \= sat(Q\[k-1\] \+ β(Q\_ref \- Q\[k-1\]), \-√(S\_nom^2 \- P^2), \+√(S\_nom^2 \- P^2))\`

\#\# Agregação e PCC  
\- \`P\_gen \= Σ P\_i\`, \`Q\_gen \= Σ Q\_i\`  
\- \`P\_PCC \= Load\_P \- P\_gen\`, \`Q\_PCC \= Load\_Q \- Q\_gen\`  
\- \`S\_PCC \= √(P\_PCC^2 \+ Q\_PCC^2)\`  
\- Fases (equilíbrio): \`Pφ \= P\_PCC/3\`, \`Qφ \= Q\_PCC/3\`, \`Sφ \= √(Pφ^2 \+ Qφ^2)\`  
\- Correntes: \`I\_total \= S\_PCC·1000 / (√3·V\_LL)\`, \`Iφ \= Sφ·1000 / V\_LN\`

---

# **2\. Finalidade do Simulador**

O simulador deve:

* Responder requisições Modbus do controlador  
* Simular dinamicamente a potência FV dos inversores  
* Disponibilizar medições do ponto de conexão (PCC)  
* Permitir cenários realistas de variação de irradiância (energia disponível)  
* Aceitar comandos Modbus FC16 para aplicar setpoints, aplicando 1 registro apenas por acesso  
* Rodar em tempo real (típico: 2 segundo)  
* Operar nas duas RS485 ao mesmo tempo

---

# **3\. Modelo dos Inversores**

## **3.1 Energia Disponível (u\[k\])**

Variável externa:

u\_i\[k\] ∈ \[0, 1\]

Potência máxima permitida:

P\_avail,i\[k\] \= u\_i\[k\] \* P\_nom,i

## **3.2 Dinâmica de Primeira Ordem com Saturação**

Cada inversor i é modelado por:

P\_i\[k\] \= sat( P\_i\[k-1\] \+ α\_i \* (P\_ref,i\[k-1\] \- P\_i\[k-1\]),  0,   P\_avail,i\[k\])

Onde:

* P\_i\[k\] \= potência entregue

* P\_ref,i\[k\] \= setpoint Modbus

* α\_i \= coeficiente dinâmico (0.1–0.4)

## **3.3 Registradores dos Inversores**

* Setpoint da potência nominal (%) \- endereço 256

Faixa de valores: 0 \- 100%  
Função: Define percentual de potência ativa nominal

* Fator de potência (FP) \- \- endereço 257

  \- \*\*Tipo de dado:\*\* U16 (unsigned 16-bit)

  \- \*\*Unidade:\*\* Adimensional

  \- \*\*Faixa de valores:\*\* \[1-20\] ou \[80-100\]

  \- \*\*Valores entre 21-79 são INVÁLIDOS\*\*


  Decodificação \- Modo LAGGING (Indutivo)

  \*\*Valores 1-20:\*\* Fator de potência \*\*indutivo\*\* (corrente atrasada em relação à tensão)


  | Valor Escrito | Fator de Potência Real | Comportamento |

  | 1 | 0.99 lagging | Inversor consome reativos |

  | 5 | 0.95 lagging | Inversor consome reativos |

  | 10 | 0.90 lagging | Inversor consome reativos |

  | 20 | 0.80 lagging | Inversor consome reativos |


  \*\*Fórmula aproximada:\*\* \`PF ≈ 1\. 00 \- (valor × 0.01)\`


  Decodificação \- Modo LEADING (Capacitivo)


  \*\*Valores 80-100:\*\* Fator de potência \*\*capacitivo\*\* (corrente adiantada em relação à tensão)


  | Valor Escrito | Fator de Potência Real | Comportamento |

  | 80 | 0.80 leading | Inversor injeta reativos |

  | 90 | 0.90 leading | Inversor injeta reativos |

  | 95 | 0.95 leading | Inversor injeta reativos |

  | 100 | 1.00 (unitário) | Sem troca de reativos |


  \*\*Fórmula:\*\* \`PF \= valor / 100\`


  

Mapa Modbus RTU (Holding Registers)  
\- 1 registro por variável unsigned 16-bit  
\- Palavra alta no registrador de base; palavra baixa no registrador seguinte.

| Potência Ativa Nominal kW | Potência Aparente VA | Endereço modbus |
| :---- | :---- | :---- |
| 60 | 60 | 101 |
| 60 | 60 | 102 |
| 35 | 35 | 103 |
| 15 | 15 | 104 |
| 15 | 15 | 105 |
| 15 | 15 | 106 |
| 15 | 15 | 107 |
| 15 | 15 | 108 |
| 15 | 15 | 109 |
| 15 | 15 | 201 |
| 15 | 15 | 202 |
| 15 | 15 | 203 |
| 15 | 15 | 204 |
| 15 | 15 | 205 |
| 15 | 15 | 206 |
| 35 | 35 | 207 |
| 35 | 35 | 208 |
| 50 | 50 | 209 |

Comandos suportados:

* FC16 (Write Multiple Registers), um registro por vez

---

# **4\. Modelo do Medidor – Ponto de Conexão (PCC)**

O medidor simulado deve calcular:

P\_PCC\[k\] \= P\_load\[k\] – Σ P\_i\[k\]

Legenda:

* P\_PCC \> 0 → consumo e P\_PCC \< 0  → injeção

Endereço modbus RTU \= 100

Leitura única a partir do endereço 0099H, sendo 14 registros \- 28 words

Variável, tipo de dado, endereço modbus, observação  
PFa    	    : REAL := 0.0; // 0099H 	Valor positivo: 0…16384 × (1/16384) e   
Valor negativo: 49151…65535 \= \-((65535 \- valor lido) / 16384\)  
PFb    	    : REAL := 0.0; // 009AH 	Valor positivo: 0…16384 × (1/16384) e   
Valor negativo: 49151…65535 \= \-((65535 \- valor lido) / 16384\)  
PFc    	    : REAL := 0.0; // 009BH 	Valor positivo: 0…16384 × (1/16384) e   
Valor negativo: 49151…65535 \= \-((65535 \- valor lido) / 16384\)  
Reserved01  : REAL;        // 009CH \- sem informação  
Reserved02  : REAL;        // 009DH \- sem informação  
Reserved03  : REAL;        // 009EH \- sem informação  
Reserved04  : REAL;        // 009FH \- sem informação		  
Ia    	    : REAL := 0.0; // 00A0H \- 12…25.600 × (1/256) A (multiplicar por RTC)  
Ib    	    : REAL := 0.0; // 00A1H \- 12…25.600 × (1/256) A (multiplicar por RTC)  
Ic    	    : REAL := 0.0; // 00A2H \- 12…25.600 × (1/256) A (multiplicar por RTC)	  
Reserved05  : REAL;        // 00A3H \- sem informação  
Ua    	    : REAL := 0.0; // 00A4H \- 256…64.000 × (1/128) Vca (multiplicar por RTP)  
Ub    	    : REAL := 0.0; // 00A5H \- 256…64.000 × (1/128) Vca (multiplicar por RTP)  
Uc    	    : REAL := 0.0; // 00A6H \- 256…64.000 × (1/128) Vca (multiplicar por RTP)

# **5\. Comportamento do Controlador Real**

O controlador executa sempre a sequência:

1. Ler medidor (FC03)  
2. Calcular controle de exportação  
3. Escrever setpoints nos inversores (FC16)  
4. Repetir continuamente

As RS485 funcionam em paralelo, com múltiplos slaves em cada porta.

---

# **6\. Configurações do Simulador**

O simulador deve permitir configurar:

### **6.1 Parâmetros Variáveis**

* Energia disponível u\[k\] por tempo  
* Potência nominal de cada inversor  
* α individual por inversor  
* Carga fixa ou dinâmica no PCC

### **6.2 Formatos de Configuração**

* CSV

### **6.3 Eventos Especiais Simuláveis**

* Falha em inversor  
* Saturação  
* Resposta lenta  
* Travamento momentâneo  
* Perda de comunicação Modbus simulada  
* Comportamento assimétrico entre inversores

---

# **7\. Funcionalidades Obrigatórias**

## **7.1 Núcleo de Simulação**

* Atualizar P\_i de todos os inversores  
* Calcular potência total  
* Atualizar medidor do PCC

## **7.2 Servidores Modbus RTU**

* Dois servidores independentes  
* Múltiplos slave IDs em cada porta  
* Respostas não bloqueantes  
* Suporte a FC03 e FC16  
* Mapeamento configurável de registradores

## **7.3 Scheduler em Tempo Real**

* Passo de 1 segundo (ou parametrizável)  
* Threads independentes para COM1 e COM2  
* Logs opcionais para auditoria

---

