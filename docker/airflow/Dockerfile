# Airflow image shared by all airflow-* services.
# Keep the version in sync with AIRFLOW_IMAGE_NAME in docker-compose.yml.
FROM apache/airflow:3.3.2

# Step 2 will add the Python dependencies the transform task needs here
# (see requirements.txt). Always install with the same apache-airflow version
# so pip cannot up/downgrade Airflow itself.
COPY docker/airflow/requirements.txt /tmp/requirements.txt
RUN if [ -s /tmp/requirements.txt ]; then \
      pip install --no-cache-dir "apache-airflow==${AIRFLOW_VERSION}" -r /tmp/requirements.txt; \
    fi
