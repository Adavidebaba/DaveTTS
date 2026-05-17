FROM python:3.12-slim

# Installa ffmpeg (necessario per pydub / merge audio)
RUN apt-get update && \
    apt-get install -y --no-install-recommends ffmpeg && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Installa dipendenze Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copia codice applicazione
COPY backend/ ./backend/
COPY frontend/ ./frontend/

# Crea directory dati
RUN mkdir -p /app/data/uploads /app/data/output /app/data/temp

# Porta esposta
EXPOSE 4300

# Avvio server
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "4300"]
