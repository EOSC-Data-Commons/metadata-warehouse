{
  pkgs,
  lib,
  config,
  inputs,
  ...
}:

{
  env.OPENSEARCH_ADDRESS = "127.0.0.1";
  env.OPENSEARCH_PORT = "9200";
  env.INDEX_NAME = "test_datacite";

  env.CELERY_BROKER_URL = "redis://127.0.0.1:6379/0";
  env.CELERY_RESULT_BACKEND = "redis://127.0.0.1:6379/0";
  env.CELERY_BATCH_SIZE = 250;

  # https://devenv.sh/languages/
  languages.python = {
    enable = true;
    version = "3.12.12";
    venv = {
      enable = true;
    };
    uv = {
      enable = true;
      sync = {
        enable = true;
        allPackages = true;
      };
    };
  };

  enterShell = '''';

  # https://devenv.sh/services/
  services.redis = {
    enable = true;
    extraConfig = ''
      bind * -::*
      protected-mode no
      dir ./redis-data
    '';
  };

  tasks."clean:python" = {
    exec = ''
      rm -rf ./.devenv/state/venv/
    '';
    cwd = ".";
  };

  # celery as task worker
  processes.metadata-warehouse-tasks =
    let
      postgres_admin = "admin";
      postgres_user = "admin";
      postgres_password = "test";
      postgres_address = "127.0.0.1";
      postgres_port = "5432";
      postgres_db = "dataset";
    in
    {
      # https://docs.celeryq.dev/en/latest/internals/reference/celery.concurrency.solo.html
      # consider performance, `solo` is single thread pool, no async gain for performance.
      exec = ''
        export POSTGRES_ADMIN=${postgres_admin}
        export POSTGRES_USER=${postgres_user}
        export POSTGRES_PASSWORD=${postgres_password}
        export POSTGRES_ADDRESS=${postgres_address}
        export POSTGRES_PORT=${postgres_port}
        export POSTGRES_DB=${postgres_db}
        celery -A tasks worker -E --pool=solo --loglevel=INFO
      '';
      cwd = "./src";
      process-compose = {
        depends_on.redis.condition = "process_healthy";
        readiness_probe = {
          # this is ugly because metadata-warehouse did not properly manage the python package structure.
          exec.command = ''
            cd ./src && celery -A tasks status && cd ..
          '';
          initial_delay_seconds = 2;
          period_seconds = 60;
          timeout_seconds = 100;
          success_threshold = 1;
          failure_threshold = 20;
        };
      };
    };

  # https://devenv.sh/processes/
  # transform restapi
  processes.metadata-warehouse-transform-api =
    let
      postgres_admin = "admin";
      postgres_user = "admin";
      postgres_password = "test";
      postgres_address = "127.0.0.1";
      postgres_port = "5432";
      postgres_db = "dataset";
    in
    {
      exec = ''
        export POSTGRES_ADMIN=${postgres_admin}
        export POSTGRES_USER=${postgres_user}
        export POSTGRES_PASSWORD=${postgres_password}
        export POSTGRES_ADDRESS=${postgres_address}
        export POSTGRES_PORT=${postgres_port}
        export POSTGRES_DB=${postgres_db}
        fastapi run --host 127.0.0.1 transform.py --port 8080
      '';
      cwd = "./src";
      process-compose = {
        readiness_probe = {
          exec.command = ''
            if curl -s -o /dev/null -w "%{http_code}" http://127.0.0.1:8080/health | grep -q 200; then
              exit 0
            else
              echo "API not ready yet..." 2>&1
              exit 1
            fi
          '';
          initial_delay_seconds = 2;
          period_seconds = 10;
          timeout_seconds = 4;
          success_threshold = 1;
          failure_threshold = 5;
        };
      };
    };

  services.postgres = {
    enable = true;
    package = pkgs.postgresql_17;
    listen_addresses = "127.0.0.1";
    port = 5432;
    initialDatabases = [
      {
        name = "dataset";
        user = "admin";
        pass = "test";
      }
    ];
  };

  services.opensearch = {
    enable = true;
    settings = {
      cluster.name = "opensearch";
      discovery.type = "single-node";
      network.host = "127.0.0.1";
      http.port = "9200";
      transport.port = "9300";
    };
  };

  # --- redis
  # https://devenv.sh/tasks/
  tasks."app:redis-data" = {
    exec = "mkdir -p redis-data";
    before = [ "devenv:processes:redis" ];
  };

  tasks."clean:redis" = {
    exec = ''
      echo "Redis server stopped, cleaning up..."
      rm -rf ./redis-data
    '';
    after = [ "devenv:processes:redis" ];
  };

  # NOTE: the lift-cycle of manually full example data creating and clear is:
  # 1. create db "admin" -> import db entries from dump.sql -> create opensearch indexing ->
  # -> indexing to db (in production this runs async in another thread) -> delete db "admin" -> back to '1'

  # --- postgres
  tasks."db-import:dump" = {
    exec = "psql -U admin dataset < dump.sql";
    status = "db-needs-dump";
    before = [ "db-import:create-index" ];
  };

  # index opensearch
  tasks."db-import:create-index" = {
    exec = "python create_index.py";
    cwd = "./metadata-warehouse/scripts/opensearch_data/";
    before = [ "db-import:indexing" ];
  };

  # import three small data repos
  tasks."db-import:indexing" = {
    exec = ''
      python repo-index.py indexing https://demo.onedata.org/oai_pmh
      python repo-index.py indexing https://dabar.srce.hr/oai/
      python repo-index.py indexing https://phys-techsciences.datastations.nl/oai
      # python repo-index.py indexing https://ssh.datastations.nl/oai
      # python repo-index.py indexing https://www.swissubase.ch/oai-pmh/v1/oai
      # python repo-index.py indexing https://lifesciences.datastations.nl/oai
      # python repo-index.py indexing https://dataverse.nl/oai
      # python repo-index.py indexing https://api.archives-ouvertes.fr/oai/hal
      # python repo-index.py indexing https://archaeology.datastations.nl/oai
    '';
  };

  tasks."clean:db" = {
    exec = ''
      psql -U $USER -d postgres -c "DROP DATABASE dataset;"
      psql -U $USER -d postgres -c 'CREATE DATABASE dataset OWNER admin;'
    '';
  };

  tasks."purge:all" = {
    exec = ''
      rm -rf ./.devenv/
      rm -rf ./redis-data/
      rm -f ./requirements.txt
    '';
    cwd = ".";
  };

  tasks."dev:uv-sync" = {
    exec = ''
      rm -f ./uv.lock
      uv sync
    '';
  };
}
