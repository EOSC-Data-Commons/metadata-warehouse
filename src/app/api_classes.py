from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, field_validator


class HealthGetResponse(BaseModel):
    status: str = Field(description='Server status')
    time: datetime = Field(description='Current daytime as UTC')


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
    raw_metadata: str  # XML, or JSON (stringified) if is_json is set
    additional_metadata: Optional[str] = None  # XML or JSON (stringified)
    harvest_url: str
    repo_code: str
    harvest_run_id: str
    is_deleted: bool
    is_json: bool = Field(
        default=False,
        description='Set if raw_metadata is JSON (already normalized DataCite JSON, validated against the schema '
        'when transformed) instead of XML',
    )


class HarvestEventCreateResponse(BaseModel):
    id: str


class HarvestRunCreateRequest(BaseModel):
    harvest_url: str
    until_date: Optional[datetime] = Field(
        default=None,
        description='Until date of the harvest run (default: now). Allows to register an initial harvest from a dump, '
        'so that the next run harvests from the date of the dump. Must include a timezone, must not be in the future '
        'and must not be earlier than the until date of the latest closed run of the endpoint.',
    )

    @field_validator('until_date')
    @classmethod
    def until_date_must_have_timezone(cls, value: Optional[datetime]) -> Optional[datetime]:
        if value is not None and value.tzinfo is None:
            raise ValueError('until_date must include a timezone')
        return value


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
    id: str = Field(description='ID of the new harvest run')
    from_date: Optional[datetime] = Field(None, description='From date for selective harvesting')
    until_date: datetime = Field(description='Until date for selective harvesting')
    endpoint_config: EndpointConfig = Field(description='Description of the endpoint used for harvesting')


class HarvestRunCloseRequest(BaseModel):
    id: str = Field(description='ID of the harvest run to close')
    success: bool = Field(description='Indicates if the harvest run was successful')
    started_at: datetime = Field(description='Start date of the harvest')
    completed_at: datetime = Field(description='End date of the harvest')


class HarvestRunCloseResponse(BaseModel):
    id: str = Field(description='ID of the closed harvest run')


class InvalidUntilDateError(Exception):
    """Raised when the until date given for a new harvest run is in the future or earlier than the latest closed run."""
