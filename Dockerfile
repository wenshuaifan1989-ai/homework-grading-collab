FROM python:3.11-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONUTF8=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

ARG DEBIAN_MIRROR
ARG PIP_INDEX_URL
RUN if [ -n "$DEBIAN_MIRROR" ]; then \
      sed -i "s|http://deb.debian.org/debian-security|${DEBIAN_MIRROR}-security|g; s|http://deb.debian.org/debian|${DEBIAN_MIRROR}|g" /etc/apt/sources.list.d/debian.sources; \
    fi

RUN apt-get update \
    && apt-get install -y --no-install-recommends libgl1 libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN python -m pip install --upgrade pip \
    && pip install -r requirements.txt

COPY . ./
RUN useradd --system --uid 10001 --create-home appuser \
    && mkdir -p /app/uploads \
    && chown -R appuser:appuser /app

USER 10001:10001
EXPOSE 8000

CMD ["gunicorn", "main:app", "-k", "uvicorn.workers.UvicornWorker", "-w", "2", "--bind", "0.0.0.0:8000", "--timeout", "120", "--access-logfile", "-", "--error-logfile", "-"]
