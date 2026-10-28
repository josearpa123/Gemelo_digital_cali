# syntax=docker/dockerfile:1
# Official SUMO image (Ubuntu 22.04, Python 3.10) + a Python 3.11 venv managed by uv.
FROM ghcr.io/eclipse-sumo/sumo:1.28.0 AS sim

COPY --from=ghcr.io/astral-sh/uv:0.9.5 /uv /usr/local/bin/uv
ENV SUMO_HOME=/usr/share/sumo \
    UV_PYTHON_INSTALL_DIR=/opt/python \
    UV_LINK_MODE=copy \
    VIRTUAL_ENV=/opt/venv \
    PATH=/opt/venv/bin:$PATH \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOME=/tmp \
    MPLCONFIGDIR=/tmp/mpl

RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*
RUN uv python install 3.11 && uv venv /opt/venv --python 3.11

COPY docker/requirements-sim.txt /tmp/requirements-sim.txt
RUN --mount=type=cache,target=/root/.cache/uv uv pip install -r /tmp/requirements-sim.txt

WORKDIR /app
COPY pyproject.toml ./
COPY sim ./sim
COPY api ./api
COPY tests ./tests
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=20s --retries=5 \
  CMD curl -fsS http://localhost:8000/health || exit 1
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]

FROM sim AS trainer
COPY docker/requirements-train.txt /tmp/requirements-train.txt
RUN --mount=type=cache,target=/root/.cache/uv uv pip install -r /tmp/requirements-train.txt
ENV LIBSUMO_AS_TRACI=1
HEALTHCHECK NONE
CMD ["python", "-c", "print('trainer ready: use make train / make train-smoke')"]
