from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field


class HealthGetResponse(BaseModel):
    status: str = Field(description='Server status')
    time: datetime = Field(description='Current daytime as UTC')


class IndexGetResponse(BaseModel):
    number_of_batches: int = Field(description='Number of batches created in Celery queue.')


class AdditionalMetadataParams(BaseModel):
    format: str
    endpoint: str
    protocol: str


class HarvestParams(BaseModel):
    metadata_prefix: str
    set: Optional[list[str]]
    additional_metadata_params: Optional[AdditionalMetadataParams]


class EndpointConfig(BaseModel):
    name: str
    harvest_url: str
    harvest_params: HarvestParams
    code: str
    protocol: str


class Config(BaseModel):
    endpoints_configs: list[EndpointConfig]


class HarvestEventCreateRequest(BaseModel):
    record_identifier: str
    datestamp: datetime
    raw_metadata: str  # XML
    additional_metadata: Optional[str] = None  # XML or JSON (stringified)
    harvest_url: str
    repo_code: str
    harvest_run_id: str
    is_deleted: bool


class HarvestEventCreateResponse(BaseModel):
    id: str


class HarvestRunCreateRequest(BaseModel):
    harvest_url: str


class HarvestRun(BaseModel):
    id: Optional[str] = Field(default=None, description='ID of the harvest run')

    status: Optional[str] = Field(default=None, description='Status of the harvest run: open|closed|failed')
    harvest_url: str
    from_date: Optional[datetime]
    until_date: Optional[datetime]
    started_at: Optional[datetime]
    completed_at: Optional[datetime]
    should_be_harvested: bool = Field(
        description='Whether this endpoint should be harvested now, may based on is_active and harvest_schedule'
    )


class HarvestRunGetResponse(BaseModel):
    harvest_runs: Optional[list[HarvestRun]]


class HarvestRunCreateResponse(BaseModel):
    id: str
    from_date: datetime | None
    until_date: datetime
    endpoint_config: EndpointConfig
    master_set_identifiers: list[str] | None = None


class HarvestRunCloseRequest(BaseModel):
    id: str = Field(description='ID of the harvest run to close')
    success: bool = Field(description='Indicates if the harvest run was successful')
    started_at: datetime = Field(description='Start date of the harvest')
    completed_at: datetime = Field(description='End date of the harvest')


class HarvestRunCloseResponse(BaseModel):
    id: str = Field(description='ID of the closed harvest run')


class SchedulerRunsResponse(BaseModel):
    """
    Response returned by /scheduler/wait-for-completion endpoint.

    Attributes
    ----------
    all_closed : bool
        True when there are no harvest runs with status='open'.

        Both 'closed' and 'failed' statuses are treated as completed runs,
        meaning the scheduler can proceed to the next step of the workflow.
    """

    all_closed: bool


class SchedulerClosedRunsResponse(BaseModel):
    """
    Response returned by /scheduler/closed-runs endpoint.

    Attributes
    ----------
    harvest_run_ids : list[str]
        IDs of harvest runs that finished in the last 6 days.

        Includes runs with status:
        - 'closed'  -> completed successfully
        - 'failed'  -> completed with errors

        Failed runs are included because they are no longer actively running
        and should be processed further by Transfomer.
    """

    harvest_run_ids: list[str]


class DependencyNotHarvestedError(Exception):
    """Raised when an endpoint depends on a master endpoint that has no completed harvest run yet."""
    def __init__(self, message, dependency: str):
        self.message = message
        super().__init__(self.message)
        self.dependency = dependency

