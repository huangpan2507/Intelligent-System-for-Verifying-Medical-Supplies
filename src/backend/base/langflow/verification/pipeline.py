"""01-08 operations invoked separately by connected Langflow stage instances."""

from __future__ import annotations

import contextlib
import copy
from datetime import timedelta
from http import HTTPStatus
from typing import TYPE_CHECKING
from urllib.parse import quote
from uuid import uuid4

import httpx

from langflow.verification.configuration import (
    CONFIGURATION_TYPES,
    AssociationConfiguration,
    ComparisonConfiguration,
    FilterConfiguration,
    ManifestConfiguration,
    RecognitionConfiguration,
    ScreeningConfiguration,
    SettlementConfiguration,
)
from langflow.verification.imaging import ENCOUNTER_CODES, IMAGES_PATH, SERIES_PATH, STUDIES_PATH, ImageCloudClient
from langflow.verification.rules import association_reasons, compare_scope, screen_body_part, select_settlement
from langflow.verification.schemas import (
    ImageRef,
    Recognition,
    ReviewedScope,
    RunInput,
    Settlement,
    SettlementPage,
    Study,
)

if TYPE_CHECKING:
    from langflow.verification.settings import FlowSettings

PREFIX = "/api/v1/verification/internal/runs"


class ExecutionUncertain(RuntimeError):  # noqa: N818 - Domain state is explicit at call sites.
    """A remote operation may have been accepted; never submit it again automatically."""


class Pipeline:
    def __init__(self, settings: FlowSettings, http: httpx.AsyncClient):
        self.settings, self.http = settings, http

    async def internal(self, method: str, run_id: str, suffix: str = "", payload: dict | None = None) -> dict:
        response = await self.http.request(
            method,
            f"{self.settings.api_url}{PREFIX}/{run_id}{suffix}",
            json=payload,
            headers={"Authorization": f"Bearer {self.settings.internal_token.get_secret_value()}"},
            timeout=self.settings.request_timeout,
        )
        response.raise_for_status()
        value = response.json()
        if method != "GET" and value.get("saved") is not True:
            msg = "Business persistence did not return a save receipt"
            raise ExecutionUncertain(msg)
        return value

    def upstream_headers(self, url: str, deployment_url: str) -> dict[str, str]:
        """A canvas URL override must not send deployment credentials to a different origin."""
        target, trusted = httpx.URL(url), httpx.URL(deployment_url)
        token = self.settings.upstream_token.get_secret_value()
        if token and (target.scheme, target.host, target.port) == (trusted.scheme, trusted.host, trusted.port):
            return {"Authorization": f"Bearer {token}"}
        return {}

    async def upstream(
        self, base: str, path: str, *, method: str = "GET", payload=None, params=None, url: str | None = None
    ) -> dict:
        endpoint = url or f"{base}{path}"
        response = await self.http.request(
            method,
            endpoint,
            json=payload,
            params=params,
            headers=self.upstream_headers(endpoint, base),
            timeout=self.settings.request_timeout,
            follow_redirects=False,
        )
        response.raise_for_status()
        return response.json()

    async def save(self, context: dict, kind: str, payload: dict) -> None:
        await self.internal(
            "POST",
            context["run_id"],
            "/artifacts",
            {"kind": kind, "key": context.get("unit_key", "main"), "payload": payload},
        )

    async def enter(self, value: dict) -> dict:
        entry = RunInput.model_validate(value)
        saved = await self.internal("GET", str(entry.run_id))
        if (
            saved["task_id"] != str(entry.task_id)
            or saved["current_run_id"] != str(entry.run_id)
            or saved["status"] != "running"
            or saved["stage"] is not None
            or str(entry.release_id) != saved["release_id"]
            or str(entry.job_id) != saved["job_id"]
            or not saved["execution_started"]
        ):
            msg = "Flow input does not match the claimed run and immutable task scope"
            raise ValueError(msg)
        if saved["policy"]["simulated"] != self.settings.demo_mode:
            msg = "Runtime simulation mode differs from the accepted run"
            raise ValueError(msg)
        return {key: saved[key] for key in ["task_id", "run_id", "release_id", "job_id", "snapshot_id", "progress"]}

    async def execute(self, stage: str, context: dict, configuration: dict | None = None) -> dict:
        if stage == "00":
            return await self.enter(context)
        operations = {
            "01": self.settlements,
            "02": self.select,
            "03": self.studies,
            "04": self.screen,
            "05": self.manifests,
            "06": self.recognize,
            "07": self.compare,
            "08": self.finish,
        }
        if stage not in operations:
            msg = "Unsupported verification stage"
            raise ValueError(msg)
        reference = context
        context = await self.internal("GET", reference["run_id"])
        for key in ["task_id", "release_id", "job_id"]:
            if reference.get(key) != context[key]:
                msg_0 = "Stage reference differs from accepted run"
                raise ValueError(msg_0)
        # Connections and configurations come from the accepted immutable binding.
        self.settings = self.settings.model_copy(
            update={
                key: value
                for key, value in context["binding"].items()
                if key in {"settlement_url", "imaging_url", "model_url", "imaging_timezone", "request_timeout"}
            }
        )
        context["node_configurations"] = copy.deepcopy(context["configurations"])
        await self.internal("POST", context["run_id"], "/stages", {"stage": stage, "event": "started"})
        try:
            if configuration is not None:
                parsed = CONFIGURATION_TYPES[stage].model_validate(configuration)
                if parsed != CONFIGURATION_TYPES[stage].model_validate(context["configurations"][stage]):
                    msg_0 = "Node parameters differ from pinned release; draft execution cannot modify a business run"
                    raise ValueError(msg_0)
            if stage in {"03", "04", "05", "06", "07"}:
                after = 0
                while True:
                    page = await self.internal("GET", context["run_id"], f"/units?after={after}")
                    unit = page["unit"]
                    if unit is None:
                        break
                    local = {**context, **unit["payload"], "unit_key": unit["key"]}
                    await operations[stage](local)
                    payload = {key: local[key] for key in ["settlements", "groups"]}
                    if stage == "07":
                        payload["result"] = local["result"]
                    await self.internal(
                        "PUT", context["run_id"], f"/units/{unit['id']}", {"key": unit["key"], "payload": payload}
                    )
                    after = unit["id"]
            else:
                await operations[stage](context)
            if stage != "08":
                await self.internal("POST", context["run_id"], "/stages", {"stage": stage, "event": "finished"})
        except Exception as exc:
            uncertain = isinstance(exc, (ExecutionUncertain, httpx.TransportError))
            # Worker also checks persistent state; preserve the original failure if saving fails.
            with contextlib.suppress(httpx.HTTPError, ExecutionUncertain):
                await self.internal(
                    "POST",
                    context["run_id"],
                    "/errors",
                    {
                        "status": "needs_confirmation" if uncertain else "failed",
                        "code": f"stage_{stage}_{type(exc).__name__}",
                        "message": "Remote execution or persistence needs confirmation"
                        if uncertain
                        else f"Stage {stage} failed; inspect saved stage evidence",
                    },
                )
            raise
        saved = await self.internal("GET", context["run_id"])
        return {
            **{key: saved[key] for key in ["task_id", "run_id", "release_id", "job_id", "snapshot_id", "progress"]},
            **({"receipt": context["receipt"]} if "receipt" in context else {}),
        }

    async def settlements(self, ctx: dict) -> None:
        snapshot = await self.internal("GET", ctx["run_id"], "/snapshot")
        if snapshot["sealed"]:
            await self.internal("POST", ctx["run_id"], "/snapshot/reuse")
            return
        config = SettlementConfiguration.model_validate(ctx["configurations"]["01"])
        cursor, token, seen = None, None, set()
        while True:
            response = await self.upstream(
                self.settings.settlement_url,
                "",
                method="POST",
                url=config.settlement_api_url,
                payload={
                    "hospital_ids": [h["settlement_id"] for h in ctx["task"]["hospitals"]],
                    "settlement_time_range": ctx["task"]["settlement_time_range"],
                    "cursor": cursor,
                    "snapshot_token": token,
                    "limit": config.page_size,
                },
            )
            page = SettlementPage.model_validate(response)
            if page.next_cursor is not None and page.next_cursor in seen:
                msg = "Source pagination cursor repeated"
                raise ValueError(msg)
            await self.internal(
                "POST", ctx["run_id"], "/snapshot/pages", {**page.model_dump(mode="json"), "cursor": cursor}
            )
            if page.next_cursor is None:
                break
            cursor, token = page.next_cursor, page.snapshot_token
            seen.add(cursor)
        await self.internal("POST", ctx["run_id"], "/snapshot/seal")

    async def select(self, ctx: dict) -> None:
        configuration = FilterConfiguration.model_validate(ctx["configurations"]["02"])
        after = ""
        while True:
            source = await self.internal("GET", ctx["run_id"], f"/unit-source?after={quote(after, safe='')}")
            unit = source["unit"]
            if unit is None:
                break
            rows = {item["detail_id"]: Settlement.model_validate(item) for item in unit["settlements"]}
            selection = {
                key: select_settlement(row, ctx["policy"]["catalog_mapping"], configuration)
                for key, row in rows.items()
            }
            categories = {item["category"] for item in selection.values()}
            review = unit["review"]
            category = review["category"] if review else next(iter(categories)) if len(categories) == 1 else None
            reasons = sorted({reason for decision in selection.values() for reason in decision["reasons"]})
            if review and any(c != category for c in categories):
                reasons.append("review_category_does_not_match_catalog")
            group = {
                "scope_id": unit["key"],
                "request_scope_id": unit["key"],
                "detail_ids": sorted(rows),
                "category": category,
                "unit": review["unit"] if review else next(iter(rows.values())).unit,
                "review": review,
                "reasons": reasons,
                "studies": [],
                "images": [],
            }
            payload = {"settlements": unit["settlements"], "groups": [group]}
            await self.save(
                {**ctx, "unit_key": unit["key"]},
                "selection",
                {"selection": selection, "configuration": configuration.model_dump(mode="json")},
            )
            await self.internal("POST", ctx["run_id"], "/units", {"key": unit["key"], "payload": payload})
            after = unit["key"]

    async def studies(self, ctx: dict) -> None:
        cloud = ImageCloudClient(self.settings, self.http)
        rows = {item["detail_id"]: Settlement.model_validate(item) for item in ctx["settlements"]}
        config = ctx["node_configurations"]["03"]
        configuration = AssociationConfiguration.model_validate(config)
        configuration.studies_url = (
            configuration.studies_url or f"{self.settings.imaging_url.rstrip('/')}{STUDIES_PATH}"
        )
        ctx.setdefault("node_configurations", {})["03"] = configuration.model_dump(mode="json")
        hospital_codes = {h["settlement_id"]: h["organ_code"] for h in ctx["task"]["hospitals"]}
        for group in ctx["groups"]:
            group["rejected_studies"] = []
            if group["reasons"]:
                continue
            group_rows = [rows[key] for key in group["detail_ids"]]
            for row in group_rows:
                if row.settlement_time is None:
                    group["reasons"].append("settlement_time_missing")
                if not row.patient_id or not row.hospital_id:
                    group["reasons"].append("patient_or_hospital_missing")
            if group["reasons"]:
                continue
            candidates = {}
            for row in group_rows:
                for modality in dict.fromkeys(configuration.modalities):
                    response = await cloud.get(
                        configuration.studies_url,
                        params={
                            "system_patient_id": row.patient_id,
                            "organ_code": hospital_codes[row.hospital_id],
                            "op_em_hp_ex_no": row.encounter_id or "",
                            "op_em_hp_ex_mark": ENCOUNTER_CODES.get(row.encounter_type, ""),
                            "chk_modality": modality,
                            "begin_time": (row.settlement_time - timedelta(days=configuration.days_before))
                            .astimezone(cloud.timezone)
                            .strftime("%Y-%m-%d %H:%M:%S"),
                            "end_time": (row.settlement_time + timedelta(days=configuration.days_after))
                            .astimezone(cloud.timezone)
                            .strftime("%Y-%m-%d %H:%M:%S"),
                        },
                    )
                    for item in response:
                        study = cloud.study(item)
                        if study.hospital_id != hospital_codes[row.hospital_id]:
                            msg = "Image cloud returned a different hospital"
                            raise ValueError(msg)
                        study.raw["organ_code"] = study.hospital_id
                        study.hospital_id = row.hospital_id
                        if study.study_id in candidates and candidates[study.study_id] != study:
                            msg = "Conflicting study identity"
                            raise ValueError(msg)
                        candidates[study.study_id] = study
            for study in candidates.values():
                reasons = sorted(
                    {
                        reason
                        for row in group_rows
                        for reason in association_reasons(
                            row, study, configuration.days_before, configuration.days_after
                        )
                    }
                )
                if study.modality not in configuration.modalities:
                    reasons.append("modality_not_selected")
                if group["review"] and study.study_id not in group["review"]["study_ids"]:
                    reasons.append("outside_reviewed_study_scope")
                if reasons:
                    group["rejected_studies"].append({"study": study.model_dump(mode="json"), "reasons": reasons})
                else:
                    group["studies"].append(study.model_dump(mode="json"))
            if not group["studies"]:
                group["reasons"].append("no_associated_studies")
            if group["review"] and set(group["review"]["study_ids"]) != {s["study_id"] for s in group["studies"]}:
                group["reasons"].append("reviewed_studies_missing_or_unassociated")
        await self.save(
            ctx, "studies", {"groups": ctx["groups"], "configuration": configuration.model_dump(mode="json")}
        )

    async def screen(self, ctx: dict) -> None:
        configuration = ScreeningConfiguration.model_validate(ctx.get("node_configurations", {}).get("04", {}))
        for group in ctx["groups"]:
            retained = []
            group["screening"] = []
            for item in group["studies"]:
                decision = screen_body_part(Study.model_validate(item), group["category"], configuration)
                group["screening"].append({"study_id": item["study_id"], **decision})
                if decision["status"] != "excluded":
                    retained.append(item)
            group["studies"] = retained
        await self.save(
            ctx, "screening", {"groups": ctx["groups"], "configuration": configuration.model_dump(mode="json")}
        )

    async def manifests(self, ctx: dict) -> None:
        cloud = ImageCloudClient(self.settings, self.http)
        configuration = ManifestConfiguration.model_validate(ctx.get("node_configurations", {}).get("05", {}))
        base = self.settings.imaging_url.rstrip("/")
        configuration.series_url = configuration.series_url or f"{base}{SERIES_PATH}"
        configuration.images_url = configuration.images_url or f"{base}{IMAGES_PATH}"
        ctx.setdefault("node_configurations", {})["05"] = configuration.model_dump(mode="json")
        for group in ctx["groups"]:
            images = {}
            group["series"] = []
            for study in group["studies"]:
                primary_id = study.get("study_primary_id") or study["study_id"]
                series = await cloud.get(
                    configuration.series_url.format(
                        study_primary_id=quote(primary_id, safe=""), study_id=quote(primary_id, safe="")
                    )
                )
                for item in series:
                    if (
                        item.get("organ_code") != study.get("raw", {}).get("organ_code", study["hospital_id"])
                        or item.get("chk_modality") != study["modality"]
                    ):
                        msg = "Series hospital or modality differs from the associated study"
                        raise ValueError(msg)
                    # Validate path identifiers before constructing another URL.
                    from pydantic import TypeAdapter

                    from langflow.verification.schemas import Identifier

                    series_id = TypeAdapter(Identifier).validate_python(item["series_id"])
                    group["series"].append({**item, "study_primary_id": primary_id})
                    response = await cloud.get(configuration.images_url.format(series_id=quote(series_id, safe="")))
                    for raw in response:
                        image = cloud.image(raw, study_primary_id=primary_id, series_id=series_id)
                        if image.image_uid in images and images[image.image_uid] != image:
                            msg = "Conflicting DICOM UID association"
                            raise ValueError(msg)
                        images[image.image_uid] = image
            group["images"] = [item.model_dump(mode="json") for item in images.values()]
            group["manifest_id"] = str(uuid4())
        await self.save(
            ctx, "manifest", {"groups": ctx["groups"], "configuration": configuration.model_dump(mode="json")}
        )

    async def recognize(self, ctx: dict) -> None:
        configuration = RecognitionConfiguration.model_validate(ctx.get("node_configurations", {}).get("06", {}))
        endpoint = configuration.model_api_url or f"{self.settings.model_url.rstrip('/')}/v1/recognitions"
        ctx.setdefault("node_configurations", {})["06"] = {"model_api_url": endpoint}
        for group in ctx["groups"]:
            if not group["images"] or group["reasons"]:
                continue
            request_id = str(uuid4())
            payload = {
                "request_id": request_id,
                "manifest_id": group["manifest_id"],
                "images": group["images"],
                "target_category": group["category"],
                "unit": group["unit"],
                "count_scope": "study_group",
                "study_ids": sorted({item["study_id"] for item in group["images"]}),
            }
            # Commit request and actual input before any remote model POST.
            await self.internal(
                "POST",
                ctx["run_id"],
                "/requests",
                {
                    "request_id": request_id,
                    "scope_id": group["request_scope_id"],
                    "payload": payload,
                },
            )
            group["request_id"] = request_id
            raw = {}
            try:
                response = await self.http.post(
                    endpoint,
                    json=payload,
                    headers=self.upstream_headers(endpoint, self.settings.model_url),
                    timeout=self.settings.request_timeout,
                    follow_redirects=False,
                )
                # No vendor contract yet: only an explicit valid synchronous result establishes a terminal state.
                raw = {"unparsed_body": response.text}
                decoded = response.json()
                raw = decoded if isinstance(decoded, dict) else {"invalid_response": decoded}
                if response.status_code != HTTPStatus.OK:
                    msg = "Model acceptance or completion is unknown"
                    raise ExecutionUncertain(msg)
                recognition = Recognition.model_validate(decoded)
                await self.internal(
                    "PUT",
                    ctx["run_id"],
                    f"/requests/{request_id}",
                    {
                        "status": recognition.status,
                        "raw_response": raw,
                        "model_job_id": recognition.model_job_id,
                        "error": recognition.error,
                    },
                )
                group["recognition"] = recognition.model_dump(mode="json")
                if recognition.status == "needs_confirmation":
                    msg = "Model reported an uncertain execution"
                    raise ExecutionUncertain(msg)
            except (httpx.HTTPError, ValueError, ExecutionUncertain) as exc:
                # Do not convert a potentially accepted POST into an ordinary retryable failure.
                with contextlib.suppress(httpx.HTTPError, ExecutionUncertain):
                    await self.internal(
                        "PUT",
                        ctx["run_id"],
                        f"/requests/{request_id}",
                        {
                            "status": "needs_confirmation",
                            "raw_response": raw,
                            "model_job_id": raw.get("model_job_id") if isinstance(raw, dict) else None,
                            "error": f"Model response requires manual confirmation ({type(exc).__name__})",
                        },
                    )
                msg = "Model execution needs manual confirmation"
                raise ExecutionUncertain(msg) from exc

    async def compare(self, ctx: dict) -> None:
        rows = {item["detail_id"]: Settlement.model_validate(item) for item in ctx["settlements"]}
        raw_configuration = ctx.get("node_configurations", {}).get("07")
        configuration = ComparisonConfiguration.model_validate(raw_configuration) if raw_configuration else None
        results = []
        for group in ctx["groups"]:
            result = compare_scope(
                rows=[rows[key] for key in group["detail_ids"]],
                category=group["category"],
                review=ReviewedScope.model_validate(group["review"]) if group["review"] else None,
                recognition=Recognition.model_validate(group["recognition"]) if group.get("recognition") else None,
                images=[ImageRef.model_validate(item) for item in group["images"]],
                reasons=group["reasons"],
                policy=ctx["policy"],
                configuration=configuration,
            )
            results.append(
                {
                    **result,
                    "scope_id": group["scope_id"],
                    "request_id": group.get("request_id"),
                    "manifest_id": group["manifest_id"],
                    "node_configurations": ctx.get("node_configurations", {}),
                }
            )
        ctx["result"] = {
            "results": results,
            "rule_version": ctx["policy"]["rule_version"],
            "simulated": ctx["policy"]["simulated"],
        }
        await self.save(ctx, "comparison", ctx["result"])

    async def finish(self, ctx: dict) -> None:
        ctx["receipt"] = await self.internal("POST", ctx["run_id"], "/results")
