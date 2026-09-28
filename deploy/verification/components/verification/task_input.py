# ruff: noqa: RUF001 - Chinese business labels use Chinese punctuation.
from lfx.custom import Component
from lfx.io import MultilineInput, Output
from lfx.schema.message import Message


class VerificationTaskInput(Component):
    display_name = "Chat Input 任务输入"
    description = "传入已受理运行的任务JSON，连接00任务入口校验。此节点不调用大模型。"
    icon = "MessagesSquare"
    name = "VerificationTaskInput"
    priority = 0

    inputs = [
        MultilineInput(
            name="input_value",
            display_name="任务JSON",
            value="",
            input_types=[],
            info="由Worker传入task_id、run_id和detail_ids。手工运行须使用已受理且已领取的运行，不能填写聊天文本。",
        ),
    ]
    outputs = [Output(name="message", display_name="任务消息", method="message_response")]

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.is_input = True

    async def message_response(self) -> Message:
        return Message(text=self.input_value)
