# Roteiro do Pitch — 01/10/2026 (10 min: 7 min + 3 min de arguição)

## Checklist 15 min antes
- [ ] `curl https://<nome>.onrender.com/health` para **acordar o serviço** (cold start ~1 min no plano gratuito)
- [ ] Abas abertas: URL pública (`/`), painel do Render (Metrics/Logs), Locust (`localhost:8089`), repositório no GitHub
- [ ] Locust já iniciado com `--host https://<nome>.onrender.com`, campos preenchidos (200 usuários, spawn 10/s)
- [ ] Serviço em `MODO=mock` (Locust não deve chamar o Gemini)
- [ ] Chave do Gemini configurada no Render (para o `/agente`); teste 1 pergunta antes
- [ ] Plano B: HTML/PNG dos testes anteriores salvos localmente; 4G/hotspot caso a rede da sala falhe

## Etapa 1 — Arquitetura e URL ativa (2 min)
1. Mostrar `https://<nome>.onrender.com/` respondendo **200 OK em HTTPS** (cadeado no navegador).
2. Desenho: cliente → PaaS (TLS gerenciado) → container Alpine → Gunicorn → Flask → (BM25 local | Gemini externo).
3. Falar em 3 frases: *Dockerfile Alpine + usuário não-root; deploy contínuo via GitHub; estado em memória (serviço stateless).*
4. Demonstração rápida do agente: `POST /agente` com "Qual a carga horária de Computação em Nuvem e em que período é ofertada?" — mostrar `passos` (Pensamento → Ação → Observação) e `fontes`.

## Etapa 2 — Disparo ao vivo do Locust (3 min)
1. Iniciar o teste: 200 usuários, spawn 10/s, contra a URL pública.
2. Narrar enquanto sobe: *"estou rampando 10 usuários por segundo; em ~20 s chegamos a 200 simultâneos"*.
3. Apontar na aba **Statistics**: RPS, falhas, mediana, p95/p99 por endpoint (`GET /`, `GET /buscar`, `POST /predict`).

## Etapa 3 — Gráficos e limite físico (2 min)
1. Aba **Charts**: curva de RPS (sobe e estabiliza = **platô de vazão**), curva de tempo de resposta (p95 sobe quando a fila se forma), falhas/s.
2. Explicar: *p95 = 95% das requisições terminaram em até X ms; p99 captura a cauda (fila, cold start). A média esconde isso.*
3. Painel do Render (Metrics): CPU/memória da instância — *"a CPU compartilhada e fracionada do plano gratuito é o gargalo físico"*.
4. Dizer honestamente o que aconteceu com o auto-escalonamento (ver abaixo).

## Etapa 4 — Arguição (3 min) — respostas prontas

**Por que PaaS e não IaaS?**
PaaS abstrai SO, patching, balanceador e TLS; o time foca na aplicação e ganha deploy por `git push`. Em troca, perde controle fino de kernel/rede. IaaS daria controle total, mas exigiria gerir VM, firewall e certificados.

**Por que Render (e não AWS/Azure/Railway)?**
Deploy direto do Dockerfile via GitHub, HTTPS automático, sem cartão. AWS App Runner está fechado a novos clientes desde 30/04/2026; o plano gratuito do Azure App Service derruba o app (HTTP 403) ao estourar a cota de CPU; o Railway gratuito tem crédito mensal de ~US$ 1, insuficiente para teste de carga.

**Explique a Lei de Amdahl no seu resultado.**
Speedup = 1 / ((1 − p) + p/n), onde *p* é a fração paralelizável e *n* o número de unidades de processamento. Aqui a parte serial (1 − p) inclui o *lock* do `/predict`, o parsing/serialização JSON e o GIL do Python; e *n* é pequeno (2 workers sobre uma fração de CPU). Por isso dobrar usuários não dobra a vazão: o teto é `1/(1 − p)`. Com o agente real, a espera pela API externa é tempo serial do ponto de vista da requisição.

**Qual a complexidade (Big-O) dos endpoints?**
- `GET /` → O(1).
- `POST /predict` (mock) → O(1) amortizado (`append` em deque) + O(|prompt|) para validar/serializar.
- `GET /buscar` → O(|q| × N): para cada termo da consulta percorre os N = 158 trechos (BM25). É o endpoint CPU-bound.
- `POST /agente` → O(passos), no máximo 5 chamadas ao LLM; dominado por latência de rede (I/O-bound).

**Por que a latência p95/p99 explode sob 200 usuários?**
Quando a taxa de chegada ultrapassa a capacidade de atendimento, forma-se fila (Lei de Little: L = λ·W). A fila aumenta o tempo de espera de quem chega, o que afeta a cauda (p95/p99) muito antes da mediana. Se aparecerem erros (timeout/502), é esgotamento de conexões/CPU da instância.

**Qual o gargalo: CPU, RAM ou rede?**
Mostrar o painel do Render. Expectativa para este serviço: **CPU** (BM25 + JSON em instância fracionada). RAM é baixa (~dezenas de MB: 158 trechos indexados, deque limitado a 1000 itens). Rede não é o limite (respostas pequenas).

**Por que o serviço "dorme"? O que é cold start?**
Plano gratuito desliga o container após 15 min sem tráfego; a próxima requisição religa (~1 min). É o preço de um plano gratuito elástico "escala a zero".

**O plano gratuito escala automaticamente?**
Não horizontalmente: esse recurso existe em planos pagos. O que observamos é uma única instância saturando. Em produção: plano pago com autoscaling por CPU/latência + estado externo (banco/cache), já que hoje o estado vive na memória de cada worker.

**Por que o estado em memória é um problema em escala?**
Cada worker tem sua própria lista: IDs e histórico não são compartilhados entre workers/instâncias e somem a cada reinício. Solução: banco externo (Postgres/Redis). Mantivemos o `deque(maxlen=1000)` para não estourar a RAM sob carga.

**Por que não rodar LLM local?**
Um modelo quantizado de 1,5B parâmetros já ocupa ~1 GB só de pesos, acima dos ~512 MB do plano gratuito, e a CPU fracionada tornaria a geração lenta demais. Usamos API externa, transformando o custo em I/O.

**O que é ReAct e como se relaciona com o RAG?**
ReAct alterna raciocínio e ação: o modelo decide *o que buscar*, recebe a observação (trechos do PPC via BM25) e decide se responde ou refina a busca. O RAG é a ferramenta; o ReAct é a estratégia do agente.

**Como vocês protegeram a API?**
HTTPS pela plataforma, container não-root, segredo só em variável de ambiente, validação de entrada, limite de tamanho de prompt, cabeçalhos de segurança, contrapressão (máx. 3 chamadas simultâneas ao LLM por worker → 429) e memória limitada.

## Dica de ouro
Se algo falhar ao vivo (rede, cold start), não improvise em silêncio: diga o que está acontecendo ("o serviço está religando do cold start, é o comportamento esperado do plano gratuito"), mostre o HTML/prints do teste anterior como evidência e retome o disparo ao vivo em seguida. Isso ainda demonstra domínio técnico.
