from langflow.verification.components import (
    VerificationStageComponent,
    stage_inputs,
)


class VerificationSettlementSnapshot(VerificationStageComponent):
    display_name = "01 结算快照"
    description = VerificationStageComponent.STAGE_DESCRIPTIONS["01"]
    icon = "Database"
    name = "VerificationSettlementSnapshot"
    stage = "01"
    inputs = stage_inputs("01")
