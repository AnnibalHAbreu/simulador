# Modelagem Simplificada de Inversores Solares com Entrada de Irradiância
Abordagem orientada a simulação e sistemas de controle (SCRPI / Não Injeção)

---

## 1. Objetivo do Documento

Este documento descreve um modelo matemático simplificado para representar um conjunto de inversores solares conectados em paralelo em um mesmo barramento CA, permitindo a introdução controlada de uma variável que representa a energia disponível proveniente dos painéis fotovoltaicos.

O objetivo principal é possibilitar:
- Simulação dinâmica do sistema
- Testes de algoritmos de controle de não injeção (SCRPI)
- Avaliação do comportamento frente a variações rápidas de geração
- Observação do impacto no ponto de conexão com a rede (PCC)

O modelo prioriza simplicidade, controle e fidelidade suficiente ao comportamento real dos inversores.

---

## 2. Conceito Fundamental do Modelo

A irradiância solar não é utilizada como referência de controle. Ela atua exclusivamente como um fator limitante da potência máxima que cada inversor pode fornecer.

No modelo proposto:
- O controlador define o setpoint de potência
- A energia disponível limita o valor máximo realizável
- A irradiância é tratada como um distúrbio externo não controlável

---

## 3. Variável de Disponibilidade de Energia

Para cada inversor i define-se uma variável adimensional:

$$
u_i[k] \in [0,1]
$$

Onde:
- u_i = 1 representa plena disponibilidade de energia
- u_i = 0 representa ausência total de geração
- valores intermediários representam geração parcial

Essa variável é fornecida externamente ao modelo e pode ser manipulada livremente para fins de ensaio e simulação.

---

## 4. Potência Máxima Disponível por Inversor

A potência máxima disponível para cada inversor é definida como:

$$
P_{avail,i}[k] = u_i[k] * P_{nom,i}
$$

Onde:
- P_nom,i é a potência nominal do inversor i
- P_avail,i[k] representa o limite superior de geração naquele instante

Essa grandeza agrega de forma simplificada os efeitos de irradiância, potência DC instalada, MPPT e perdas do lado DC.

---

## 5. Modelo Dinâmico do Inversor

Cada inversor é modelado como um sistema discreto de primeira ordem com saturação, adequado para uma taxa de amostragem típica de 1 segundo.

### 5.1 Equação dinâmica

$$
P_i[k] = sat(P_i[k-1] + \alpha_i * (P_{ref,i}[k-1] - P_i[k-1]), 0, P_{avail,i}[k])
$$

Onde:
- P_i[k] é a potência ativa efetivamente entregue pelo inversor
- P_ref,i[k] é o setpoint de potência fornecido pelo controlador
- α_i é o coeficiente dinâmico do inversor (tipicamente entre 0,1 e 0,4)
- sat(x,a,b) limita x ao intervalo [a,b]

---

## 6. Interpretação Física do Modelo do Inversor

Esse modelo representa de forma agregada:
- Atrasos internos de processamento
- Rampas internas de potência
- Limitação por potência disponível no lado DC
- Saturações impostas por limites do equipamento

Não há tentativa de modelar MPPT, corrente ou tensão individualmente.

---

## 7. Modelo Agregado do Sistema de Inversores

A potência total gerada pelo conjunto de inversores conectados em paralelo é dada por:

$$
P_{gen}[k] = P_1[k] + P_2[k] + ... + P_N[k]
$$

Onde N é o número total de inversores.

---

## 8. Modelo do Ponto de Conexão com a Rede (PCC)

A potência ativa medida no ponto de conexão com a rede é:

$$
P_{PCC}[k] = P_{load}[k] - P_{gen}[k]
$$

Convenção de sinais:
- P_PCC > 0 indica consumo da rede
- P_PCC < 0 indica injeção de potência na rede

Esse é o sinal utilizado pelo controlador SCRPI.

---

## 9. Distribuição de Setpoints entre Inversores

O setpoint total calculado pelo controlador pode ser distribuído proporcionalmente à potência nominal de cada inversor:

$$
P_{ref,i}[k] = P_{ref,total}[k] * (P_{nom,i} / \sum P_{nom})
$$

Essa estratégia garante:
- Compartilhamento equilibrado de carga
- Evita saturação prematura de inversores menores
- Comportamento previsível do conjunto

---

## 10. Casos de Uso e Ensaios Possíveis

Com esse modelo é possível simular:
- Passagem rápida de nuvens (variação abrupta de u_i)
- Falha ou degradação parcial de inversores
- Assimetria de geração entre inversores
- Transições suaves ou abruptas de geração
- Robustez do controle de não injeção

---

## 11. Vantagens da Abordagem

- Modelo simples e computacionalmente leve
- Totalmente controlável para ensaios
- Independente de modelos detalhados de painéis fotovoltaicos
- Fácil implementação em Python, CODESYS ou CLPs
- Representa com boa fidelidade o comportamento real para fins de controle

---

## 12. Conclusão

A representação da irradiância solar como uma variável externa de disponibilidade de potência permite um modelo limpo, robusto e adequado para simulação e desenvolvimento de sistemas de controle.

Essa abordagem fornece o grau de realismo necessário para projetos de SCRPI e EMS, evitando complexidade excessiva e mantendo total domínio sobre os cenários de teste.

---
