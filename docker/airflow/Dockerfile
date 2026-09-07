# Airflow with the warehouse jobs installed, used by every airflow service in docker-compose.yml.
#
# Every service shares one image: the worker needs the full job runtime (fastembed, datahugger,
# opensearch-py, psycopg) to run the tasks, and the dag-processor needs it to import the DAGs.
#
# The dependency set comes from pyproject.toml's [project.dependencies], which is why fastapi lives
# in the "api" extra instead: airflow pins its own fastapi for the api-server, and installing ours
# on top of it is how you break the UI.
ARG AIRFLOW_VERSION=3.3.1
FROM apache/airflow:${AIRFLOW_VERSION}-python3.12

# ARGs do not survive FROM
ARG AIRFLOW_VERSION

USER airflow

# uv and VIRTUAL_ENV=/home/airflow/.local come from the base image, so this installs into airflow's
# own environment. Pinning apache-airflow keeps the resolver from moving airflow itself.
#
# The version ranges of pyproject.toml are used rather than uv.lock's exact pins on purpose: airflow
# has its own constraints on the shared transitive deps and must win. As a result this image can
# resolve a slightly different fastembed/datahugger than the transform image; both are within the
# declared ranges, and `docker compose build` prints what each one got.
COPY pyproject.toml /tmp/warehouse/pyproject.toml
RUN uv pip install --no-cache "apache-airflow==${AIRFLOW_VERSION}" --extra harvest -r /tmp/warehouse/pyproject.toml

# Baked in so the image runs standalone; docker-compose.yml mounts the same paths for hot reload
COPY --chown=airflow:root ./src /opt/airflow/warehouse/src
COPY --chown=airflow:root ./config /opt/airflow/warehouse/config
COPY --chown=airflow:root ./dags /opt/airflow/dags

# src for the transform/utils/config packages, the root for the top level config package (schema.json)
ENV PYTHONPATH=/opt/airflow/warehouse/src:/opt/airflow/warehouse
# The default /root/.cache is not writable by the airflow user
ENV FASTEMBED_CACHE_DIR=/opt/airflow/cache/fastembed
