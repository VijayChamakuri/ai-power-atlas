FROM apache/airflow:2.10.5-python3.12

USER root
# git: analysis runs record the commit. libgomp1: LightGBM's OpenMP runtime on Linux.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git libgomp1 \
    && rm -rf /var/lib/apt/lists/* \
    && mkdir -p /opt/atlas/project \
    && chown -R airflow /opt/atlas
USER airflow

# The project gets its own venv: Airflow's constraints pin pandas and others below what it needs.
ENV UV_PROJECT_ENVIRONMENT=/opt/atlas/venv
WORKDIR /opt/atlas/project
COPY --chown=airflow:root pyproject.toml uv.lock README.md ./
COPY --chown=airflow:root src ./src
RUN pip install --no-cache-dir uv==0.8.22 \
    && python -m uv sync --frozen --no-dev --python "$(command -v python)"
WORKDIR /opt/airflow
