# Relatório — Prática 1: Docker e Deploy em PaaS (máx. 2 páginas)

**Disciplina:** Computação em Nuvem e SOA — IFPA Campus Ananindeua (2026.2) · **Professor:** Fábio Ferreira
**Equipe:** ⟦PREENCHER nomes e matrículas⟧ · **Trilha:** Integrada (API com agente ReAct + RAG sobre o PPC)

## 1. Entregáveis
| Item | Evidência |
|---|---|
| Repositório público (Dockerfile, app.py, requirements.txt, .dockerignore) | ⟦PREENCHER: https://github.com/Gabriel-Aian/ifpa-nuvem-pratica1-Gabriel-Aian⟧ |
| URL pública em HTTPS | ⟦PREENCHER: https://NOME.onrender.com⟧ |
| Plataforma PaaS | Render (plano gratuito, runtime Docker) |

## 2. Arquitetura e decisões de engenharia
- **Imagem:** `python:3.12-alpine` (base mínima, ~50 MB), dependências instaladas antes do código para reaproveitar cache de camadas, `pip --no-cache-dir`.
- **Servidor:** Gunicorn (WSGI de produção) com 2 workers × 4 threads; porta lida de `$PORT` (contrato do PaaS), padrão 5000 localmente.
- **Segurança:** container como usuário não-root; segredo (chave da API) só em variável de ambiente; HTTPS gerenciado pela plataforma; validação de entrada e cabeçalhos de segurança.
- **`.dockerignore`:** exclui `.git`, `.env`, PDFs, ambientes virtuais e materiais de teste, reduzindo contexto de build e evitando vazamento de arquivos.
- **Agente:** `/predict` (mock, usado nos testes de carga) e `/agente` (ReAct + BM25 sobre o PPC + Gemini). O LLM é acessado por API porque um modelo local não cabe nos ~512 MB do plano gratuito.
- **Por que Render:** deploy direto do Dockerfile via GitHub, HTTPS automático e sem cartão; AWS App Runner está fechado a novos clientes e o plano gratuito do Azure derruba o app ao estourar a cota.

## 3. Evidências
**Figura 1 — Container rodando localmente** (`docker run`, saída de `docker ps` e `curl http://localhost:5000/`)
⟦INSERIR PRINT⟧

**Figura 2 — Resposta HTTP 200 OK na nuvem pública** (navegador com cadeado HTTPS ou `curl -i https://NOME.onrender.com/`)
⟦INSERIR PRINT⟧

**Figura 3 (opcional) — Agente respondendo sobre o PPC** (`POST /agente` com `passos` e `fontes`)
⟦INSERIR PRINT⟧

## 4. Limitações conhecidas
Plano gratuito desliga o serviço após ~15 min ocioso (cold start ≈ 1 min); estado em memória não é compartilhado entre workers nem sobrevive a reinícios (solução de produção: Postgres/Redis).
