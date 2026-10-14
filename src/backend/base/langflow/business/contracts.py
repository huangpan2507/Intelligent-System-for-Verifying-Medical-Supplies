"""Business-neutral graph and public contracts."""

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

CONTRACT_VERSION = 2


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Node(Contract):
    # Native canvas IDs include the component namespace and extension slot.
    id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_:@-]{0,100}$")
    kind: str
    label: str = ""
    config: dict[str, Any] = Field(default_factory=dict)
    position: dict[str, float] = Field(default_factory=dict)


class Edge(Contract):
    source: str
    port: str = "data"
    target: str
    input: str = "data"


class Graph(Contract):
    nodes: list[Node] = Field(min_length=1, max_length=100)
    edges: list[Edge] = Field(default_factory=list, max_length=300)


class ConnectionWrite(Contract):
    name: str = Field(min_length=1, max_length=200)
    kind: Literal["postgresql", "mysql", "api", "model"]
    config: dict[str, Any]
    secret: str = ""


class SchemeWrite(Contract):
    code: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_.-]{0,159}$")
    name: str = Field(min_length=1, max_length=200)
    flow_id: str
    graph: Graph
    allowed_sources: list[str] = Field(default_factory=list)


class DraftWrite(Contract):
    graph: Graph
    expected_revision: int = Field(ge=0)


class SubmitTask(Contract):
    scheme: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    external_task_id: str | None = Field(default=None, min_length=1, max_length=160)


class Publish(Contract):
    expected_revision: int = Field(ge=0)
    note: str = Field(default="", max_length=1000)


class Activate(Contract):
    release_id: str | None
    expected_revision: int = Field(ge=0)


def normalize_parameters(specifications, supplied):
    """Use the same declared parameter contract for public tasks and subflows."""
    import copy

    import jsonschema

    values = copy.deepcopy(supplied)
    for spec in specifications:
        if "default" in spec and spec["name"] not in values:
            values[spec["name"]] = spec["default"]
    schema = {
        "type": "object",
        "properties": {p["name"]: {k: p[k] for k in ["type", "enum"] if k in p} for p in specifications},
        "required": [p["name"] for p in specifications if p.get("required")],
        "additionalProperties": False,
    }
    jsonschema.validate(values, schema)
    return values
