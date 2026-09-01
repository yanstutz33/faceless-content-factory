FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    FACTORY_DATA_DIR=/app/data \
    FACTORY_HOST=0.0.0.0 \
    FACTORY_PORT=8787 \
    FFMPEG_PATH=ffmpeg \
    FFPROBE_PATH=ffprobe

RUN apt-get update \
    && apt-get install --yes --no-install-recommends ffmpeg curl ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && groupadd --gid 10001 ffactory \
    && useradd --uid 10001 --gid ffactory --create-home --shell /usr/sbin/nologin ffactory

WORKDIR /app

COPY requirements.txt ./
RUN pip install --no-cache-dir --requirement requirements.txt

COPY app.py ./
COPY factory ./factory
COPY web ./web
COPY assets ./assets

RUN mkdir -p /app/data \
    && chown -R ffactory:ffactory /app

USER ffactory

EXPOSE 8787
VOLUME ["/app/data"]

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
  CMD curl --fail --silent http://127.0.0.1:8787/healthz >/dev/null || exit 1

CMD ["python", "app.py", "serve"]

