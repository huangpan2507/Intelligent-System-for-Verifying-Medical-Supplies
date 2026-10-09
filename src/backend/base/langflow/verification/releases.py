# ruff: noqa: RUF001 - Chinese business messages intentionally use Chinese punctuation.
"""Immutable, validated verification releases; draft edits never affect accepted runs."""

from __future__ import annotations

import copy
import hashlib
import importlib.metadata
import sys
from itertools import pairwise
from pathlib import Path

from fastapi import HTTPException
from sqlalchemy import func, select, update

from langflow.verification.configuration import CONFIGURATION_TYPES
from langflow.verification.database import (
    ActivationAudit,
    ExecutionBinding,
    ReleaseCandidate,
    RuleDefinition,
    RuleRelease,
    fingerprint,
)
from langflow.verification.imaging import IMAGES_PATH, SERIES_PATH, STUDIES_PATH

COMPONENT_FILES = {
    "VerificationTaskInput": "task_input.py",
    "VerificationTaskValidation": "task_validation.py",
    "VerificationSettlementSnapshot": "settlement_snapshot.py",
    "VerificationConsumableFilter": "consumable_filter.py",
    "VerificationStudyAssociation": "study_association.py",
    "VerificationBodyScreening": "body_screening.py",
    "VerificationImageManifest": "image_manifest.py",
    "VerificationModelRecognition": "model_recognition.py",
    "VerificationResultComparison": "result_comparison.py",
    "VerificationResultSave": "result_save.py",
}


def project_root() -> Path:
    # Source deployments and the supplied container both retain deploy/verification.
    for root in Path(__file__).resolve().parents:
        if (root / "deploy/verification/components/verification").is_dir():
            return root
    msg = "Verification component bundle is missing from this runtime"
    raise ValueError(msg)


def runtime_manifest() -> dict:
    """Fingerprint execution sources and installed versions, rather than trusting a label."""
    import lfx

    root = project_root()
    locations = {
        "verification": Path(__file__).parent,
        "lfx": Path(lfx.__file__).parent,
        "components": root / "deploy/verification/components",
    }
    hashes = {}
    for label, directory in locations.items():
        for file in sorted(directory.rglob("*.py")):
            hashes[f"{label}/{file.relative_to(directory)}"] = hashlib.sha256(file.read_bytes()).hexdigest()
    for path in [
        "api/v1/verification.py",
        "api/v2/workflow.py",
        "services/background_execution/service.py",
        "services/background_execution/runner.py",
        "services/jobs/service.py",
    ]:
        file = Path(__file__).parents[1] / path
        if file.exists():
            hashes[path] = hashlib.sha256(file.read_bytes()).hexdigest()
    versions = {d.metadata["Name"].lower(): d.version for d in importlib.metadata.distributions() if d.metadata["Name"]}
    return {"sources": hashes, "dependencies": versions, "python": sys.version.split()[0]}


LOADED_RUNTIME_DIGEST = fingerprint(runtime_manifest())


def compile_release(graph: dict, catalog_mapping: dict, settings, *, flow_id: str, owner_id: str) -> dict:
    """Accept the ten audited palette types in order; reject dynamic/custom dependencies."""
    from lfx.extension.loader import discover_inline_bundles

    graph = copy.deepcopy(graph)
    nodes, edges = graph.get("nodes", []), graph.get("edges", [])
    if len(nodes) != len(COMPONENT_FILES) or len(edges) != len(COMPONENT_FILES) - 1:
        msg = "发布须包含任务输入及00—08十个节点、九条顺序连线"
        raise ValueError(msg)
    bundle_dir = project_root() / "deploy/verification/components"
    discovered = next(b for b in discover_inline_bundles([bundle_dir]) if b.bundle == "verification")
    if discovered.errors:
        msg = "Verification component discovery failed"
        raise ValueError(msg)
    classes = {item.class_name: item.klass for item in discovered.components}
    expected = list(COMPONENT_FILES)
    by_type = {}
    configurations = {}
    for node in nodes:
        kind = node["data"]["type"].split(":")[-1].split("@")[0]
        if kind not in classes or kind in by_type:
            msg = "发布仅支持各一个已审核Verification组件"
            raise ValueError(msg)
        by_type[kind] = node
        body = node["data"]["node"]
        template = body["template"]
        if body.get("frozen") or node["data"].get("frozen") or body.get("tool_mode"):
            msg = "核验发布不能冻结节点或使用工具模式"
            raise ValueError(msg)
        source = (bundle_dir / "verification" / COMPONENT_FILES[kind]).read_text()
        if template.get("code", {}).get("value", "").strip() != source.strip():
            msg = f"{kind}执行代码与当前审核组件不一致，请更新草稿节点后重新检查"
            raise ValueError(msg)
        component = classes[kind]()
        outputs = body.get("outputs", [])
        if [(o.get("name"), o.get("method")) for o in outputs] != [(o.name, o.method) for o in component.outputs]:
            msg = "发布节点的输出方法必须与已审核组件一致"
            raise ValueError(msg)
        allowed = {field.name for field in component.inputs} | {"code", "_type"}
        if set(template) - allowed:
            msg = f"{kind} contains unsupported dynamic fields"
            raise ValueError(msg)
        for name, field in template.items():
            if not isinstance(field, dict):
                continue
            if field.get("load_from_db") or (field.get("password") and field.get("value")):
                msg = "发布不可依赖可变全局变量或内嵌凭据"
                raise ValueError(msg)
            if name not in {"context", "code", "_type", "input_value"}:
                component.set(**{name: field.get("value")})
        if kind == "VerificationTaskInput":
            template["input_value"]["value"] = ""
        elif component.stage in CONFIGURATION_TYPES:
            config = component.business_configuration()
            stage = component.stage
            defaults = {
                "01": {"settlement_api_url": settings.settlement_url.rstrip("/") + "/v1/settlements/query"},
                "03": {"studies_url": settings.imaging_url.rstrip("/") + STUDIES_PATH},
                "05": {
                    "series_url": settings.imaging_url.rstrip("/") + SERIES_PATH,
                    "images_url": settings.imaging_url.rstrip("/") + IMAGES_PATH,
                },
                "06": {"model_api_url": settings.model_url.rstrip("/") + "/v1/recognitions"},
            }
            for field, value in defaults.get(stage, {}).items():
                if not config.get(field):
                    config[field] = value
                    template[field]["value"] = value
            configurations[stage] = CONFIGURATION_TYPES[stage].model_validate(config).model_dump(mode="json")
    ordered = [by_type[kind]["id"] for kind in expected]
    if len(set(ordered)) != len(COMPONENT_FILES) or {(e["source"], e["target"]) for e in edges} != set(
        pairwise(ordered)
    ):
        msg = "核验发布必须按任务输入→00→01…→08连通，不能跳过阶段"
        raise ValueError(msg)
    for edge in edges:
        target = edge.get("data", {}).get("targetHandle", {})
        source = edge.get("data", {}).get("sourceHandle", {})
        if (
            target.get("fieldName") != "context"
            or source.get("name") not in {"message", "verified_context"}
            or target.get("id") != edge["target"]
            or source.get("id") != edge["source"]
        ):
            msg = "Invalid verification edge ports"
            raise ValueError(msg)
    manifest = runtime_manifest()
    if fingerprint(manifest) != LOADED_RUNTIME_DIGEST:
        msg = "源码或依赖已变化，请先重启业务 API 和 Langflow，再校验发布"
        raise ValueError(msg)
    return {
        "graph": graph,
        "flow_id": flow_id,
        "owner_id": owner_id,
        "configurations": configurations,
        "catalog_mapping": catalog_mapping,
        "currency": "CNY",
        "simulated": settings.demo_mode,
        "runtime": manifest,
        "runtime_digest": fingerprint(manifest),
        "connections": {
            key: getattr(settings, key)
            for key in ["settlement_url", "imaging_url", "model_url", "imaging_timezone", "request_timeout"]
        },
        "contracts": {"settlement": "range-v1", "imaging": "apipost-v2", "model": "recognition-v1"},
    }


def require_runtime(package: dict) -> None:
    if package["runtime_digest"] != LOADED_RUNTIME_DIGEST or fingerprint(runtime_manifest()) != LOADED_RUNTIME_DIGEST:
        msg = "发布所需运行构建或依赖不匹配；请使用对应运行包，不可改用当前代码"
        raise ValueError(msg)


def rule_view(session, rule: RuleDefinition) -> dict:
    binding = session.get(ExecutionBinding, rule.active_binding_id) if rule.active_binding_id else None
    release = session.get(RuleRelease, binding.release_id) if binding else None
    return {
        "code": rule.code,
        "name": rule.name,
        "flow_id": rule.flow_id,
        "revision": rule.revision,
        "draft_config": rule.draft_config,
        "draft_revision": rule.draft_revision,
        "active_release_id": release.id if release else None,
        "active_version": release.version if release else None,
    }


def release_view(release: RuleRelease, *, include_package=False) -> dict:
    value = {
        "id": release.id,
        "rule_code": release.rule_code,
        "version": release.version,
        "content_hash": release.content_hash,
        "created_at": release.created_at,
        "note": release.note,
        "author_id": release.author_id,
        "simulated": release.package["simulated"],
        "runtime_digest": release.package["runtime_digest"],
    }
    if include_package:
        value["package"] = release.package
    return value


def publish(session, rule: RuleDefinition, body, author_id: str) -> RuleRelease:
    candidate = session.get(ReleaseCandidate, str(body.candidate_id))
    if candidate is None or candidate.rule_code != rule.code:
        raise HTTPException(404, "发布候选不存在")
    if candidate.content_hash != body.content_hash or fingerprint(candidate.package) != body.content_hash:
        raise HTTPException(409, "发布候选摘要不一致，请重新检查")
    if candidate.validation.get("simulation") != "passed":
        raise HTTPException(409, "候选须完成模拟执行验证后才能发布")
    existing = session.scalar(select(RuleRelease).where(RuleRelease.candidate_id == candidate.id))
    if existing:
        return existing
    require_runtime(candidate.package)
    version = (session.scalar(select(func.max(RuleRelease.version)).where(RuleRelease.rule_code == rule.code)) or 0) + 1
    release = RuleRelease(
        rule_code=rule.code,
        version=version,
        candidate_id=candidate.id,
        content_hash=candidate.content_hash,
        package=candidate.package,
        author_id=author_id,
        note=candidate.note,
    )
    session.add(release)
    session.flush()
    session.add(
        ExecutionBinding(
            release_id=release.id,
            config={
                **release.package["connections"],
                "simulated": release.package["simulated"],
                "runtime_digest": release.package["runtime_digest"],
            },
        )
    )
    session.flush()
    return release


def activate(session, rule: RuleDefinition, body, author_id: str) -> dict:
    binding_id = None
    if body.release_id:
        release = session.get(RuleRelease, str(body.release_id))
        if release is None or release.rule_code != rule.code:
            raise HTTPException(404, "发布版本不存在")
        require_runtime(release.package)
        binding_id = session.scalar(select(ExecutionBinding.id).where(ExecutionBinding.release_id == release.id))
    changed = session.execute(
        update(RuleDefinition)
        .where(RuleDefinition.code == rule.code, RuleDefinition.revision == body.expected_revision)
        .values(active_binding_id=binding_id, revision=body.expected_revision + 1)
    )
    if changed.rowcount != 1:
        raise HTTPException(409, "启用关系已被修改，请刷新后重试")
    session.add(
        ActivationAudit(
            rule_code=rule.code,
            revision=body.expected_revision + 1,
            release_id=str(body.release_id) if body.release_id else None,
            author_id=author_id,
        )
    )
    session.flush()
    session.refresh(rule)
    return rule_view(session, rule)
