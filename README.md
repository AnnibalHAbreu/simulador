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
