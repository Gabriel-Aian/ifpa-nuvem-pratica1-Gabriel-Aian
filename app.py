"""API da Prática 1 - Computação em Nuvem e SOA (IFPA Ananindeua).

Endpoints
  GET  /          healthcheck (200) com modo de operação
  GET  /health    healthcheck mínimo (para o PaaS)
  POST /predict   contrato da trilha integrada. Segue a variável MODO (mock | real)
  POST /agente    sempre executa o agente real (ReAct + RAG + Gemini); usar na demonstração
  GET  /buscar    busca BM25 no PPC (somente RAG, sem LLM) -> endpoint CPU-bound p/ Locust
  GET  /pedidos   últimas transações registradas em memória (por tenant)

Variáveis de ambiente
  PORT                     porta injetada pelo PaaS (padrão 5000)
  MODO                     "mock" (padrão, sem custo/limite externo) ou "real" (ReAct + Gemini)
  GEMINI_API_KEY           chave da API (apenas no modo real; configurar no painel do PaaS)
  GEMINI_MODEL             modelo barato do Gemini (padrão gemini-3.1-flash-lite)
  MAX_LLM_CONCORRENTES     chamadas simultâneas ao LLM por worker (padrão 3)
"""
import datetime
import itertools
import os
import threading
from collections import deque

from flask import Flask, jsonify, request

from agent import ErroLLM, executar_react
from rag import BaseConhecimento

app = Flask(__name__)
app.json.ensure_ascii = False

MODO = os.environ.get("MODO", "mock").strip().lower()
MAX_PROMPT = 500

# Base de conhecimento carregada uma vez por worker (estado somente-leitura)
BASE = BaseConhecimento()

# "Banco" em memória, com limite para não crescer sem controle sob carga.
# Segregação lógica por tenant via campo tenant_id (multitenant simulado).
pedidos_armazenados = deque(maxlen=1000)
_contador = itertools.count(1)
_lock = threading.Lock()

# Contrapressão: limita chamadas simultâneas ao LLM (I/O externo) por worker
_llm_slots = threading.BoundedSemaphore(int(os.environ.get("MAX_LLM_CONCORRENTES", "3")))


def agora():
    return datetime.datetime.now().isoformat()


@app.after_request
def cabecalhos_seguranca(resp):
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["Cache-Control"] = "no-store"
    return resp


@app.route("/", methods=["GET"])
def healthcheck():
    return jsonify({
        "status": "Online",
        "timestamp": agora(),
        "ambiente": "Container Linux (Docker)",
        "disciplina": "Computacao em Nuvem e SOA - IFPA",
        "modo": MODO,
        "trechos_ppc": len(BASE.chunks),
        "endpoints": ["/predict [POST]", "/agente [POST]", "/buscar?q= [GET]",
                      "/pedidos [GET]", "/health [GET]"],
    }), 200


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"status": "ok"}), 200


# --- TRILHA INTEGRADA: agente de IA (ReAct + RAG sobre o PPC) ---
@app.route("/predict", methods=["POST"])
def predict():
    return _processar(MODO)


@app.route("/agente", methods=["POST"])
def agente():
    # sempre usa o agente real, independente de MODO (exige GEMINI_API_KEY)
    return _processar("real")


def _processar(modo):
    data = request.get_json(silent=True) or {}
    user_prompt = data.get("prompt")
    tenant_id = str(data.get("tenant_id", "default_tenant"))[:64]

    if not user_prompt or not isinstance(user_prompt, str) or not user_prompt.strip():
        return jsonify({"erro": "Bad Request", "mensagem": "Prompt ausente"}), 400
    if len(user_prompt) > MAX_PROMPT:
        return jsonify({"erro": "Bad Request",
                        "mensagem": f"Prompt excede {MAX_PROMPT} caracteres"}), 400

    detalhes = {}
    if modo == "real":
        if not _llm_slots.acquire(timeout=5):
            return jsonify({"erro": "Too Many Requests",
                            "mensagem": "Agente ocupado, tente novamente"}), 429
        try:
            detalhes = executar_react(user_prompt, BASE)
        except ErroLLM as e:
            return jsonify({"erro": "Bad Gateway", "mensagem": str(e)}), 502
        finally:
            _llm_slots.release()
        resposta = detalhes.pop("resposta")
        trilha = "Integrada - ReAct + RAG (PPC)"
    else:
        resposta = f"[AGENTE IA MOCK] Processando busca semantica para o prompt: '{user_prompt}'"
        trilha = "Integrada - Inteligencia Artificial (mock)"

    with _lock:
        transacao = {
            "id": next(_contador),
            "tenant_id": tenant_id,
            "prompt": user_prompt,
            "resposta_agente": resposta,
            "status_execucao": "Sucesso",
            "data_registro": agora(),
        }
        pedidos_armazenados.append(transacao)

    corpo = {"sucesso": True, "trilha": trilha, "modo": modo, "dados": transacao}
    if detalhes:
        corpo["agente"] = detalhes
    return jsonify(corpo), 201


# --- RAG puro (sem LLM): trabalho de CPU determinístico, ideal para o teste de carga ---
@app.route("/buscar", methods=["GET"])
def buscar():
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify({"erro": "Bad Request", "mensagem": "Parametro q ausente"}), 400
    try:
        k = max(1, min(int(request.args.get("k", 3)), 10))
    except ValueError:
        k = 3
    achados = BASE.buscar(q[:200], k=k)
    for a in achados:
        a["texto"] = a["texto"][:300]
    return jsonify({"consulta": q, "resultados": achados}), 200


@app.route("/pedidos", methods=["GET"])
def pedidos():
    tenant = request.args.get("tenant_id")
    with _lock:
        itens = [p for p in pedidos_armazenados if tenant is None or p["tenant_id"] == tenant]
    return jsonify({"total": len(itens), "ultimos": itens[-20:]}), 200


@app.errorhandler(404)
def nao_encontrado(_):
    return jsonify({"erro": "Not Found"}), 404


@app.errorhandler(405)
def metodo_invalido(_):
    return jsonify({"erro": "Method Not Allowed"}), 405


@app.errorhandler(500)
def erro_interno(_):
    return jsonify({"erro": "Internal Server Error"}), 500


if __name__ == "__main__":
    # Uso local/desenvolvimento. Em produção o Gunicorn sobe o app (ver Dockerfile).
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
