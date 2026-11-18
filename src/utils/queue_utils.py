from enum import Enum
from typing import Any, NamedTuple, Optional


def detect_identifier_type(identifier: str) -> str:
    return 'DOI' if identifier.startswith('10.') else 'URL'


class HarvestEventQueue(NamedTuple):
    id: str  # 0
    xml: Optional[str]  # 1, the record if the event is XML, otherwise None
    json: Optional[dict[str, Any]]  # 2, the record if the event is JSON (already normalized), otherwise None
    repository_id: str  # 3
    endpoint_id: str  # 4
    record_identifier: str  # 5
    identifier_type: str  # IdentifierType #6
    code: str  # 7
    harvest_url: str  # 8
    additional_metadata: Optional[str]  # 9
    additional_metadata_API: Optional[str]  # 10
    additional_metadata_protocol: Optional[str]  # 11
    is_deleted: bool  # 12
    datestamp: str  # 13
