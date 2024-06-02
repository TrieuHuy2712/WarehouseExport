from abc import abstractmethod, ABC
from typing import List

from src.Model.Order import Order


class Web(ABC):
    @abstractmethod
    def get_orders_by_date(self) -> List[Order]:
        # Return orders from date and to date
        pass


class SAPO(ABC):
    @abstractmethod
    def get_orders_by_date(self) -> List[Order]:
        # Return orders from date and to date
        pass