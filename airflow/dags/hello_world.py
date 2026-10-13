"""Smoke-test DAG for the Airflow stack.

Trigger it manually from the UI. It verifies that:
  * the scheduler can parse and schedule a DAG,
  * a Celery worker picks the task up from RabbitMQ,
  * the worker can reach the warehouse API on the compose network.

It can be deleted once the real DAGs are in place.
"""

import socket

import requests
from airflow.sdk import dag, task

WAREHOUSE_API_URL = 'http://transform:80'


@dag(
    dag_id='hello_world',
    schedule=None,
    catchup=False,
    tags=['smoke-test'],
)
def hello_world() -> None:
    @task
    def say_hello() -> str:
        hostname = socket.gethostname()
        print(f'Hello from Airflow worker {hostname}')
        return hostname

    @task
    def check_warehouse_api(worker: str) -> None:
        response = requests.get(f'{WAREHOUSE_API_URL}/health', timeout=10)
        response.raise_for_status()
        print(f'Worker {worker} reached the warehouse API: {response.json()}')

    check_warehouse_api(say_hello())


hello_world()
