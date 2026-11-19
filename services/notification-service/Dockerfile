FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends \
    curl dnsutils iputils-ping \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY app.py start.sh ./
RUN chmod +x start.sh && mkdir -p /data

EXPOSE 5002 5444
CMD ["./start.sh"]
