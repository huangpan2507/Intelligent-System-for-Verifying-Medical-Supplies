from pathlib import Path

import pytest
from langflow.verification.components import VerificationStageComponent
from lfx.extension.loader import discover_inline_bundles
from lfx.interface.components import create_component_template
from lfx.schema.message import Message

ROOT = Path(__file__).resolve().parents[3]


@pytest.fixture
def palette():
    results = discover_inline_bundles([ROOT / "deploy/verification/components"])
    result = next(result for result in results if result.bundle == "verification")
    assert not result.errors
    return {item.class_name: item for item in result.components}


def test_discovered_palette_has_ten_visible_components_with_stage_specific_fields(palette):
    assert len(palette) == 10
    stages = set()
    for item in palette.values():
        assert not getattr(item.klass, "legacy", False)
        component = item.klass()
        template, _ = create_component_template(component_extractor=component, module_name=item.module_name)
        if item.class_name == "VerificationTaskInput":
            assert template["is_input"] is True
            assert "input_value" in template["template"]
        else:
            stage = component.stage
            stages.add(stage)
            expected = {"_type", "code", "context", *VerificationStageComponent.STAGE_FIELDS.get(stage, [])}
            assert set(template["template"]) == expected
            assert all(template["template"][name]["show"] for name in expected - {"_type", "code"})
    assert stages == {f"{i:02d}" for i in range(9)}


async def test_empty_task_input_explains_the_required_business_json(palette):
    component = palette["VerificationTaskValidation"].klass()
    component.set(context=Message(text=""))
    with pytest.raises(ValueError, match="task_id、run_id、release_id和job_id"):
        await component.execute_stage()
