from typing import List

from src.Enums import SapoChannel


class OrderRequest:
    orders: List[str] = []
    from_date: str = None
    to_date: str = None
    sapo_channel: SapoChannel = SapoChannel.All
    is_complete_order_status: bool = True
    is_fulfilled_status: bool = True # Luôn trong trạng thái giao hàng