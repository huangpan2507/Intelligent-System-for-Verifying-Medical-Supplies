"""Versioned contracts; missing observations are never inferred as zero."""

from __future__ import annotations

from decimal import Decimal
from typing import Annotated, Literal
from uuid import UUID

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, field_validator, model_validator

Identifier = Annotated[str, Field(min_length=1, max_length=160, pattern=r"^\w[\w.:-]*$")]
Number = Annotated[Decimal, Field(allow_inf_nan=False, max_digits=20, decimal_places=6)]
Category = Literal["hip_prosthesis", "knee_prosthesis"]
RunStatus = Literal["waiting", "running", "completed", "partial_failed", "failed", "needs_confirmation"]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReviewedScope(Contract):
    """Explicit human-verified comparison scope, not a model's implicit guarantee."""

    scope_id: Identifier
    detail_ids: list[Identifier] = Field(min_length=1, max_length=100)
    study_ids: list[Identifier] = Field(min_length=1, max_length=100)
    category: Category
    unit: Identifier
    target_confirmed: bool = False
    coverage_confirmed: bool = False
    counting_validated: bool = False
    evidence_ref: str = Field(min_length=1, max_length=1000)

    @field_validator("detail_ids", "study_ids")
    @classmethod
    def unique_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            msg = "Duplicate identifiers in comparison scope"
            raise ValueError(msg)
        return sorted(value)


class SettlementTimeRange(Contract):
    start_inclusive: AwareDatetime
    end_exclusive: AwareDatetime

    @model_validator(mode="after")
    def ordered(self) -> SettlementTimeRange:
        if self.start_inclusive >= self.end_exclusive:
            msg = "Settlement time range must have start < end"
            raise ValueError(msg)
        return self


class SubmitTask(Contract):
    hospital_scope: str = Field(min_length=1, max_length=200)
    settlement_time_range: SettlementTimeRange
    rule: str = Field(min_length=1, max_length=200)

    @field_validator("hospital_scope", "rule")
    @classmethod
    def nonblank(cls, value: str) -> str:
        value = value.strip()
        if not value:
            msg = "Hospital and rule selection cannot be blank"
            raise ValueError(msg)
        return value


class SettlementQuery(Contract):
    hospital_ids: list[Identifier] = Field(min_length=1, max_length=100)
    settlement_time_range: SettlementTimeRange
    cursor: str | None = None
    snapshot_token: str | None = None
    limit: int = Field(default=100, ge=1, le=200)


class SettlementPage(Contract):
    items: list[dict] = Field(max_length=200)
    next_cursor: str | None
    snapshot_token: str
    consistency: Literal["source_snapshot", "observed_pages"]
    simulated: bool


class RuleCreate(Contract):
    code: Identifier
    name: str = Field(min_length=1, max_length=200)
    flow_id: UUID


class PrepareRelease(Contract):
    catalog_mapping: dict[str, Category] = Field(min_length=1, max_length=1000)
    note: str = Field(default="", max_length=1000)


class SaveRuleDraft(PrepareRelease):
    expected_revision: int = Field(ge=0)


class PublishRelease(Contract):
    candidate_id: UUID
    content_hash: str = Field(pattern=r"^[a-f0-9]{64}$")


class ActivateRelease(Contract):
    release_id: UUID | None
    expected_revision: int = Field(ge=0)


class SnapshotPageWrite(Contract):
    items: list[dict] = Field(max_length=200)
    snapshot_token: str
    consistency: Literal["source_snapshot", "observed_pages"]
    cursor: str | None
    next_cursor: str | None
    simulated: bool


class UnitWrite(Contract):
    key: Identifier
    payload: dict


class RerunAction(Contract):
    confirmed_execution_ended: Literal[True]
    reason: str = Field(min_length=5, max_length=1000)
    refetch_unsealed: bool = False


class Settlement(Contract):
    detail_id: Identifier
    patient_id: str | None = None
    hospital_id: str | None = None
    encounter_id: str | None = None
    encounter_type: Literal["inpatient", "outpatient", "other"] | None = None
    catalog_code: str | None = None
    item_name: str | None = None
    medical_consumable: bool | None = None
    insurance_paid: bool | None = None
    quantity: Number | None = None
    unit: str | None = None
    unit_price: Number | None = None
    amount: Number | None = None
    settlement_time: AwareDatetime | None = None
    update_time: AwareDatetime | None = None
    is_reversal: bool | None = None
    raw: dict = Field(default_factory=dict)


class Study(Contract):
    study_id: Identifier
    study_primary_id: Identifier | None = None
    ris_study_id: str | None = None
    patient_id: str | None = None
    hospital_id: str | None = None
    encounter_id: str | None = None
    encounter_type: str | None = None
    modality: str | None = None
    checked_at: AwareDatetime | None = None
    project_name: str | None = None
    body_part: str | None = None
    raw: dict = Field(default_factory=dict)


class ImageRef(Contract):
    study_id: Identifier
    series_id: Identifier
    image_uid: Identifier
    url: str
    raw: dict = Field(default_factory=dict)

    @field_validator("url")
    @classmethod
    def http_url(cls, value: str) -> str:
        from urllib.parse import urlsplit

        parsed = urlsplit(value)
        if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
            msg = "DICOM reference must be an HTTP(S) URL without credentials"
            raise ValueError(msg)
        return value


class Recognition(Contract):
    status: Literal["completed", "partial_failed", "failed", "no_input", "needs_confirmation"]
    raw_type: str | None = None
    raw_count: Number | None = None
    category: Category | None = None
    count: Number | None = None
    count_scope: Literal["study_group", "study", "series", "image", "unknown"] = "unknown"
    unit: str | None = None
    study_ids: list[Identifier] = Field(default_factory=list)
    processed_uids: list[Identifier] = Field(default_factory=list)
    excluded: dict[str, str] = Field(default_factory=dict)
    failed: dict[str, str] = Field(default_factory=dict)
    evidence: list[str] = Field(default_factory=list)
    counting_basis: str | None = None
    model_version: str = "unknown"
    preprocessing_version: str = "unknown"
    model_job_id: str | None = None
    error: str | None = None
    simulated: bool = False


class StageUpdate(Contract):
    stage: str = Field(pattern=r"^0[1-8]$")
    event: Literal["started", "finished"]


class ArtifactWrite(Contract):
    kind: Literal["settlement_snapshot", "selection", "studies", "screening", "manifest", "comparison"]
    key: Identifier = "main"
    payload: dict


class RequestWrite(Contract):
    request_id: UUID
    scope_id: Identifier
    payload: dict


class RequestResult(Contract):
    status: Literal["completed", "partial_failed", "failed", "no_input", "needs_confirmation"]
    raw_response: dict
    model_job_id: str | None = None
    error: str | None = None


class ManualAction(Contract):
    confirmed_execution_ended: Literal[True]
    reason: str = Field(min_length=5, max_length=1000)


class RunInput(Contract):
    task_id: UUID
    run_id: UUID
    release_id: UUID
    job_id: UUID


class ErrorWrite(Contract):
    status: Literal["failed", "needs_confirmation"]
    code: Identifier
    message: str = Field(max_length=2000)


def json_value(value: BaseModel) -> dict:
    return value.model_dump(mode="json")
