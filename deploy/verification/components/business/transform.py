from langflow.business.components import BusinessComponent
from lfx.io import Output


class BusinessTransform(BusinessComponent):
    display_name = "Business Transform"
    description = "Persistent business datasets: transform"
    name = "BusinessTransform"
    kind = "transform"
    outputs = [
        Output(display_name="Data", name="data", method="out_data", group_outputs=True),
    ]
