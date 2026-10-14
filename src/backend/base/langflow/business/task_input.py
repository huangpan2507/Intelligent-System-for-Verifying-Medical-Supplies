"""Fixed regulator task contract; values belong to an accepted task, never a canvas."""

import copy
import re
from datetime import datetime

CONTRACT = "regulatory.v1"
PARAMETERS = [{"name": name, "type": "string", "required": True} for name in ("hospital_name", "start", "end")]
CONTEXT = [
    {"name": name, "type": "integer" if name == "version" else "string"}
    for name in ("scheme", "rule_name", "external_task_id", "task_id", "release_id", "version")
]


def parameter_definitions(node):
    return PARAMETERS if node["kind"] == "taskinput" else node["config"].get("parameters", [])


def validate_request(parameters, external_task_id):
    """Check only at intake, preserving the submitted values and explicit period."""
    if not isinstance(external_task_id, str) or not external_task_id.strip():
        msg = "external_task_id is required for regulatory tasks"
        raise ValueError(msg)
    if set(parameters) != {p["name"] for p in PARAMETERS}:
        msg = "Regulatory parameters must contain hospital_name, start and end"
        raise ValueError(msg)
    for name, value in parameters.items():
        if not isinstance(value, str) or not value.strip():
            msg = f"{name} must be a non-empty string"
            raise ValueError(msg)
    dates = []
    for name in ("start", "end"):
        value = parameters[name]
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}", value):
            msg = f"{name} must use YYYY-MM-DD HH:mm:ss (Asia/Shanghai)"
            raise ValueError(msg)
        try:
            dates.append(datetime.strptime(value, "%Y-%m-%d %H:%M:%S"))  # noqa: DTZ007 - contract is Beijing wall time
        except ValueError as exc:
            msg = f"{name} is not a valid date and time"
            raise ValueError(msg) from exc
    if dates[0] > dates[1]:
        msg = "start must not be later than end"
        raise ValueError(msg)
    return copy.deepcopy(parameters)


def accepted_input(session, task):
    from langflow.business.models import Release, TaskInput

    entry = session.get(TaskInput, task.id)
    if entry is None:
        return None
    release = session.get(Release, task.release_id)
    return {
        "parameters": copy.deepcopy(task.parameters),
        "task": {
            "scheme": task.scheme_code,
            "rule_name": entry.rule_name,
            "external_task_id": entry.external_task_id,
            "task_id": task.id,
            "release_id": task.release_id,
            "version": release.version,
        },
    }
