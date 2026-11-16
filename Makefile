include .env
export

COMPOSE := docker compose

DB ?= datasetdb
DB_USER ?= datasetuser

.PHONY: help init up down restart build rebuild fresh logs ps \
        dags dags-errors worker-shell scheduler-shell postgres-shell \
        clean clean-all

help:
	@echo "Airflow commands:"
	@echo "  make init           				Initialise Airflow"
	@echo "  make up             				Start Airflow"
	@echo "  make down           				Stop Airflow"
	@echo "  make restart        				Restart Airflow"
	@echo "  make build          				Build images"
	@echo "  make rebuild        				Rebuild images without cache"
	@echo "  make fresh          				Destroy volumes and recreate from scratch"
	@echo "  make logs           				Follow Airflow logs"
	@echo "  make ps             				Show containers"
	@echo "  make dags           				List DAGs"
	@echo "  make dags-errors    				Show DAG import errors"
	@echo "  make worker-shell   				Shell into airflow-worker"
	@echo "  make scheduler-shell 			Shell into airflow-scheduler"
	@echo "  make postgres-shell [DB=<database>] [DB_USER=<user>]  PostgreSQL shell (defaults: DB=airflow DB_USER=airflow)"
	@echo "  make clean          				Stop and remove containers"
	@echo "  make clean-all      				Remove containers, volumes and images"

init:
	$(COMPOSE) up airflow-init

up:
	$(COMPOSE) up -d

down:
	$(COMPOSE) down

restart:
	$(COMPOSE) restart

build:
	$(COMPOSE) build

rebuild:
	$(COMPOSE) build --no-cache
	$(COMPOSE) up -d --force-recreate

fresh:
	$(COMPOSE) down -v --remove-orphans
	$(COMPOSE) build --no-cache
	$(COMPOSE) up airflow-init
	$(COMPOSE) up -d

logs:
	$(COMPOSE) logs -f

ps:
	$(COMPOSE) ps

dags:
	$(COMPOSE) exec airflow-scheduler \
		airflow dags list

dags-errors:
	$(COMPOSE) exec airflow-scheduler \
		airflow dags list-import-errors

worker-shell:
	$(COMPOSE) exec airflow-worker bash

scheduler-shell:
	$(COMPOSE) exec airflow-scheduler bash

postgres-shell:
	$(COMPOSE) exec postgres \
		psql -U $(DB_USER) -d $(DB)

clean:
	$(COMPOSE) down --remove-orphans

clean-all:
	$(COMPOSE) down -v --remove-orphans --rmi local

