from langflow.business.components import BusinessComponent
from lfx.io import Output


class BusinessDatabase(BusinessComponent):
    display_name = "Business Database"
    description = "Persistent business datasets: database"
    name = "BusinessDatabase"
    kind = "database"
    outputs = [
        Output(display_name="Data", name="data", method="out_data", group_outputs=True),
    ]
