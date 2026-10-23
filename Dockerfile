FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DATA_DIR=/data RADIUS_CONFIG=/etc/freeradius/3.0
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends freeradius freeradius-utils openssl ca-certificates && rm -rf /var/lib/apt/lists/*
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY app ./app
COPY web ./web
COPY docker ./docker
RUN chmod +x /app/docker/entrypoint.sh
EXPOSE 8080 1812/udp 1813/udp
VOLUME ["/data"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/api/health',timeout=3)"
ENTRYPOINT ["/app/docker/entrypoint.sh"]
