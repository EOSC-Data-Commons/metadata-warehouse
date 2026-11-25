# PostgreSQL for the metadata warehouse, with the extensions needed for hybrid search in postgres:
#  - pgvector      vector column type + HNSW/IVFFlat indexes (from the PGDG apt repo)
#  - VectorChord   vchordrq vector index (IVF + RaBitQ quantization), requires pgvector,
#                  must be in shared_preload_libraries (set in docker-compose.yml)
#                  https://github.com/tensorchord/VectorChord
#  - pg_textsearch BM25 ranked full text search, must be in shared_preload_libraries (set in docker-compose.yml)
#                  https://github.com/timescale/pg_textsearch
#
# Debian based image (not alpine) because both extensions are distributed as prebuilt .deb packages.
FROM postgres:17-trixie

# TARGETARCH is provided by buildkit: amd64 or arm64, both are published upstream
ARG TARGETARCH
ARG VECTORCHORD_VERSION=1.1.1
ARG PG_TEXTSEARCH_VERSION=1.3.1

RUN set -eux; \
    apt-get update; \
    apt-get install -y --no-install-recommends ca-certificates curl unzip "postgresql-${PG_MAJOR}-pgvector"; \
    mkdir -p /tmp/debs; \
    cd /tmp; \
    curl -fsSL -o debs/vchord.deb \
        "https://github.com/tensorchord/VectorChord/releases/download/${VECTORCHORD_VERSION}/postgresql-${PG_MAJOR}-vchord_${VECTORCHORD_VERSION}-1_${TARGETARCH}.deb"; \
    curl -fsSL -o pg_textsearch.zip \
        "https://github.com/timescale/pg_textsearch/releases/download/v${PG_TEXTSEARCH_VERSION}/pg-textsearch-v${PG_TEXTSEARCH_VERSION}-pg${PG_MAJOR}-${TARGETARCH}.zip"; \
    unzip -o pg_textsearch.zip -d debs; \
    rm -f debs/*dbgsym*.deb; \
    dpkg -i debs/*.deb; \
    apt-get purge -y --auto-remove curl unzip; \
    rm -rf /tmp/pg_textsearch.zip /tmp/debs /var/lib/apt/lists/*
