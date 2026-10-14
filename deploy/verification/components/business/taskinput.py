from langflow.business.components import BusinessComponent
from lfx.io import Output


class BusinessTaskinput(BusinessComponent):
    display_name = "Business Task Start"
    description = "Start a regulatory task with accepted request parameters and task identifiers."
    name = "BusinessTaskinput"
    kind = "taskinput"
    outputs = [Output(display_name="Task input", name="data", method="out_data", group_outputs=True)]
