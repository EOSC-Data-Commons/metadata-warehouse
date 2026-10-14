from typing import Any

from celery import Task

from transform.celery_app_def import celery_app
from transform.transform_core import TransformResources, transform_batch_impl
from utils.queue_utils import HarvestEventQueue


class TransformTask(Task):  # type: ignore
    resources: TransformResources

    def __init__(self) -> None:
        self.resources = TransformResources()


# Legacy Celery entry point (used by the FastAPI /index route until it is removed).
# The Airflow DAG `transform_index` calls transform.transform_core.transform_batch_impl directly.
@celery_app.task(base=TransformTask, bind=True)
def transform_batch(self: Any, batch: list[HarvestEventQueue], index_name: str, reuse_embeddings: bool) -> Any:
    return transform_batch_impl(self.resources, batch, index_name, reuse_embeddings)
