# Passo 1: imagem base minimalista de Python com Alpine Linux
FROM python:3.12-alpine

# Não gera .pyc e não bufferiza logs (aparecem em tempo real no painel do PaaS)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Passo 2: diretório de trabalho isolado dentro do container
WORKDIR /app

# Passo 3: instalar dependências primeiro (aproveita cache de camadas) e sem cache de pip
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Passo 4: copiar apenas o que o serviço precisa (o resto é barrado pelo .dockerignore)
COPY app.py agent.py rag.py chunks.json ./

# Passo 5: rodar como usuário sem privilégios (princípio do menor privilégio)
RUN adduser -D -u 10001 appuser
USER appuser

# Passo 6: porta lógica do container. O PaaS injeta $PORT; localmente o padrão é 5000
EXPOSE 5000

# Passo 7: Gunicorn (WSGI de produção). Workers e threads ajustáveis por variável de ambiente
# Forma "sh -c" para expandir ${PORT}; "exec" repassa os sinais do Docker ao Gunicorn
CMD ["sh", "-c", "exec gunicorn --bind 0.0.0.0:${PORT:-5000} --workers ${WEB_CONCURRENCY:-2} --threads ${GUNICORN_THREADS:-4} --timeout 60 --access-logfile - app:app"]
