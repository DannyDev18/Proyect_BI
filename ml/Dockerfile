FROM python:3.11-slim

WORKDIR /app

RUN apt-get update && apt-get install -y gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# El servidor jupyter corre por defecto en puerto 8888
EXPOSE 8888

# Evitar ejecutar Jupyter desde root; para desarrollo local con volumen es seguro.
CMD ["jupyter", "lab", "--ip=0.0.0.0", "--port=8888", "--no-browser", "--allow-root", "--NotebookApp.token=''"]
