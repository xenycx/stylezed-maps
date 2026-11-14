# Stylized maps — the public site in one image: Python server + map engine + fonts + rsvg.
# Build:  docker build -t stylized-maps .
# Run:    docker run -p 8080:8080 -v maps-data:/data -e PUBLIC_URL=... -e GOOGLE_CLIENT_ID=... stylized-maps
FROM python:3.13-slim-trixie

RUN apt-get update \
 && apt-get install -y --no-install-recommends librsvg2-bin fontconfig ca-certificates tini \
 && rm -rf /var/lib/apt/lists/*
COPY --from=ghcr.io/astral-sh/uv:0.9 /uv /usr/local/bin/uv

WORKDIR /app
ENV UV_PROJECT_ENVIRONMENT=/opt/venv UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project && rm -rf /root/.cache

COPY . .
RUN FONTCONFIG_FILE=/app/fonts.conf fc-cache -f >/dev/null \
 && useradd -u 10001 -M -d /app maps \
 && mkdir -p /data \
 && rm -rf /app/data /app/out /app/var \
 && ln -s /data/places /app/data && ln -s /data/out /app/out \
 && chown -R maps:maps /data

ENV PATH=/opt/venv/bin:$PATH PYTHONUNBUFFERED=1 \
    HOST=0.0.0.0 PORT=8080 DATA_DIR=/data TRUST_PROXY=1 \
    OPENBLAS_NUM_THREADS=1 OMP_NUM_THREADS=1 MPLBACKEND=Agg
USER 10001
VOLUME /data
EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8080/healthz', timeout=4).status == 200 else 1)"
ENTRYPOINT ["tini", "--"]
CMD ["sh", "-c", "mkdir -p /data/places /data/out && exec python webapp/server.py"]
