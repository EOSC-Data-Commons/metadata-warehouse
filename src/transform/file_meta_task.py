from typing import Any
from celery import Task

from config.postgres_config import PostgresConfig
from transform.celery_app_def import celery_app, logger
from transform.file_meta_core import TransformFilemetadata, transform_filemetadata_batch_impl
from utils.queue_utils import HarvestEventQueue


class FileMetadataTask(Task):  # type: ignore
    postgres_config: PostgresConfig

    def __init__(self) -> None:
        self.resources = TransformFilemetadata()



@celery_app.task(bind=True, base=FileMetadataTask)
def add_file_metadata(self: Any, batch: list[HarvestEventQueue]) -> int:
    return transform_filemetadata_batch_impl(self.resources, batch)

