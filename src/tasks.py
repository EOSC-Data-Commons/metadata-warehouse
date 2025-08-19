from celery import Celery
from opensearchpy import OpenSearch
from opensearchpy.helpers import bulk
import xmltodict
from utils import normalize_datacite_json
from typing import Any

def flush_bulk(client: OpenSearch, batch: list[dict[str, Any]]) -> None:
    success, failed = bulk(client, batch)
    print(success, failed)

celery_app = Celery('tasks')
#celery_app.task_serializer = 'json'
#celery_app.ignore_result = False

host = 'opensearch'
client = OpenSearch(
    hosts=[{'host': host, 'port': 9200}],
    http_auth=None,
    use_ssl=False
)

@celery_app.task
def transform_batch(batch: list[str]) -> int:
    # transform to JSON and normalize
    converted = list(map(lambda el: normalize_datacite_json.normalize_datacite_json(
        xmltodict.parse(el, process_namespaces=True)['http://www.openarchives.org/OAI/2.0/:metadata'][
            'http://datacite.org/schema/kernel-4:resource']), batch))

    os_eles = list(map(lambda el: {"_op_type": "index", "_index": "test_datacite", "_source": el}, converted))

    flush_bulk(client, os_eles)

    return len(batch)
