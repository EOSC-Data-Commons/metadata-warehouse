# PostgreSQL for the metadata warehouse, with the extensions needed for hybrid search in postgres:
#  - pgvector      vector column type + HNSW/IVFFlat indexes (from the PGDG apt repo)
#  - pgvectorscale StreamingDiskANN index + statistical binary quantization, requires pgvector
#                  https://github.com/timescale/pgvectorscale
#  - pg_textsearch BM25 ranked full text search, must be in shared_preload_libraries (set in docker-compose.yml)
#                  https://github.com/timescale/pg_textsearch
#
# Debian based image (not alpine) because both extensions are distributed as prebuilt .deb packages.
FROM postgres:17-bookworm

# TARGETARCH is provided by buildkit: amd64 or arm64, both are published upstream
ARG TARGETARCH
ARG PGVECTORSCALE_VERSION=0.9.0
ARG PG_TEXTSEARCH_VERSION=1.3.1

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates curl unzip "postgresql-${PG_MAJOR}-pgvector"; \
    cd /tmp; \
    curl -fsSL -o pgvectorscale.zip \
        "https://github.com/timescale/pgvectorscale/releases/download/${PGVECTORSCALE_VERSION}/pgvectorscale-${PGVECTORSCALE_VERSION}-pg${PG_MAJOR}-${TARGETARCH}.zip"; \
    curl -fsSL -o pg_textsearch.zip \
        "https://github.com/timescale/pg_textsearch/releases/download/v${PG_TEXTSEARCH_VERSION}/pg-textsearch-v${PG_TEXTSEARCH_VERSION}-pg${PG_MAJOR}-${TARGETARCH}.zip"; \
    unzip -o pgvectorscale.zip -d debs; \
    unzip -o pg_textsearch.zip -d debs; \
    rm -f debs/*dbgsym*.deb; \
    dpkg -i debs/*.deb; \
    apt-get purge -y --auto-remove curl unzip; \
    rm -rf /tmp/pgvectorscale.zip /tmp/pg_textsearch.zip /tmp/debs /var/lib/apt/lists/*
