# Relatório Técnico — Prática 2: Testes de Carga com Locust (máx. 3 páginas)

**Equipe:** ⟦PREENCHER⟧ · **Serviço testado:** ⟦URL⟧ em `MODO=mock` · **Ferramenta:** Locust ⟦versão⟧

## 1. Metodologia
Cenário com 3 tarefas ponderadas por usuário virtual: `GET /` (peso 3, O(1)), `GET /buscar` (peso 4, RAG/BM25, CPU-bound) e `POST /predict` (peso 2, escrita em memória). Tempo de espera entre requisições: ⟦0,5–1,5 s ou o valor usado⟧.

| | Linha de base local | Estresse em nuvem pública |
|---|---|---|
| Ambiente | Docker na máquina da equipe (⟦CPU/RAM do seu PC⟧) | Render, plano gratuito |
| Usuários simultâneos | 50 | 200 |
| Taxa de spawn / duração | ⟦ ⟧ / ⟦ ⟧ | ⟦ ⟧ / ⟦ ⟧ |

## 2. Resultados
**Figura 1 — Gráficos do Locust, linha de base local (50 usuários):** ⟦INSERIR: RPS, tempo de resposta p50/p95, usuários⟧
**Figura 2 — Gráficos do Locust, nuvem pública (200 usuários):** ⟦INSERIR⟧

| Métrica | Local (50 u) | Nuvem (200 u) |
|---|---|---|
| Vazão média (RPS) | ⟦ ⟧ | ⟦ ⟧ |
| Latência mediana (ms) | ⟦ ⟧ | ⟦ ⟧ |
| Latência p95 (ms) | ⟦ ⟧ | ⟦ ⟧ |
| Latência p99 (ms) | ⟦ ⟧ | ⟦ ⟧ |
| Taxa de erro (%) | ⟦ ⟧ | ⟦ ⟧ |
| Total de requisições | ⟦ ⟧ | ⟦ ⟧ |

*(Fonte: `resultados/*_stats.csv` ou tabela "Statistics" do relatório HTML do Locust.)*

## 3. Análise de gargalos de infraestrutura
⟦PREENCHER com base nos seus dados e no painel Metrics do Render. Roteiro:⟧
- **CPU:** a CPU da instância gratuita é compartilhada/fracionada. Se a CPU ficou próxima do teto enquanto o RPS estabilizou, o gargalo é CPU (esperado: BM25 + serialização JSON).
- **RAM:** ⟦valor observado⟧ MB — baixa, pois o índice tem 158 trechos e o histórico é um `deque(maxlen=1000)`.
- **Conexões/rede:** ⟦houve timeouts, resets ou HTTP 5xx? em que momento?⟧ Respostas pequenas; a rede não é o limite.
- **Platô de vazão:** o RPS parou de crescer em ⟦valor⟧ com ⟦N⟧ usuários, enquanto p95/p99 subiram ⟦X×⟧ — sinal de saturação e formação de fila.

## 4. Fundamentação teórica
**Lei de Amdahl.** Speedup(n) = 1 / ((1 − p) + p/n), com *p* a fração paralelizável e *n* as unidades de processamento. O teto é 1/(1 − p). No serviço, a fração serial (1 − p) inclui o *lock* que protege o histórico do `/predict`, o parsing/serialização JSON e o GIL do Python; e *n* é pequeno (2 workers sobre CPU fracionada). Logo, quadruplicar usuários (50 → 200) não quadruplica a vazão; estimativa a partir dos dados: com speedup observado S = ⟦RPS nuvem / RPS local ajustado⟧ e n = ⟦ ⟧, p ≈ ⟦(1 − 1/S)/(1 − 1/n)⟧.

**Complexidade assintótica (Big-O).**
| Endpoint | Custo | Observação |
|---|---|---|
| `GET /` | O(1) | resposta de tamanho constante |
| `POST /predict` (mock) | O(1) amortizado + O(\|prompt\|) | `append` em deque; validação/serialização lineares no tamanho do prompt |
| `GET /buscar` | O(\|q\| · N), N = 158 | percorre todos os trechos por termo: é o endpoint CPU-bound |
| `POST /agente` | O(passos) ≤ 5 chamadas ao LLM | dominado por latência de rede (I/O-bound) |

**Latência percentil e filas.** p95/p99 medem a cauda da distribuição; sob saturação a taxa de chegada excede a de serviço e forma-se fila (Lei de Little, L = λ·W), o que eleva p95/p99 muito antes da mediana.

## 5. Avaliação do auto-escalonamento elástico
O plano gratuito do Render executa **uma única instância** e não faz escalonamento horizontal (recurso de planos pagos); a elasticidade disponível é "escalar a zero" após 15 min de inatividade, com *cold start* de ≈ 1 min. ⟦Descrever o que foi observado: a primeira requisição após inatividade demorou X s; durante o pico não surgiram novas instâncias; p95 subiu de X para Y ms⟧. Em produção: plano pago com autoscaling por CPU/latência, estado externo (Postgres/Redis) e balanceador.

## 6. Conclusão
⟦2–3 frases: capacidade máxima sustentada (RPS) sem erros, onde o p95 passou do aceitável, principal gargalo e recomendação.⟧
