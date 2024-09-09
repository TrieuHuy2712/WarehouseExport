from dataclasses import dataclass
from typing import Optional

from dataclasses_json import dataclass_json


@dataclass_json
@dataclass
class SaleOrder:
    total_sales: str = None
    last_order_on: str = None
    returned_item_quantity: int = 0
    net_quantity: int = 0
    order_purchases: int = None
