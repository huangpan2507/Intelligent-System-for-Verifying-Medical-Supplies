# ruff: noqa: INP001 - discovered inline component bundle.
from langflow.business.components import BusinessComponent
from lfx.io import Output


class BusinessDatabaselookup(BusinessComponent):
    display_name = "Business Database Lookup"
    description = "Read related database records using upstream keys and validate the association."
    name = "BusinessDatabaselookup"
    kind = "databaselookup"
    outputs = [
        Output(display_name="Data", name="data", method="out_data", group_outputs=True),
        Output(display_name="Issues", name="issues", method="out_issues", group_outputs=True),
    ]
