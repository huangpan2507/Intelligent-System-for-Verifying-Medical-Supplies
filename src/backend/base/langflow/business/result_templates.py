# ruff: noqa: RUF001 - predefined Chinese business narratives.
"""Versioned result presets: business bindings live here, not in the generic Output contract."""

import json
from pathlib import Path

ROOT = Path(__file__).with_name("result_templates")


def template(template_id):
    if template_id != "hip_knee_v1":
        msg = f"Unknown result template: {template_id}"
        raise ValueError(msg)
    return json.loads((ROOT / "hip_knee_v1.json").read_text())


def prepare_output(config, *, single):
    if single:
        config["primary"] = True
    if not config.get("result_template"):
        return None
    profile = template(config["result_template"])
    config["columns"] = profile["columns"]
    config["obligation"] = profile["obligation"]
    return profile


def display(value):
    """Keep exact decimal text; never round or fill missing facts with zero."""
    if value is None or value == "":
        return "未提供"
    return str(value)


def render(profile, facts, *, reasons=None):
    checks = [
        {
            "name": c["name"],
            "label": c["label"],
            "status": facts.get(c["status"], "uncompared"),
            "left": facts.get(c["left"]),
            "right": facts.get(c["right"]),
            "difference": facts.get(c.get("difference", "")),
            "reason": (reasons or {}).get(c["name"], ""),
        }
        for c in profile["checks"]
    ]
    differences = [c["label"] for c in checks if c["status"] == "different"]
    unfinished = [c["label"] for c in checks if c["status"] not in {"equal", "different"}]
    status = "difference" if differences else "incomplete" if unfinished else "normal"
    narrative = (
        f"{display(facts.get('PSN_NAME'))}患者在{display(facts.get('ORGAN_NAME'))}的结算项目为"
        f"{display(facts.get('HILIST_NAME'))}。"
        f"结算类别为{display(facts.get('target_category'))}，影像识别类别为{display(facts.get('recognized_category'))}；"
        f"结算数量为{display(facts.get('CNT'))}，影像识别数量为{display(facts.get('recognized_quantity'))}；"
        f"双方折算金额分别为{display(facts.get('settled_amount'))}元和{display(facts.get('observed_amount'))}元。"
    )
    if differences:
        narrative += f"本次核验存在{'、'.join(differences)}差异。"
        for check in checks:
            if check["status"] == "different" and check["difference"] is not None:
                narrative += f"{check['label']}差值（识别侧减结算侧）为{display(check['difference'])}。"
    if unfinished:
        narrative += f"{'、'.join(unfinished)}尚未完成，不能判为正常。"
        explanation = "；".join(f"{c['label']}：{c['reason']}" for c in checks if c["reason"])
        if explanation:
            narrative += explanation + "。"
    if status == "normal":
        narrative += "本次核验结果正常，三项比较一致。"
    narrative += (
        f"检查申请单号（RPT_NO）：{display(facts.get('RPT_NO'))}；"
        f"医院代码（ORGAN_CODE）：{display(facts.get('ORGAN_CODE'))}；"
        f"系统标识（SYSTEM_ID）：{display(facts.get('SYSTEM_ID'))}。"
    )
    if facts.get("simulated") in (True, "true", "True", 1):
        narrative += "本结果包含模拟影像识别，仅用于流程验收。"
    return {"status": status, "complete": not unfinished, "narrative": narrative, "checks": checks}


def preview():
    profile = template("hip_knee_v1")
    return {
        "id": profile["id"],
        "version": profile["version"],
        "name": profile["name"],
        "columns": profile["columns"],
        "obligation": profile["obligation"],
        "example": {
            **render(profile, profile["example"]),
            "facts": profile["example"],
            "template_id": profile["id"],
            "template_version": profile["version"],
        },
    }
