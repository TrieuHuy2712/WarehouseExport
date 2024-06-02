from dataclasses import dataclass

from dataclasses_json import dataclass_json

@dataclass_json
@dataclass
class InputDetailProduct:
    Product_Id: str
    Product_Name: str
    Product_Quantity: int
    Unit: str

@dataclass_json
@dataclass
class InputProduct:
    Item_Id: str
    Item_Name: str
    Product: list[InputDetailProduct]


