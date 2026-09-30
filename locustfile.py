"""Teste de carga (Prática 2).

Execução com interface web (usada no pitch, ao vivo):
    locust -f locustfile.py --host https://SEU-SERVICO.onrender.com
    -> abrir http://localhost:8089, definir usuários e taxa de spawn, iniciar.

Execução headless (gera CSV + relatório HTML com gráficos para o PDF):
    # Linha de base local (container em http://localhost:5000), 50 usuários
    locust -f locustfile.py --headless --host http://localhost:5000 \
           -u 50 -r 5 -t 2m --csv resultados/local_50u --html resultados/local_50u.html

    # Estresse na nuvem pública, 200 usuários
    locust -f locustfile.py --headless --host https://SEU-SERVICO.onrender.com \
           -u 200 -r 10 -t 3m --csv resultados/nuvem_200u --html resultados/nuvem_200u.html

IMPORTANTE: rode contra o serviço em MODO=mock. No modo "real" cada requisição gasta
créditos do Gemini e bate no limite do provedor (HTTP 429), medindo o provedor e não a sua infra.
"""
import os
import random

from locust import HttpUser, between, task

CONSULTAS = [
    "carga horaria computacao em nuvem",
    "ementa sistemas distribuidos",
    "estagio supervisionado",
    "virtualizacao e servidores de aplicacoes",
    "trabalho de conclusao de curso",
    "media semestral aprovacao",
    "inteligencia artificial ementa",
    "atividades complementares horas",
    "rede de computadores",
    "perfil do egresso",
]

PROMPTS = [
    "Qual a carga horaria de Computacao em Nuvem?",
    "Quais disciplinas existem no 7o periodo?",
    "Como funciona o estagio obrigatorio?",
]


class UsuarioAPI(HttpUser):
    # Tempo de "reflexão" do usuário virtual entre requisições (segundos).
    # Vazão máx. aproximada = usuários / tempo médio de espera. Para saturar o servidor,
    # reduza: WAIT_MIN=0.1 WAIT_MAX=0.3 locust -f locustfile.py ...
    wait_time = between(float(os.getenv("WAIT_MIN", "0.5")), float(os.getenv("WAIT_MAX", "1.5")))

    @task(3)
    def healthcheck(self):
        # O(1): resposta de tamanho constante
        self.client.get("/", name="GET /")

    @task(4)
    def buscar_ppc(self):
        # RAG puro (BM25): trabalho de CPU proporcional a |consulta| x |trechos|
        q = random.choice(CONSULTAS)
        with self.client.get("/buscar", params={"q": q, "k": 3},
                             name="GET /buscar", catch_response=True) as r:
            if r.status_code != 200:
                r.failure(f"status {r.status_code}")
            elif not r.json().get("resultados"):
                r.failure("busca sem resultados")

    @task(2)
    def predict(self):
        # escrita em memória (append O(1) amortizado) protegida por lock
        payload = {"prompt": random.choice(PROMPTS), "tenant_id": f"t{random.randint(1, 20)}"}
        with self.client.post("/predict", json=payload,
                              name="POST /predict", catch_response=True) as r:
            if r.status_code != 201:
                r.failure(f"status {r.status_code}")
