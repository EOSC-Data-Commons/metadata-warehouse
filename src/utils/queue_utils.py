from typing import NamedTuple, Optional


class HarvestEventQueue(NamedTuple):
    id: str # 0
    xml: str # 1
    repository_id: str # 2
    endpoint_id: str # 3
    record_identifier: str # 4
    code: str # 5
    harvest_url: str # 6
    additional_metadata: Optional[str] # 7
    is_deleted: bool # 8
