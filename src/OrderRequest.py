from typing import List

from src.Enums import SapoChannel


class OrderRequest:
    orders: List[str] = []
    from_date: str = None
    to_date: str = None
    sapo_channel: SapoChannel = SapoChannel.All