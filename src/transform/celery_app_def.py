import os
from logging.config import dictConfig
from typing import Any

from celery import Celery
from celery.signals import after_setup_logger
from celery.utils.log import get_task_logger

from config.logging_config import LOGGING_CONFIG


@after_setup_logger.connect()  # type: ignore[untyped-decorator, unused-ignore]
def configurate_celery_task_logger(**kwargs: Any) -> None:
    # https://docs.celeryq.dev/en/latest/userguide/signals.html#after-setup-logger
    dictConfig(LOGGING_CONFIG)


logger = get_task_logger(__name__)


# Results are needed by clients that wait for a task (the Airflow DAGs).
# 'rpc://' sends the result back to the client that sent the task, so no extra service is needed.
celery_app = Celery('tasks', backend=os.environ.get('CELERY_RESULT_BACKEND', 'rpc://'))

# celery_app.task_serializer = 'json'
# celery_app.ignore_result = False
