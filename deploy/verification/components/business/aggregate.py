from langflow.business.components import BusinessComponent
from lfx.io import Output


class BusinessAggregate(BusinessComponent):
    display_name = "Business Aggregate"
    description = "Persistent business datasets: aggregate"
    name = "BusinessAggregate"
    kind = "aggregate"
    outputs = [
        Output(display_name="Data", name="data", method="out_data", group_outputs=True),
        Output(display_name="Members", name="members", method="out_members", group_outputs=True),
    ]
