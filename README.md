# Prática 1 e 2 — Computação em Nuvem e SOA (IFPA Ananindeua, 2026.2)

API Flask containerizada (Docker/Alpine) publicada em PaaS, com agente de IA **ReAct + RAG**
sobre o PPC do curso de Bacharelado em Ciência da Computação, e teste de carga com **Locust**.

## Arquitetura

```
Cliente / Locust ──HTTPS──> PaaS (Render) ──> Container Alpine
                                               └─ Gunicorn (2 workers x 4 threads)
                                                  └─ Flask app.py
                                                     ├─ GET  /          healthcheck
                                                     ├─ GET  /buscar    RAG puro (BM25, CPU-bound)
                                                     ├─ POST /predict   mock (MODO=mock) ou agente (MODO=real)
                                                     ├─ POST /agente    agente ReAct real (Gemini)
                                                     └─ rag.py + agent.py + chunks.json (PPC indexado)
                                                                       └──HTTPS──> API Gemini (I/O externo)
```

- **RAG:** `ingest_ppc.py` divide o PPC (158 trechos: 1 por disciplina do ementário + seções) e gera
  `chunks.json`. A busca é **BM25 em Python puro** (`rag.py`): sem dependências extras e leve
  para o plano gratuito.
- **ReAct:** `agent.py` executa o laço *Pensamento → Ação (`buscar_ppc`) → Observação → Resposta final*
  (máx. 4 buscas) chamando o Gemini por REST.
- **Modos:** `MODO=mock` (padrão) não usa LLM; é o que se estressa no Locust.
  `/agente` sempre usa o agente real (demonstração).

## Estrutura

| Arquivo | Função |
|---|---|
| `app.py` | API Flask (endpoints, validação, cabeçalhos de segurança) |
| `rag.py` | Busca BM25 sobre os trechos do PPC |
| `agent.py` | Agente ReAct + cliente Gemini |
| `chunks.json` | PPC indexado (gerado por `ingest_ppc.py`) |
| `ingest_ppc.py` | Extração/chunking do PPC (offline) |
| `Dockerfile` / `.dockerignore` | Imagem Alpine, usuário não-root, `$PORT` do PaaS |
| `locustfile.py` | Cenários de carga (Prática 2) |

## Rodar localmente com Docker

```bash
docker build -t ifpa-nuvem .
docker run --rm -p 5000:5000 ifpa-nuvem
curl http://localhost:5000/
curl "http://localhost:5000/buscar?q=carga+horaria+computacao+em+nuvem"
curl -X POST http://localhost:5000/predict -H "Content-Type: application/json" \
     -d '{"prompt":"Qual a carga horária de Computação em Nuvem?","tenant_id":"t1"}'
```

Para testar o agente real localmente:

```bash
docker run --rm -p 5000:5000 -e GEMINI_API_KEY=SUA_CHAVE -e GEMINI_MODEL=gemini-3.1-flash-lite ifpa-nuvem
curl -X POST http://localhost:5000/agente -H "Content-Type: application/json" \
     -d '{"prompt":"Qual a carga horária de Computação em Nuvem e em que período é ofertada?"}'
```

> Confira no painel do Google AI Studio qual é o nome do modelo barato disponível para a sua chave
> e ajuste `GEMINI_MODEL` se necessário.

## Deploy no Render (plano gratuito)

1. Em render.com: **New → Web Service → Build and deploy from a Git repository** e conecte este repositório.
2. **Language/Runtime: Docker** (o Render detecta o `Dockerfile`). **Instance Type: Free**.
3. Em **Environment Variables** adicione:
   - `MODO=mock`
   - `GEMINI_API_KEY=...` (só para o `/agente`; **nunca** commitar a chave)
   - `GEMINI_MODEL=gemini-3.1-flash-lite`
4. Em **Advanced → Health Check Path:** `/health`.
5. **Create Web Service.** Ao terminar o build, a URL `https://<nome>.onrender.com` já responde em HTTPS.

O plano gratuito desliga o serviço após ~15 min sem tráfego; o primeiro acesso leva cerca de 1 min.
**Acorde o serviço antes do pitch** (`curl https://<nome>.onrender.com/health`).

## Teste de carga (Locust)

```bash
pip install -r requirements-locust.txt
mkdir resultados

# Linha de base local (container em localhost:5000) — 50 usuários
locust -f locustfile.py --headless --host http://localhost:5000 \
       -u 50 -r 5 -t 2m --csv resultados/local_50u --html resultados/local_50u.html

# Estresse na nuvem pública — 200 usuários
locust -f locustfile.py --headless --host https://<nome>.onrender.com \
       -u 200 -r 10 -t 3m --csv resultados/nuvem_200u --html resultados/nuvem_200u.html

# Interface web (para o pitch ao vivo): http://localhost:8089
locust -f locustfile.py --host https://<nome>.onrender.com
```

O HTML gerado traz os gráficos (RPS, tempos de resposta p50/p95, usuários) e a tabela de percentis,
prontos para entrar no relatório. Para saturar a instância, reduza o tempo de espera:
`WAIT_MIN=0.1 WAIT_MAX=0.3 locust ...`.

## Segurança

- HTTPS terminado pela plataforma; container roda como usuário **não-root**.
- Chave da API somente por variável de ambiente (nunca no repositório).
- Validação de entrada (JSON inválido, prompt vazio ou acima de 500 caracteres → 400).
- Cabeçalhos `X-Content-Type-Options`, `X-Frame-Options` e `Cache-Control: no-store`.
- Contrapressão no agente: no máximo 3 chamadas simultâneas ao LLM por worker (HTTP 429 acima disso).
- Memória limitada: histórico de transações em `deque(maxlen=1000)`.
