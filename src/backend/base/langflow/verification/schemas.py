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


class TaskConfig(Contract):
    days_before: int = Field(default=30, ge=0, le=365)
    days_after: int = Field(default=30, ge=0, le=365)
    reviewed_scopes: list[ReviewedScope] = Field(default_factory=list, max_length=100)


class SubmitTask(Contract):
    source_system: Identifier
    external_task_id: Identifier
    detail_ids: list[Identifier] = Field(min_length=1, max_length=100)
    config: TaskConfig = Field(default_factory=TaskConfig)

    @field_validator("detail_ids")
    @classmethod
    def canonical_ids(cls, value: list[str]) -> list[str]:
        if len(value) != len(set(value)):
            msg = "Settlement detail IDs must be unique"
            raise ValueError(msg)
        return sorted(value)

    @model_validator(mode="after")
    def validate_scopes(self) -> SubmitTask:
        assigned: set[str] = set()
        scope_ids: set[str] = set()
        study_categories: set[tuple[str, str]] = set()
        for scope in self.config.reviewed_scopes:
            if scope.scope_id in scope_ids or not set(scope.detail_ids).issubset(self.detail_ids):
                msg = "Comparison scope must have a unique ID and belong to this task"
                raise ValueError(msg)
            if assigned.intersection(scope.detail_ids):
                msg = "A settlement detail cannot consume multiple recognition totals"
                raise ValueError(msg)
            for study in scope.study_ids:
                key = (study, scope.category)
                if key in study_categories:
                    msg = "A study/category count cannot be allocated to multiple scopes"
                    raise ValueError(msg)
                study_categories.add(key)
            assigned.update(scope.detail_ids)
            scope_ids.add(scope.scope_id)
        self.config.reviewed_scopes.sort(key=lambda scope: scope.scope_id)
        return self


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


class FinishRun(Contract):
    results: list[dict] = Field(min_length=1, max_length=100)
    rule_version: str
    simulated: bool


class ManualAction(Contract):
    confirmed_execution_ended: Literal[True]
    reason: str = Field(min_length=5, max_length=1000)


class RunInput(Contract):
    task_id: UUID
    run_id: UUID
    detail_ids: list[Identifier]


class ErrorWrite(Contract):
    status: Literal["failed", "needs_confirmation"]
    code: Identifier
    message: str = Field(max_length=2000)


def json_value(value: BaseModel) -> dict:
    return value.model_dump(mode="json")
