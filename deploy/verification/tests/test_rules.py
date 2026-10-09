from datetime import timedelta
from decimal import Decimal

import pytest
from langflow.verification.demo import example_task, settlement_fixture, study_fixture
from langflow.verification.rules import association_reasons, compare_scope, screen_body_part
from langflow.verification.schemas import ImageRef, Recognition, ReviewedScope, Settlement, Study, SubmitTask
from pydantic import ValidationError


@pytest.fixture
def comparison():
    return {
        "rows": [Settlement.model_validate(settlement_fixture("hip"))],
        "category": "hip_prosthesis",
        "review": ReviewedScope(
            scope_id="hip",
            detail_ids=["detail-hip"],
            study_ids=["study-hip"],
            category="hip_prosthesis",
            unit="set",
            target_confirmed=True,
            coverage_confirmed=True,
            counting_validated=True,
            evidence_ref="test-review",
        ),
        "recognition": Recognition(
            status="completed",
            raw_type="hip",
            raw_count=1,
            category="hip_prosthesis",
            count=1,
            count_scope="study",
            unit="set",
            study_ids=["study-hip"],
            processed_uids=["image-1"],
            evidence=["evidence:1"],
            counting_basis="controlled-study-validation",
            simulated=True,
        ),
        "images": [
            ImageRef(
                study_id="study-hip", series_id="series-hip", image_uid="image-1", url="https://dicom.invalid/1.dcm"
            )
        ],
        "reasons": [],
        "policy": {
            "catalog_mapping": {"DEMO-HIP": "hip_prosthesis"},
            "money_tolerance": "0.01",
            "currency": "CNY",
            "simulated": True,
        },
    }


@pytest.mark.parametrize(
    ("count", "status", "amount", "delta"),
    [
        (0, "less", "0.00", "-20000.00"),
        (1, "less", "10000.00", "-10000.00"),
        (2, "equal", "20000.00", "0.00"),
        (3, "greater", "30000.00", "10000.00"),
    ],
)
def test_exact_amounts_and_valid_zero(comparison, count, status, amount, delta):
    comparison["recognition"].count = Decimal(count)
    result = compare_scope(**comparison)
    assert result["quantity"]["status"] == status
    assert result["fee"]["converted_amount"] == amount
    assert result["fee"]["delta"] == delta


@pytest.mark.parametrize("status", ["failed", "partial_failed", "no_input", "needs_confirmation"])
def test_failure_is_not_zero(comparison, status):
    comparison["recognition"].status = status
    comparison["recognition"].count = None
    result = compare_scope(**comparison)
    assert result["quantity"]["status"] == "not_compared"
    assert result["quantity"]["delta"] is None
    assert result["fee"]["status"] == "not_compared"


@pytest.mark.parametrize(
    "change",
    [
        "no_review",
        "coverage",
        "counting",
        "image_count",
        "incomplete",
        "unit",
        "missing_count",
        "missing_quantity",
        "unknown_reversal",
        "mixed_encounter",
    ],
)
def test_unproven_counts_are_not_compared(comparison, change):
    if change == "no_review":
        comparison["review"] = None
    elif change == "coverage":
        comparison["review"].coverage_confirmed = False
    elif change == "counting":
        comparison["review"].counting_validated = False
    elif change == "image_count":
        comparison["recognition"].count_scope = "image"
    elif change == "incomplete":
        comparison["recognition"].processed_uids = []
        comparison["recognition"].failed = {"image-1": "decode_failed"}
    elif change == "unit":
        comparison["recognition"].unit = "component"
    elif change == "missing_count":
        comparison["recognition"].count = None
    elif change == "missing_quantity":
        comparison["rows"][0].quantity = None
    elif change == "unknown_reversal":
        comparison["rows"][0].is_reversal = None
    elif change == "mixed_encounter":
        row = comparison["rows"][0].model_copy(deep=True)
        row.encounter_id = "other-visit"
        comparison["rows"].append(row)
    result = compare_scope(**comparison)
    assert result["quantity"]["status"] == "not_compared"
    assert result["quantity"]["delta"] is None


@pytest.mark.parametrize("change", ["missing_price", "missing_amount", "wrong_amount", "different_prices"])
def test_fee_failure_does_not_erase_quantity(comparison, change):
    row = comparison["rows"][0]
    if change == "missing_price":
        row.unit_price = None
    elif change == "missing_amount":
        row.amount = None
    elif change == "wrong_amount":
        row.amount = Decimal(19999)
    else:
        other = row.model_copy(deep=True)
        other.detail_id = "second-detail"
        other.unit_price = Decimal(20000)
        other.amount = Decimal(40000)
        comparison["rows"].append(other)
    result = compare_scope(**comparison)
    assert result["quantity"]["status"] == "less"
    assert result["fee"]["status"] == "not_compared"


def test_same_price_group_allocates_total_once(comparison):
    other = comparison["rows"][0].model_copy(deep=True)
    other.detail_id = "second-detail"
    comparison["rows"].append(other)
    result = compare_scope(**comparison)
    assert result["quantity"]["settlement"] == "4"
    assert result["quantity"]["recognized"] == "1"
    assert result["fee"]["converted_amount"] == "10000.00"
    assert result["fee"]["source_amount"] == "40000.00"


def test_missing_settlement_time_does_not_use_update_time():
    row = Settlement.model_validate(settlement_fixture("hip"))
    row.settlement_time = None
    reasons = association_reasons(row, Study.model_validate(study_fixture("hip")), 30, 30)
    assert "settlement_time_missing" in reasons


def test_timing_and_identity():
    row = Settlement.model_validate(settlement_fixture("hip"))
    study = Study.model_validate(study_fixture("hip"))
    assert association_reasons(row, study, 30, 30) == []
    study.checked_at = row.settlement_time + timedelta(hours=1)
    assert "inpatient_study_must_precede_settlement" in association_reasons(row, study, 30, 30)
    row.encounter_type = study.encounter_type = "outpatient"
    assert association_reasons(row, study, 30, 30) == []
    study.encounter_id = "other-visit"
    assert "encounter_id_mismatch" in association_reasons(row, study, 30, 30)


def test_unknown_body_part_is_retained():
    study = Study.model_validate(study_fixture("hip"))
    study.body_part = None
    study.project_name = "术后复查"
    assert screen_body_part(study, "hip_prosthesis")["status"] == "needs_verification"


def test_three_business_inputs_reject_old_trial_contract():
    assert SubmitTask.model_validate(example_task()).hospital_scope == "常州市第一人民医院"
    with pytest.raises(ValidationError):
        SubmitTask.model_validate({**example_task(), "detail_ids": ["detail-hip"]})
