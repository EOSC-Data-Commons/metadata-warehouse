from enum import Enum
from typing import NamedTuple, Optional


def detect_identifier_type(identifier: str) -> str:
    return 'DOI' if identifier.startswith('10.') else 'URL'


class HarvestEventQueue(NamedTuple):
    id: str  # 0
    xml: str  # 1
    repository_id: str  # 2
    endpoint_id: str  # 3
    record_identifier: str  # 4
    identifier_type: str  # IdentifierType #5
    code: str  # 6
    harvest_url: str  # 7
    additional_metadata: Optional[str]  # 8
    additional_metadata_API: Optional[str]  # 9
    additional_metadata_protocol: Optional[str]  # 10
    is_deleted: bool  # 11
    datestamp: str  # 12
