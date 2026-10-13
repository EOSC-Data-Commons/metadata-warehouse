# Airflow image shared by all airflow-* services.
# Keep the version in sync with the image tag in docker-compose.yml.
FROM apache/airflow:3.3.2

# git is needed to install the harvester from GitHub
USER root
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*
USER airflow

# Branch, tag or commit of https://github.com/EOSC-Data-Commons/metadata-crawlers (pin a tag/commit in production)
ARG HARVESTER_REF=master

COPY docker/airflow/requirements.txt /tmp/requirements.txt

# One pip run, so everything is resolved together with the pinned Airflow version:
# if there is a conflict pip fails the build instead of changing the Airflow version.
RUN pip install --no-cache-dir "apache-airflow==${AIRFLOW_VERSION}" \
    -r /tmp/requirements.txt \
    "metadata-harvester @ git+https://github.com/EOSC-Data-Commons/metadata-crawlers.git@${HARVESTER_REF}"
