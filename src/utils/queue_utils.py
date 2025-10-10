from typing import NamedTuple, Optional


class HarvestEvent(NamedTuple):
    id: str # 0
    xml: str # 1
    repository_id: str # 2
    endpoint_id: str # 3
    record_identifier: str # 4
