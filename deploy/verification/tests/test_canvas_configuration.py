import pytest
from langflow.verification.configuration import (
    ComparisonConfiguration,
    FilterCondition,
    FilterConfiguration,
    ScreeningConfiguration,
)
from langflow.verification.demo import settlement_fixture, study_fixture
from langflow.verification.rules import screen_body_part, select_settlement
from langflow.verification.schemas import Settlement, Study
from lfx.io import MultiselectInput
from lfx.template.template.base import Template
from pydantic import ValidationError

MAPPING = {"DEMO-HIP": "hip_prosthesis", "DEMO-KNEE": "knee_prosthesis"}


def test_multiselect_survives_frontend_template_round_trip():
    field = MultiselectInput(name="modalities", options=["DR", "CT"], value=["DR", "CT"])
    restored = Template.from_dict({"_type": "Component", "modalities": field.to_dict()})
    assert restored.fields[0].is_list is True
    assert restored.fields[0].value == ["DR", "CT"]


@pytest.mark.parametrize(
    ("field", "operator", "value", "status"),
    [
        ("quantity", "ge", "2", "eligible"),
        ("quantity", "gt", "2", "excluded"),
        ("unit_price", "lt", "10000.01", "eligible"),
        ("amount", "eq", "20000.00", "eligible"),
        ("item_name", "contains", "髋", "eligible"),
        ("catalog_code", "in", "DEMO-HIP,DEMO-KNEE", "eligible"),
        ("catalog_code", "not_in", "DEMO-HIP,DEMO-KNEE", "excluded"),
        ("is_reversal", "eq", "false", "eligible"),
    ],
)
def test_field_rules_change_selection(field, operator, value, status):
    row = Settlement.model_validate(settlement_fixture("hip"))
    configuration = FilterConfiguration(conditions=[FilterCondition(field=field, operator=operator, value=value)])
    result = select_settlement(row, MAPPING, configuration)
    assert result["status"] == status
    assert result["filter_checks"][0]["matched"] == (status == "eligible")


@pytest.mark.parametrize(
    ("match", "missing", "status"),
    [("all", "needs_data", "needs_data"), ("any", "needs_data", "eligible"), ("all", "exclude", "excluded")],
)
def test_missing_values_use_three_valued_logic(match, missing, status):
    row = Settlement.model_validate({**settlement_fixture("hip"), "unit_price": None})
    configuration = FilterConfiguration(
        match=match,
        missing=missing,
        conditions=[
            FilterCondition(field="quantity", operator="ge", value="2"),
            FilterCondition(field="unit_price", operator="gt", value="0"),
        ],
    )
    result = select_settlement(row, MAPPING, configuration)
    assert result["status"] == status
    assert result["filter_checks"][1]["actual"] is None
    assert result["filter_checks"][1]["matched"] is None


def test_additional_filter_does_not_disable_core_insurance_scope():
    row = Settlement.model_validate({**settlement_fixture("hip"), "insurance_paid": False})
    configuration = FilterConfiguration(conditions=[FilterCondition(field="quantity", operator="ge", value="2")])
    assert select_settlement(row, MAPPING, configuration)["status"] == "excluded"


@pytest.mark.parametrize(
    "condition",
    [
        {"field": "raw.sql", "operator": "eq", "value": "anything"},
        {"field": "quantity", "operator": "ge", "value": "NaN"},
        {"field": "quantity", "operator": "contains", "value": "1"},
        {"field": "insurance_paid", "operator": "gt", "value": "true"},
        {"field": "insurance_paid", "operator": "eq", "value": "anything"},
    ],
)
def test_invalid_rule_is_rejected(condition):
    with pytest.raises(ValidationError):
        FilterCondition.model_validate(condition)


def test_body_field_and_terms_are_configurable_but_unknown_is_retained():
    study = Study.model_validate(study_fixture("hip"))
    configuration = ScreeningConfiguration(
        field="project_name", rules=[{"category": "unrelated", "term": "Synthetic hip radiograph"}]
    )
    assert screen_body_part(study, "hip_prosthesis", configuration)["status"] == "excluded"
    study.project_name = "unknown"
    assert screen_body_part(study, "hip_prosthesis", configuration)["status"] == "needs_verification"
    with pytest.raises(ValidationError):
        ScreeningConfiguration(
            rules=[{"category": "unrelated", "term": "hip"}, {"category": "hip_prosthesis", "term": "HIP"}]
        )


def test_comparison_parameters_reject_empty_selection_and_retired_tolerance():
    with pytest.raises(ValidationError):
        ComparisonConfiguration(comparisons=[])
    with pytest.raises(ValidationError):
        ComparisonConfiguration(quantity_tolerance=-1)
    with pytest.raises(ValidationError):
        ComparisonConfiguration(money_tolerance="0.01")
