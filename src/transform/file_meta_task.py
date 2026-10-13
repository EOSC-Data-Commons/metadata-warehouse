import os
from enum import Enum
from typing import Any

import psycopg
from celery import Task
from datahugger import (
    DabarXmlSrcDataset,
    Dataset,
    DataverseJsonSrcDataset,
    FileEntry,
    HalJsonSrcDataset,
    ZenodoJsonSrcDataset,
    ZipEntry,
    resolve,
)
from psycopg.rows import dict_row

from config.postgres_config import PostgresConfig
from transform.celery_app_def import celery_app, logger
from utils.queue_utils import HarvestEventQueue


class ProviderCode(str, Enum):
    DANS = 'DANS'
    ZENODO = 'ZENODO'
    HAL = 'HAL'
    DABAR = 'DABAR'
    SWISSUBASE = 'SWISS'


class FileMetadataTask(Task):  # type: ignore
    postgres_config: PostgresConfig

    def __init__(self) -> None:
        # TODO: how to configure DB and not hard code?
        self.postgres_config = PostgresConfig(db=os.environ.get('FILE_DB'))

    def parse_checksum(self, file: FileEntry | ZipEntry) -> tuple[str | None, str | None]:
        if not file.checksum:
            return None, None

        algo = file.checksum[0][0].replace('sha1', 'sha-1').upper()
        value = file.checksum[0][1]
        return algo, value

    def make_file_entry(self, harvest_event: HarvestEventQueue, file: FileEntry) -> tuple[Any, ...]:

        checksum_type, checksum_value = self.parse_checksum(file)

        return (
            harvest_event.harvest_url,
            harvest_event.record_identifier,
            file.file_identifier or file.filename,
            file.filename or file.file_identifier,
            'datahugger',
            harvest_event.identifier_type,
            'Dataset',
            file.mimetype,
            file.size,
            checksum_type,
            checksum_value,
            file.version,
            file.download_url,
            file.creation_date,
            file.last_modification_date,
        )

    def make_zip_entry(self, harvest_event: HarvestEventQueue, zip_file: ZipEntry) -> tuple[Any, ...]:
        checksum_type, checksum_value = self.parse_checksum(zip_file)

        return (
            harvest_event.harvest_url,
            harvest_event.record_identifier,
            harvest_event.record_identifier,
            harvest_event.record_identifier,
            'datahugger',
            harvest_event.identifier_type,
            'Dataset',
            'application/zip',
            None,
            checksum_type,
            checksum_value,
            zip_file.version,
            zip_file.download_url,
            zip_file.creation_date,
            None,
        )

    def collect_files(self, harvest_event: HarvestEventQueue, dataset: Dataset) -> list[tuple[Any, ...]]:
        return [self.make_file_entry(harvest_event, file) for file in dataset.crawl_file()]


@celery_app.task(bind=True, base=FileMetadataTask, ignore_result=True)
def add_file_metadata(self: Any, batch: list[HarvestEventQueue]) -> int:

    success = 0

    with psycopg.connect(**self.postgres_config.connection_params, row_factory=dict_row) as conn:
        cur = conn.cursor()

        for ele in batch:
            files = []
            harvest_event = HarvestEventQueue(*ele)  # reconstruct HarvestEvent from serialized list

            if (
                harvest_event.additional_metadata_API
                and harvest_event.additional_metadata
                and harvest_event.additional_metadata_protocol == 'DATAVERSE_API'
            ):
                # this only covers dataverse for now

                url = harvest_event.additional_metadata_API.replace(
                    '/api/datasets/:persistentId/versions/:latest-published',
                    f'/dataset.xhtml?persistentId=doi:{harvest_event.record_identifier}',
                )

                ds_dv = DataverseJsonSrcDataset(url, harvest_event.additional_metadata)

                files.extend(self.collect_files(harvest_event, ds_dv))

            elif harvest_event.additional_metadata and harvest_event.code == ProviderCode.ZENODO:
                # get id from DOI: 10.5281/zenodo.570959 -> 570959
                ds_z = ZenodoJsonSrcDataset(
                    harvest_event.record_identifier.split('.')[-1], harvest_event.additional_metadata
                )

                files.extend(self.collect_files(harvest_event, ds_z))

            elif harvest_event.additional_metadata and harvest_event.code == ProviderCode.HAL:
                # HAL IDs contain a version suffix, needs to be removed
                ds_hal = HalJsonSrcDataset(
                    harvest_event.record_identifier.split('v')[0], harvest_event.additional_metadata
                )

                files.extend(self.collect_files(harvest_event, ds_hal))

            elif harvest_event.additional_metadata and harvest_event.code == ProviderCode.DABAR:
                ds_dabar = DabarXmlSrcDataset('', harvest_event.additional_metadata)

                files.extend(self.collect_files(harvest_event, ds_dabar))

            elif harvest_event.code == ProviderCode.SWISSUBASE:
                ds_swiss = resolve(
                    f'https://www.swissubase.ch/en/catalogue/studies/1223/latest/datasets/114/{harvest_event.record_identifier}/overview'
                )

                for zip_file in ds_swiss.crawl():
                    files.append(self.make_zip_entry(harvest_event, zip_file))

            if len(files) == 0:
                logger.debug(f'no files for {harvest_event.record_identifier} in {harvest_event.code}')
                continue
            success += 1

            # Delete existing file entries for this endpoint and endpoint
            # A new version could provide fewer files
            cur.execute(
                """
                DELETE FROM record_files
                WHERE harvest_url = %s AND record_identifier = %s
                """,
                (harvest_event.harvest_url, harvest_event.record_identifier),
            )

            sql = """
                    INSERT INTO record_files (
                        harvest_url,
                        record_identifier,
                        file_identifier,
                        file_name,
                        file_information_method,
                        identifier_type,
                        identifier_granularity,
                        file_type,
                        file_size,
                        checksum_type,
                        checksum_value,
                        file_version,
                        download_url,
                        file_created_at,
                        file_last_modified_at
                    ) VALUES (
                        %s, %s, %s, %s, %s,
                        %s::file_identifier_type,
                        %s::identifier_granularity_level,
                        %s, %s,
                        %s::checksum_algorithm,
                        %s, %s, %s,
                        %s::timestamp with time zone,
                        %s::timestamp with time zone
                    )
                """

            cur.executemany(sql, files)

    return success
