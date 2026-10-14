from langflow.business.components import BusinessComponent
from lfx.io import Output


class BusinessCompare(BusinessComponent):
    display_name = "Business Compare"
    description = "Persistent business datasets: compare"
    name = "BusinessCompare"
    kind = "compare"
    outputs = [
        Output(display_name="Data", name="data", method="out_data", group_outputs=True),
    ]
