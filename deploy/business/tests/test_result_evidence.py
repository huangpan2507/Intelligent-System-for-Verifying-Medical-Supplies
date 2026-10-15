# ruff: noqa: S101, PLR2004, S608, INP001, F811 - shared pytest fixtures and immutable snapshots.
from uuid import uuid4

import httpx
import pyarrow as pa
import pytest
from langflow.business.datasets import ROW_ID, ident, literal
from langflow.business.models import BusinessResult, Dataset, Release, ResultEvidence
from langflow.business.result_evidence import EvidenceView, snapshot_rows, source_detail
from langflow.business.results import persist
from langflow.verification.api import create_app
from sqlalchemy import delete, select
from test_results import runtime  # noqa: F401
from test_workflows import env  # noqa: F401


def write(store, node, rows, **kwargs):
    return store.write_batches(node, [rows], pa.Table.from_pylist(rows).schema, **kwargs)


@pytest.fixture
def evidence_case(runtime):
    persist(runtime)
    store = runtime.store
    settlement = write(store, "Billing", [{"PSN_NAME": "Sample", "SETL_FEE_LIST_ID": "D1", "CNT": 1, "PRIC": 100}])
    studies = write(
        store,
        "ExamLookup--source",
        [
            {"rpt_no": "SAME-RPT", "ris_study_id": "exam-a", "proj_name": "Exam A", "chk_modality": "DR"},
            {"rpt_no": "SAME-RPT", "ris_study_id": "exam-b", "proj_name": "Exam B", "chk_modality": "CT"},
        ],
        provenance={"query": {"returns": [{"field": "ris_study_id", "output": "study_ris_study_id"}]}},
    )
    series = write(
        store,
        "SequenceLookup--source",
        [
            {"ris_study_id": "exam-a", "global_id": "series-a"},
            {"ris_study_id": "exam-b", "global_id": "series-b"},
        ],
        provenance={"query": {"returns": [{"field": "global_id", "output": "series_id"}]}},
    )
    parent = write(
        store,
        "SequenceLookup",
        [
            {"RPT_NO": "SAME-RPT", "study_ris_study_id": "exam-a", "series_id": "series-a"},
            {"RPT_NO": "SAME-RPT", "study_ris_study_id": "exam-b", "series_id": "series-b"},
        ],
    )
    store.link(
        parent,
        " UNION ALL ".join(
            f"SELECT {ident(ROW_ID)} AS row_id, {literal(ref['id'])} AS parent_id, "
            f"{ident(ROW_ID)} AS parent_row_id FROM {store.relation(parent['id'])}"
            for ref in [studies, series]
        ),
        [studies["id"], series["id"]],
    )
    originals = [
        {
            "domain": "https://image.invalid",
            "file_path": "/a",
            "sop_instance_uid": "a",
            "_request_row_id": 0,
            "_raw_record": '{"image_instance_number":1}',
        },
        {
            "domain": "https://image.invalid",
            "file_path": "/a",
            "sop_instance_uid": "a",
            "_request_row_id": 0,
            "_raw_record": '{"image_instance_number":1}',
        },
        {
            "domain": "https://image.invalid",
            "file_path": "/b",
            "sop_instance_uid": "b",
            "_request_row_id": 1,
            "_raw_record": '{"image_instance_number":2}',
        },
    ]
    api = write(
        store,
        "Images--responses",
        originals,
        provenance={
            "parents": [parent["id"]],
            "query": {
                "collection": {
                    "address_fields": ["domain", "file_path"],
                    "item_keys": ["sop_instance_uid"],
                    "item_context": ["RPT_NO", "study_ris_study_id", "series_id"],
                }
            },
        },
    )
    with runtime.database.sessions.begin() as session:
        result = session.scalar(select(BusinessResult))
        release = session.get(Release, result.release_id)
        release.package = {
            **release.package,
            "result_templates": {"Results": {"obligation": {"sources": [{"node": "Billing"}]}}},
        }
        session.execute(
            delete(ResultEvidence).where(ResultEvidence.result_id == result.id, ResultEvidence.kind != "recognition")
        )
        ordinal = 10
        for ref in [settlement, studies, series, api]:
            for row in store.page(ref["id"])["rows"]:
                session.add(
                    ResultEvidence(
                        result_id=result.id,
                        ordinal=ordinal,
                        kind="source",
                        source_dataset_id=ref["id"],
                        source_row_id=row[ROW_ID],
                        context={},
                    )
                )
                ordinal += 1
        for suffix in ["a", "b"]:
            session.add(
                ResultEvidence(
                    result_id=result.id,
                    ordinal=ordinal,
                    kind="image",
                    context={
                        "RPT_NO": "SAME-RPT",
                        "address": "https://image.invalid/" + suffix,
                        "study_ris_study_id": "exam-" + suffix,
                        "series_id": "series-" + suffix,
                        "sop_instance_uid": suffix,
                    },
                )
            )
            ordinal += 1
    return runtime, result


def test_group_counts_and_relationships_do_not_guess_from_request_number(evidence_case):
    runtime, result = evidence_case
    view = EvidenceView(runtime.database, runtime.task.id, result)
    page = view.page("study", None, 0, 1)
    assert page["total"] == 2
    assert page["counts"] == {"settlement": 1, "study": 2, "series": 2, "recognition": 1, "image": 2, "unlinked": 0}
    assert view.page("study", None, 1, 1)["items"][0]["id"] != page["items"][0]["id"]
    for study in view.page("study", None, 0, 20)["items"]:
        series = view.page("series", study["id"], 0, 20)["items"]
        assert len(series) == 1
        image = view.page("image", series[0]["id"], 0, 20)["items"]
        assert len(image) == 1
        assert image[0]["details"]["study_ris_study_id"] == study["details"]["ris_study_id"]
        # Two raw returns of one image remain traceable, but do not count as two images.
        assert len(image[0]["sources"]) == (2 if study["details"]["ris_study_id"] == "exam-a" else 1)


def test_exact_row_identity_and_source_detail(evidence_case):
    runtime, result = evidence_case
    ref = runtime.store.query("Projected", f"SELECT 91::BIGINT AS {ident(ROW_ID)}, 'correct' AS value")
    with runtime.database.sessions.begin() as session:
        evidence = ResultEvidence(
            result_id=result.id, kind="source", ordinal=100, source_dataset_id=ref["id"], source_row_id=91, context={}
        )
        session.add(evidence)
        session.flush()
    assert snapshot_rows(runtime.store, ref["id"], [0]) == {}
    assert source_detail(runtime.database, runtime.task.id, result.id, evidence.id)["record"]["value"] == "correct"
    with pytest.raises(ValueError, match="this result"):
        source_detail(runtime.database, runtime.task.id, str(uuid4()), evidence.id)


def test_wrong_image_context_stays_unlinked(evidence_case):
    runtime, result = evidence_case
    with runtime.database.sessions.begin() as session:
        evidence = session.scalar(select(ResultEvidence).where(ResultEvidence.kind == "image"))
        evidence.context = {**evidence.context, "series_id": "not-the-saved-series"}
    page = EvidenceView(runtime.database, runtime.task.id, result).page("unlinked", None, 0, 20)
    assert any(i["id"] == evidence.id for i in page["items"])
    assert next(i for i in page["items"] if i["id"] == evidence.id)["sources"] == []


def test_conflicting_study_ancestry_does_not_keep_the_first_parent(evidence_case):
    runtime, result = evidence_case
    with runtime.database.sessions() as session:
        datasets = {d.node_id: d for d in session.scalars(select(Dataset).where(Dataset.raw.is_(True)))}
    parent = datasets["SequenceLookup"]
    study, series = datasets["ExamLookup--source"], datasets["SequenceLookup--source"]
    # The same series appears in two joined rows; the second has ambiguous study ancestry.
    mapping = " UNION ALL ".join(
        f"SELECT {row} row_id, {literal(source)} parent_id, {original} parent_row_id"
        for row, source, original in [
            (0, study.id, 0),
            (0, series.id, 0),
            (1, study.id, 0),
            (1, study.id, 1),
            (1, series.id, 0),
        ]
    )
    runtime.store.link({"id": parent.id, "node_id": parent.node_id}, mapping, [study.id, series.id])
    view = EvidenceView(runtime.database, runtime.task.id, result)
    item = next(i for i in view.page("series", None, 0, 20)["items"] if i["details"]["global_id"] == "series-a")
    assert item["parent"] is None
    assert item["id"] in {i["id"] for i in view.page("unlinked", None, 0, 20)["items"]}


async def test_evidence_apis_are_read_only_and_source_isolated(evidence_case):
    runtime, result = evidence_case
    with runtime.database.sessions() as session:
        evidence = session.scalar(select(ResultEvidence).where(ResultEvidence.kind == "recognition"))
    root = f"/api/v1/business/tasks/{runtime.task.id}"
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app(runtime.settings, runtime.database)), base_url="http://fixture"
    ) as http:
        for path in [
            f"results/{result.id}/evidence-view?group=study&limit=1",
            f"results/{result.id}/evidence/{evidence.id}/detail",
            "result-storage",
        ]:
            response = await http.get(f"{root}/{path}", headers={"Authorization": "Bearer " + "a" * 20})
            assert response.status_code == 200, response.text
            assert (
                await http.get(f"{root}/{path}", headers={"Authorization": "Bearer " + "b" * 20})
            ).status_code == 404
        assert (
            await http.get(
                f"{root}/results/{uuid4()}/evidence/{evidence.id}/detail",
                headers={"Authorization": "Bearer " + "a" * 20},
            )
        ).status_code == 404
