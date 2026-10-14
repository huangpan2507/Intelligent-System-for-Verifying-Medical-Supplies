from langflow.business.components import BusinessComponent
from lfx.io import Output


class BusinessOutput(BusinessComponent):
    display_name = "Business Output"
    description = "Persistent business datasets: output"
    name = "BusinessOutput"
    kind = "output"
    outputs = [
        Output(display_name="Data", name="data", method="out_data", group_outputs=True),
    ]
