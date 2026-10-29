# Airflow image shared by all airflow-* services.
# Keep the version in sync with the image tag in docker-compose.yml.
FROM apache/airflow:3.3.2

# git is needed to fetch the harvester from GitHub
USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
USER airflow

COPY docker/airflow/requirements.txt /tmp/requirements.in

# Resolve all dependencies together.
# Pin the Airflow version to prevent accidental upgrades.

RUN printf 'apache-airflow==%s\n' "$AIRFLOW_VERSION" \
        > /tmp/airflow.in \
        && cat /tmp/requirements.in >> /tmp/airflow.in \
    && uv pip compile /tmp/airflow.in \
        --constraint "${HOME}/constraints.txt" \
        --exclude-newer "3 days" \
        -o /tmp/requirements.txt \
    && pip install --no-cache-dir \
        "apache-airflow==${AIRFLOW_VERSION}" \
        -r /tmp/requirements.txt \
        --constraint "${HOME}/constraints.txt" \
    && pip check


# 2. The harvester in its own isolated venv (used by @task.external_python),
# with exactly the versions from its uv.lock.
# Branch, tag or commit of metadata-crawlers (pin a tag/commit in production):
ARG HARVESTER_REF=master
RUN umask 0002 \
    && git clone https://github.com/EOSC-Data-Commons/metadata-crawlers.git /tmp/metadata-crawlers \
    && git -C /tmp/metadata-crawlers checkout "${HARVESTER_REF}" \
    && UV_PROJECT_ENVIRONMENT=/opt/airflow/harvester-venv UV_PYTHON_DOWNLOADS=never \
       uv sync --project /tmp/metadata-crawlers --frozen --no-dev --no-editable --no-cache \
    && rm -rf /tmp/metadata-crawlers

# 3. The dependencies of the transform code in an isolated venv (used by @task.external_python),
# with exactly the versions from the uv.lock of this repo (the same set as in the transform image).
# Only the dependencies are installed; the code (src/, config/) is mounted into the containers and found via PYTHONPATH.
# The venv uses the Python of the Airflow image. If a dependency has no wheel for it, build the venv with
# another Python instead, e.g. `uv sync --python 3.12` (and remove UV_PYTHON_DOWNLOADS=never).
COPY --chown=airflow:root pyproject.toml uv.lock /tmp/transform-project/
RUN umask 0002 \
    && UV_PROJECT_ENVIRONMENT=/opt/airflow/transform-venv UV_PYTHON_DOWNLOADS=never \
       uv sync --project /tmp/transform-project --frozen --no-dev --no-install-project --no-cache \
    && rm -rf /tmp/transform-project
