"""Keep the original class identifier available for saved verification flows."""

from langflow.verification.components import ConsumableVerificationStage as VerificationStageComponent


class ConsumableVerificationStage(VerificationStageComponent):
    legacy = True
