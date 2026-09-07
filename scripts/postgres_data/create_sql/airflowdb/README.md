Intentionally empty: airflow owns this schema and creates it with `airflow db migrate`, which the
airflow-apiserver container runs on every start (`_AIRFLOW_DB_MIGRATE` in docker-compose.yml).

create_db.py is only used here to `CREATE DATABASE airflowdb`; it skips the SQL files it does not
find, so there is nothing to put in this folder.

Never run `create_db.py --db airflowdb --reset`: it drops schema public, which is airflow's entire
metadata (DAG history, task instances, connections).
