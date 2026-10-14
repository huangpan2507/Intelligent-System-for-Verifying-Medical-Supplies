# ruff: noqa: RUF001 - reviewed Chinese business labels.
"""The reviewed hip/knee template's classification settings (no credentials)."""

from scripts.business.core_classification import CATEGORIES, MATERIAL_FIELDS, NAME_FIELDS

GUIDANCE = """判断该条耗材的类别，不要仅凭手术名称把同一手术的全部耗材当成关节假体。
明确的髋/膝关节假体或成套假体系统可归入对应类别，其他具体耗材归入其他。
依据不足、相互矛盾或无法判断时保持无法确定；不根据数量、价格猜类别。
请用简短中文说明可核对的依据，不需要内部推理过程。"""


def core_config(model):
    return {
        **{k: model[k] for k in ["connection", "path", "model"]},
        "max_calls": model.get("max_calls", 10),
        "classification_fields": [
            {"field": f, "role": "evidence" if f in MATERIAL_FIELDS else "context"} for f in NAME_FIELDS
        ],
        "category_routes": [{"category": c, "continue": c in CATEGORIES[:2]} for c in CATEGORIES[:3]],
        "business_guidance": GUIDANCE,
        "rules": [
            {"op": "contains_all", "keywords": ["人工", part], "category": c}
            for c, part in zip(CATEGORIES[:2], ["髋关节", "膝关节"], strict=True)
        ],
        "ambiguity_hints": ["未使用", "非人工", "取出器"],
        "conflicts": [
            {"category": c, "field": "HILIST_NAME", "contains": part}
            for c, part in [(CATEGORIES[0], "膝"), (CATEGORIES[1], "髋")]
        ],
    }
