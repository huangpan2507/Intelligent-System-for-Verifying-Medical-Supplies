from langflow.business.components import BusinessComponent
from lfx.io import Output


class BusinessUnion(BusinessComponent):
    display_name = "Business Union"
    description = "Persistent business datasets: union"
    name = "BusinessUnion"
    kind = "union"
    outputs = [
        Output(display_name="Data", name="data", method="out_data", group_outputs=True),
    ]
