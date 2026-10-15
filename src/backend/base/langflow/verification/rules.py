"""Deterministic rules shared by the Langflow stages and business tests."""

from __future__ import annotations

from datetime import timedelta
from decimal import Decimal
from operator import contains, eq, ge, gt, le, lt, ne
from typing import TYPE_CHECKING

from langflow.verification.configuration import ScreeningConfiguration

if TYPE_CHECKING:
    from langflow.verification.configuration import ComparisonConfiguration, FilterConfiguration
    from langflow.verification.schemas import ImageRef, Recognition, ReviewedScope, Settlement, Study


def select_settlement(
    row: Settlement, mapping: dict[str, str], configuration: FilterConfiguration | None = None
) -> dict:
    reasons = []
    category = mapping.get(row.catalog_code or "")
    if row.insurance_paid is False or row.medical_consumable is False:
        return {"status": "excluded", "category": category, "reasons": ["outside_insured_consumable_scope"]}
    if row.insurance_paid is None or row.medical_consumable is None:
        reasons.append("payment_or_item_type_missing")
    if category is None:
        reasons.append("catalog_mapping_unconfirmed")
    result = {"status": "needs_data" if reasons else "eligible", "category": category, "reasons": reasons}
    if configuration and configuration.conditions:
        apply_filters(row, result, configuration)
    return result


def apply_filters(row: Settlement, result: dict, configuration: FilterConfiguration) -> None:
    checks = []
    for condition in configuration.conditions:
        actual = getattr(row, condition.field)
        operands = condition.operands()
        op = condition.operator
        if op in {"present", "missing"}:
            matched = (actual is None) if op == "missing" else (actual is not None)
        elif actual is None:
            matched = None
        elif op in {"in", "not_in"}:
            matched = (actual in operands) if op == "in" else (actual not in operands)
        else:
            expected = operands[0]
            operations = {"eq": eq, "ne": ne, "gt": gt, "ge": ge, "lt": lt, "le": le, "contains": contains}
            matched = operations[op](actual, expected)
        checks.append(
            {**condition.model_dump(), "actual": str(actual) if actual is not None else None, "matched": matched}
        )
    states = [check["matched"] for check in checks]
    if configuration.match == "all":
        matched = False if False in states else None if None in states else True
    else:
        matched = True if True in states else None if None in states else False
    result["filter_checks"] = checks
    if matched is False:
        result["status"] = "excluded"
        result["reasons"].append("configured_filter_not_matched")
    elif matched is None:
        result["status"] = "excluded" if configuration.missing == "exclude" else "needs_data"
        result["reasons"].append("configured_filter_value_missing")


def association_reasons(row: Settlement, study: Study, days_before: int, days_after: int) -> list[str]:
    reasons = []
    for field in ("patient_id", "hospital_id", "encounter_id", "encounter_type"):
        left, right = getattr(row, field), getattr(study, field)
        if not left or not right:
            reasons.append(f"{field}_unconfirmed")
        elif left != right:
            reasons.append(f"{field}_mismatch")
    if study.modality not in {"CT", "DR"}:
        reasons.append("unsupported_modality")
    if row.settlement_time is None:
        reasons.append("settlement_time_missing")
    elif study.checked_at is None:
        reasons.append("study_time_missing")
    else:
        if not (
            row.settlement_time - timedelta(days=days_before)
            <= study.checked_at
            <= row.settlement_time + timedelta(days=days_after)
        ):
            reasons.append("outside_query_window")
        if row.encounter_type == "inpatient" and study.checked_at >= row.settlement_time:
            reasons.append("inpatient_study_must_precede_settlement")
        elif row.encounter_type == "outpatient" and study.checked_at <= row.settlement_time:
            reasons.append("outpatient_study_must_follow_settlement")
        elif row.encounter_type not in {"inpatient", "outpatient"}:
            reasons.append("encounter_timing_rule_unconfirmed")
    return reasons


def screen_body_part(study: Study, category: str | None, configuration: ScreeningConfiguration | None = None) -> dict:
    """Only an exact known whole-study body-part value can exclude a study."""
    configuration = configuration or ScreeningConfiguration()
    original = getattr(study, configuration.field)
    text = (original or "").strip().lower()
    matched_category = next((rule.category for rule in configuration.rules if rule.term.strip().lower() == text), None)
    if matched_category is not None and matched_category == category:
        status = "related"
    elif matched_category is not None:
        status = "excluded"
    else:
        status = "needs_verification"
    return {
        "status": status,
        "field": configuration.field,
        "original_value": original,
        "original_body_part": study.body_part,
        "original_project_name": study.project_name,
    }


def relation(delta: Decimal) -> str:
    return "greater" if delta > 0 else "less" if delta < 0 else "equal"


def not_compared(reasons: list[str]) -> dict:
    return {"status": "not_compared", "reasons": sorted(set(reasons)), "delta": None}


def compare_scope(
    *,
    rows: list[Settlement],
    category: str | None,
    review: ReviewedScope | None,
    recognition: Recognition | None,
    images: list[ImageRef],
    reasons: list[str],
    policy: dict,
    configuration: ComparisonConfiguration | None = None,
) -> dict:
    """Compare one disjoint scope; never apportion one model total across price lines."""
    blockers = list(reasons)
    if not review:
        blockers.append("comparison_scope_not_reviewed")
    elif not review.target_confirmed:
        blockers.append("target_not_confirmed")
    if not category or any(policy["catalog_mapping"].get(row.catalog_code or "") != category for row in rows):
        blockers.append("category_mapping_unconfirmed")
    if not rows or len({(r.patient_id, r.hospital_id, r.encounter_id, r.encounter_type) for r in rows}) != 1:
        blockers.append("mixed_business_association")
    if not images:
        blockers.append("no_applicable_images")
    execution = "completed"
    if recognition is None:
        blockers.append("recognition_unavailable")
    else:
        if recognition.status in {"failed", "partial_failed", "needs_confirmation"}:
            execution = "failed" if recognition.status != "partial_failed" else "partial_failed"
        if recognition.status != "completed":
            blockers.append(f"recognition_{recognition.status}")
        expected = {image.image_uid for image in images}
        processed = set(recognition.processed_uids)
        excluded = set(recognition.excluded)
        failed = set(recognition.failed)
        if (
            len(processed) != len(recognition.processed_uids)
            or processed & excluded
            or processed & failed
            or excluded & failed
            or processed | excluded | failed != expected
        ):
            blockers.append("processing_manifest_mismatch")
        if not processed:
            blockers.append("no_processed_images")
        # Without per-count-unit exclusion validation, an omitted image cannot establish a complete count.
        if excluded or failed:
            blockers.append("input_processing_incomplete")
        if failed and execution == "completed":
            execution = "partial_failed"
        expected_studies = {image.study_id for image in images}
        if set(recognition.study_ids) != expected_studies or (review and expected_studies != set(review.study_ids)):
            blockers.append("counting_study_scope_mismatch")
        if not recognition.evidence:
            blockers.append("recognition_evidence_missing")
        if not policy["simulated"] and recognition.simulated:
            blockers.append("simulated_result_in_real_run")
    result = {
        "detail_ids": sorted(row.detail_id for row in rows),
        "execution_status": execution,
        "category": category,
        "evidence": recognition.evidence if recognition else [],
        "review_evidence": review.evidence_ref if review else None,
        "raw_recognition": recognition.model_dump(mode="json") if recognition else None,
        "type": not_compared(blockers),
        "quantity": not_compared(blockers),
        "fee": not_compared(blockers),
        "conclusion": "not_compared",
        "review_clue": False,
        "interpretation": (
            "Human review required; observed implants may include prior procedures. Amounts are not fund losses."
        ),
    }
    if blockers:
        return requested_comparisons(result, configuration)
    result["type"] = (
        {"status": "equal" if recognition.category == category else "different", "reasons": []}
        if recognition.category is not None
        else not_compared(["recognized_category_unknown"])
    )
    count_blockers = []
    if result["type"]["status"] != "equal":
        count_blockers.append("category_not_aligned")
    if not review.coverage_confirmed:
        count_blockers.append("coverage_not_confirmed")
    if not review.counting_validated or not recognition.counting_basis:
        count_blockers.append("counting_not_validated")
    if recognition.count_scope not in {"study", "study_group"}:
        count_blockers.append("image_or_series_count_not_comparable")
    if recognition.count_scope == "study" and len(review.study_ids) != 1:
        count_blockers.append("study_count_cannot_represent_multiple_studies")
    if any(row.unit != review.unit for row in rows) or recognition.unit != review.unit:
        count_blockers.append("count_unit_mismatch")
    if any(row.quantity is None or row.quantity < 0 for row in rows):
        count_blockers.append("settlement_quantity_missing_or_negative")
    if any(row.is_reversal is not False for row in rows):
        count_blockers.append("reversal_rule_unconfirmed")
    if recognition.count is None or recognition.count < 0:
        count_blockers.append("recognition_count_missing_or_negative")
    if count_blockers:
        result["quantity"] = not_compared(count_blockers)
        result["fee"] = not_compared(["quantity_not_comparable"])
    else:
        settled = sum((row.quantity for row in rows), Decimal(0))
        delta = recognition.count - settled
        result["quantity"] = {
            "status": "equal" if delta == 0 else relation(delta),
            "settlement": str(settled),
            "recognized": str(recognition.count),
            "delta": str(delta),
            "unit": review.unit,
            "reasons": [],
        }
        result["fee"] = compare_fee(rows, recognition.count, policy)
    return requested_comparisons(result, configuration, coverage=review.coverage_confirmed)


def requested_comparisons(
    result: dict, configuration: ComparisonConfiguration | None, *, coverage: bool = False
) -> dict:
    requested = configuration.comparisons if configuration else ["type", "quantity", "fee"]
    if configuration:
        result["comparison_rules"] = configuration.model_dump(mode="json")
    for key in ("type", "quantity", "fee"):
        if key not in requested:
            result[key] = {"status": "not_requested", "delta": None, "reasons": ["disabled_by_node_configuration"]}
    statuses = [result[key]["status"] for key in requested]
    result["conclusion"] = (
        "difference"
        if any(s in {"different", "greater", "less"} for s in statuses)
        else "consistent"
        if all(s == "equal" for s in statuses)
        else "not_compared"
    )
    # The clue is only a review prompt; a model zero does not establish absence of implantation.
    result["review_clue"] = result["conclusion"] == "difference" and coverage
    return result


def compare_fee(rows: list[Settlement], count: Decimal, policy: dict) -> dict:
    reasons = []
    if any(row.unit_price is None or row.amount is None for row in rows):
        return not_compared(["price_or_source_amount_missing"])
    if len({row.unit_price for row in rows}) != 1:
        return not_compared(["multiple_prices_cannot_allocate_recognition_total"])
    if any(row.unit_price < 0 or row.amount < 0 for row in rows):
        return not_compared(["negative_fee_or_reversal"])
    for row in rows:
        calculated = row.quantity * row.unit_price
        if calculated != row.amount:
            reasons.append("source_amount_does_not_match_quantity_times_price")
    if reasons:
        return not_compared(reasons)
    amount = sum((row.amount for row in rows), Decimal(0))
    converted = count * rows[0].unit_price
    delta = converted - amount
    return {
        "status": "equal" if delta == 0 else relation(delta),
        "source_amount": str(amount),
        "converted_amount": str(converted),
        "delta": str(delta),
        "unit_price": str(rows[0].unit_price),
        "currency": policy["currency"],
        "reasons": [],
    }
