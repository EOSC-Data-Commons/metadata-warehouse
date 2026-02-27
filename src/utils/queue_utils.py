from enum import Enum
from typing import NamedTuple, Optional


#class IdentifierType(Enum):
    #DOI = 'doi'
    #URL = 'url'

class HarvestEventQueue(NamedTuple):
    id: str # 0
    xml: str # 1
    repository_id: str # 2
    endpoint_id: str # 3
    record_identifier: str # 4
    identifier_type: str #IdentifierType #5
    code: str # 6
    harvest_url: str # 7
    additional_metadata: Optional[str] # 8
    additional_metadata_API: Optional[str] #9
    is_deleted: bool # 10
    datestamp: str # 11
