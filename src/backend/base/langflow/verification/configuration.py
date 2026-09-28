"""Typed canvas parameters; no executable expressions or arbitrary source fields."""

from __future__ import annotations

from decimal import Decimal
from string import Formatter
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, HttpUrl, TypeAdapter, field_validator, model_validator

from langflow.verification.schemas import Contract, Number

FIELD_TYPES = {
    "medical_consumable": "bool",
    "insurance_paid": "bool",
    "is_reversal": "bool",
    "quantity": "number",
    "unit_price": "number",
    "amount": "number",
    "catalog_code": "text",
    "item_name": "text",
    "unit": "text",
    "encounter_type": "text",
    "hospital_id": "text",
}


class FilterCondition(Contract):
    field: str
    operator: Literal["eq", "ne", "gt", "ge", "lt", "le", "contains", "in", "not_in", "present", "missing"]
    value: str = Field(default="", max_length=1000)

    def operands(self) -> list:
        if self.operator in {"present", "missing"}:
            return []
        values = self.value.split(",") if self.operator in {"in", "not_in"} else [self.value]
        kind = FIELD_TYPES[self.field]
        parsed = []
        for item in values:
            value = item.strip()
            if kind == "number":
                value = TypeAdapter(Number).validate_python(value)
            elif kind == "bool":
                if value.lower() not in {"true", "false"}:
                    msg = "布尔字段的目标值只能为true或false"
                    raise ValueError(msg)
                value = value.lower() == "true"
            parsed.append(value)
        return parsed

    @model_validator(mode="after")
    def check_operator(self) -> FilterCondition:
        if self.field not in FIELD_TYPES:
            msg = f"不支持的结算筛选字段: {self.field}"
            raise ValueError(msg)
        kind = FIELD_TYPES[self.field]
        if self.operator in {"gt", "ge", "lt", "le"} and kind != "number":
            msg = "大小比较只能用于数量、单价或金额字段"
            raise ValueError(msg)
        if self.operator == "contains" and kind != "text":
            msg = "包含比较只能用于文本字段"
            raise ValueError(msg)
        self.operands()
        return self


class FilterConfiguration(Contract):
    conditions: list[FilterCondition] = Field(default_factory=list, max_length=30)
    match: Literal["all", "any"] = "all"
    missing: Literal["needs_data", "exclude"] = "needs_data"


class AssociationConfiguration(Contract):
    studies_url: str = Field(default="", max_length=2048)
    days_before: int = Field(default=30, ge=0, le=365)
    days_after: int = Field(default=30, ge=0, le=365)
    modalities: list[Literal["DR", "CT"]] = Field(default_factory=lambda: ["DR", "CT"], min_length=1, max_length=2)

    @field_validator("studies_url")
    @classmethod
    def check_studies_url(cls, value: str) -> str:
        return validate_api_url(value)


class BodyRule(Contract):
    category: Literal["hip_prosthesis", "knee_prosthesis", "unrelated"]
    term: str = Field(min_length=1, max_length=200)


def default_body_rules() -> list[BodyRule]:
    terms = {
        "hip_prosthesis": ["hip", "髋关节", "髋"],
        "knee_prosthesis": ["knee", "膝关节", "膝"],
        "unrelated": ["chest", "head", "胸部", "头颅"],
    }
    return [BodyRule(category=category, term=term) for category, values in terms.items() for term in values]


class ScreeningConfiguration(Contract):
    field: Literal["body_part", "project_name"] = "body_part"
    rules: list[BodyRule] = Field(default_factory=default_body_rules, max_length=100)

    @model_validator(mode="after")
    def unambiguous_terms(self) -> ScreeningConfiguration:
        seen = {}
        for rule in self.rules:
            term = rule.term.strip().lower()
            if not term or (term in seen and seen[term] != rule.category):
                msg = "部位词条不能为空或同时属于不同类别"
                raise ValueError(msg)
            seen[term] = rule.category
        return self


class ComparisonConfiguration(Contract):
    comparisons: list[Literal["type", "quantity", "fee"]] = Field(
        default_factory=lambda: ["type", "quantity", "fee"], min_length=1, max_length=3
    )
    quantity_tolerance: Number = Field(default=Decimal(0), ge=0, le=1000)
    money_tolerance: Number = Field(default=Decimal("0.01"), ge=0, le=1)


def validate_api_url(value: str, placeholder: str | None = None, aliases: tuple[str, ...] = ()) -> str:
    """Allow complete HTTP endpoints, with a single named ID in path/query for manifest URLs."""
    value = value.strip()
    if not value:
        return value
    fields = []
    for _, field, spec, conversion in Formatter().parse(value):
        if field is not None:
            if placeholder is None or field not in (placeholder, *aliases) or spec or conversion:
                msg = f"URL仅支持占位符 {{{placeholder}}}" if placeholder else "此接口URL不支持占位符"
                raise ValueError(msg)
            fields.append(field)
    if placeholder and not fields:
        msg = f"URL必须包含 {{{placeholder}}} 占位符"
        raise ValueError(msg)
    parts = urlsplit(value)
    if "{" in parts.netloc or "}" in parts.netloc or parts.fragment or parts.username or parts.password:
        msg = "URL主机不能包含占位符; URL不能包含登录凭据或片段"
        raise ValueError(msg)
    if any(character.isspace() for character in value):
        msg = "URL不能包含空白字符"
        raise ValueError(msg)
    expanded = value.format(**dict.fromkeys((placeholder, *aliases), "identifier")) if placeholder else value
    TypeAdapter(HttpUrl).validate_python(expanded)
    return value


class ManifestConfiguration(Contract):
    series_url: str = Field(default="", max_length=2048)
    images_url: str = Field(default="", max_length=2048)

    @field_validator("series_url")
    @classmethod
    def check_series_url(cls, value: str) -> str:
        return validate_api_url(value, "study_primary_id", ("study_id",))

    @field_validator("images_url")
    @classmethod
    def check_images_url(cls, value: str) -> str:
        return validate_api_url(value, "series_id")


class RecognitionConfiguration(Contract):
    model_api_url: str = Field(default="", max_length=2048)

    @field_validator("model_api_url")
    @classmethod
    def check_model_url(cls, value: str) -> str:
        return validate_api_url(value)


CONFIGURATION_TYPES = {
    "02": FilterConfiguration,
    "03": AssociationConfiguration,
    "04": ScreeningConfiguration,
    "05": ManifestConfiguration,
    "06": RecognitionConfiguration,
    "07": ComparisonConfiguration,
}
