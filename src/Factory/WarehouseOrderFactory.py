from abc import ABC, abstractmethod
from typing import List

from src.APIWebOrder import APIWebOrder
from src.AutomationMisaOrder import AutomationMisaOrder
from src.AutomationSapoOrder import AutomationSapoOrder
from src.Enums import SapoShop, Category, Channel
from src.Model.Order import Order
from src.OrderRequest import OrderRequest


class WarehouseOrderFactory(ABC):
    @abstractmethod
    def create_web_order(self, order: OrderRequest):
        pass

    @abstractmethod
    def create_sapo_order(self, order: OrderRequest, shop: SapoShop):
        pass

    @staticmethod
    def submit_order(orders: List[Order], channel: Channel):
        auto_misa = AutomationMisaOrder(orders=orders, channel=channel)
        auto_misa.send_orders_to_misa()

    @staticmethod
    def set_category_request(request: Category):
        if request == Category.Auto:
            return OrderAutoFactory()
        else:
            return OrderAPIFactory()


class OrderAutoFactory(WarehouseOrderFactory):
    def create_web_order(self, order: OrderRequest):
        pass

    def create_sapo_order(self, order: OrderRequest, shop: SapoShop):
        return AutomationSapoOrder(order=order, shop=shop)


class OrderAPIFactory(WarehouseOrderFactory):
    def create_web_order(self, order: OrderRequest):
        return APIWebOrder(order)

    def create_sapo_order(self, shop: SapoShop):
        pass
