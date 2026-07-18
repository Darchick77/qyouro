FROM python:3.11-slim

RUN apt-get update && apt-get install -y libdmtx-dev && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY backend/ backend/
COPY frontend/ frontend/
COPY bot/ bot/
COPY run.py .

ENV PORT=10000
CMD python run.py
