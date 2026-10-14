"""A small expression language; user expressions never become executable Python/SQL."""

import ast
from decimal import Decimal

from langflow.business.datasets import ident, literal


def expression(value, fields):
    tree = ast.parse(value, mode="eval")
    operators = {ast.Add: "+", ast.Sub: "-", ast.Mult: "*", ast.Div: "/", ast.Mod: "%"}

    def compile_node(node):
        if isinstance(node, ast.Name) and node.id in fields:
            return ident(node.id)
        if isinstance(node, ast.Constant) and isinstance(node.value, (str, int, float, bool, type(None))):
            return literal(Decimal(str(node.value)) if isinstance(node.value, float) else node.value)
        if isinstance(node, ast.BinOp) and type(node.op) in operators:
            return f"({compile_node(node.left)} {operators[type(node.op)]} {compile_node(node.right)})"
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.USub, ast.UAdd)):
            return f"({'-' if isinstance(node.op, ast.USub) else '+'}{compile_node(node.operand)})"
        if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
            return f"(NOT {compile_node(node.operand)})"
        if isinstance(node, ast.BoolOp) and isinstance(node.op, (ast.And, ast.Or)):
            operator = " AND " if isinstance(node.op, ast.And) else " OR "
            return "(" + operator.join(compile_node(v) for v in node.values) + ")"
        if isinstance(node, ast.Compare):
            comparisons = {ast.Eq: "=", ast.NotEq: "<>", ast.Lt: "<", ast.LtE: "<=", ast.Gt: ">", ast.GtE: ">="}
            parts = []
            left = node.left
            for op, right in zip(node.ops, node.comparators, strict=True):
                if type(op) not in comparisons:
                    break
                parts.append(f"({compile_node(left)} {comparisons[type(op)]} {compile_node(right)})")
                left = right
            else:
                return "(" + " AND ".join(parts) + ")"
        if isinstance(node, ast.IfExp):
            return (
                f"(CASE WHEN {compile_node(node.test)} THEN {compile_node(node.body)} "
                f"ELSE {compile_node(node.orelse)} END)"
            )
        if (
            isinstance(node, ast.Call)
            and isinstance(node.func, ast.Name)
            and node.func.id in {"abs", "round", "lower", "upper", "trim", "coalesce", "concat", "contains"}
            and not node.keywords
        ):
            return f"{node.func.id}({', '.join(compile_node(a) for a in node.args)})"
        msg = (
            "Expression supports fields, literals, arithmetic, comparisons, and/or/not, conditional values, "
            "and abs/round/lower/upper/trim/coalesce/concat/contains only"
        )
        raise ValueError(msg)

    return compile_node(tree.body)


def condition(item, fields, parameters=None):
    name = item["field"]
    if name not in fields:
        msg = f"Unknown field: {name}"
        raise ValueError(msg)
    field = ident(name)
    op = item.get("op", "eq")
    value = (parameters or {})[item["parameter"]] if item.get("parameter") else item.get("value")
    if item.get("right_field") and item["right_field"] not in fields:
        msg = f"Unknown field: {item['right_field']}"
        raise ValueError(msg)
    right = ident(item["right_field"]) if item.get("right_field") in fields else literal(value)
    binary = {"eq": "=", "ne": "<>", "gt": ">", "ge": ">=", "lt": "<", "le": "<="}
    if op in binary:
        return f"{field} {binary[op]} {right}"
    if op in {"is_null", "not_null"}:
        return f"{field} IS {'NOT ' if op == 'not_null' else ''}NULL"
    if op in {"in", "not_in"}:
        if not isinstance(value, list) or not value:
            msg = "Membership requires a nonempty value list"
            raise ValueError(msg)
        return f"{field} {'NOT ' if op == 'not_in' else ''}IN ({', '.join(literal(v) for v in value)})"
    if op == "contains":
        return f"contains(CAST({field} AS VARCHAR), {right})"
    msg = f"Unknown condition operator: {op}"
    raise ValueError(msg)


def predicate(config, fields, parameters=None):
    items = config.get("conditions", [])
    if not items:
        return "TRUE"
    logic = config.get("logic", "and").upper()
    if logic not in {"AND", "OR"}:
        msg = "Condition logic must be AND or OR"
        raise ValueError(msg)
    return f" {logic} ".join(f"({condition(c, fields, parameters)})" for c in items)
