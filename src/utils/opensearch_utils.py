from typing import Any


def make_opensearch_document(
    src: dict[str, Any],
    repository: str,
    harvest_url: str,
    record_identifier: str,
) -> dict[str, Any]:
    return {
        **src,
        '_repo': repository,
        '_harvest_url': harvest_url,
        '_record_identifier': record_identifier,
    }
