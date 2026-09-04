# Passo 1: Imagem base minimalista de Python com Alpine Linux
FROM python:3.9-alpine

# Passo 2: Estabelecer o diretório de trabalho isolado dentro do container
WORKDIR /app

# Passo 3: Copiar o requirements e instalar dependências sem salvar cache em disco
COPY requirements.txt requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# Passo 4: Copiar o restante do código fonte do microsserviço
COPY app.py app.py

# Passo 5: Expor a porta lógica do container
EXPOSE 5000

# Passo 6: Comando padrão iniciando a API via Gunicorn WSGI Server em nível de produção
CMD ["gunicorn", "--bind", "0.0.0.0:5000", "app:app"]
