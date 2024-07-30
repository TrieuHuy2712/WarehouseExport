import json
import math
from datetime import datetime
from typing import List

import requests

from src.Exceptions import OrderError
from src.IRetrieveOrder import Web
from src.InputProduct import InputDetailProduct
from src.Model.Order import Order
from src.OrderRequest import OrderRequest
from src.utils import set_up_logger, get_value_of_config, get_item_information, convert_time_format_of_web, parse_to_time_format_of_web


class APIWebOrder(Web):
    def __init__(self, order: OrderRequest = None):
        self.logging = set_up_logger("Warehouse_Export")
        self.orders = []
        self.from_date = convert_time_format_of_web(order.from_date)
        self.to_date = convert_time_format_of_web(order.to_date)
        self.to_search_order = order.orders
        self.payment_methods = []
        self.item_information = get_item_information()
        self.products = self.__get_product_information__()
        self.cookies = self.authentication()
        self.meta_page = {}
        self.on_delivery = order.is_fulfilled_status
        self.base_from_date = parse_to_time_format_of_web(order.from_date)
        self.base_to_date = parse_to_time_format_of_web(order.to_date)

    def get_orders_by_date(self) -> List[Order]:
        try:
            self.logging.info(msg=f"Begin search API at Web")
            self.filter_orders_date_time()
            self.logging.info(msg=f"[Date] List API has been found on from web : {','.join([order.code for order in self.orders])}")
            if self.on_delivery:
                return self.filter_time()
            return self.orders
        except Exception as e:
            self.logging.error(msg=f"[Date] API Web Order got error by search: {e}")

    def filter_time(self):
        filter_orders = []
        for order in self.orders:
            format_string = "%H:%M:%S - %d/%m/%Y"
            try:
                parsed_date = datetime.strptime(order.created_on, format_string)
                if self.base_from_date <= parsed_date <= self.base_to_date: # Check base time when run auto
                    filter_orders.append(order)
            except ValueError as e:
                self.logging.error(msg=f"[Date] Cannot parsing create date of order {order.code}")
        return filter_orders


    @staticmethod
    def authentication():
        url = f"{get_value_of_config('api_url')}/login/"
        payload = f"email={get_value_of_config('website_login')}&password={get_value_of_config('website_password')}"
        headers = {
            'Content-Type': 'application/x-www-form-urlencoded'
        }
        response = requests.post(url=url, headers=headers, data=payload)
        return response.cookies.get_dict()

    def filter_orders_date_time(self):
        self._process_orders_from_page(1)
        for page in range(2, self.meta_page["total_page"] + 1):
            self._process_orders_from_page(page)

    def _process_orders_from_page(self, page):
        list_orders = self._get_list_order_from_page(page)
        for order in list_orders:
            self.__update_order_information__(order)
        self.orders.extend(list_orders)
        self.to_search_order.extend(order.code for order in list_orders)

    def _get_list_order_from_page(self, page):
        params = self.prepare_params_list_orders()
        state_delivery = 'on_delivery' if self.on_delivery else ''
        order_request = requests.get(f"{get_value_of_config('api_url')}/api/v1/orders/all?"
                                     f"time__icontains={params.get('time_request', '')}"
                                     f"&uid__icontains={params.get('order_request', '')}"
                                     f"&page={page}"
                                     f"&state={state_delivery}",
                                     cookies=self.cookies)
        parse_json = json.loads(order_request.text)["orders"]

        if self.meta_page.get('total', None) is None:
            self.meta_page["total"] = json.loads(order_request.text)['total']
            self.meta_page["current_page"] = json.loads(order_request.text)['page']
            self.meta_page["total_page"] = math.ceil(self.meta_page.get("total") / 10)

        return [Order.from_dict(order) for order in parse_json]

    def prepare_params_list_orders(self):
        if len(self.to_search_order) == 0:
            orders = ""
        elif len(self.to_search_order) == 1:
            orders = self.to_search_order[0]
        else:
            orders = f"{':'.join(self.to_search_order)}"

        time = f"{self.from_date} / {self.to_date}"

        return {"order_request": orders, "time_request": time}

    def __update_order_information__(self, order: Order):
        for order_line in order.order_line_items:
            order_line.is_composite = True
            for composite_item in order_line.composite_item_domains:
                composite_item.quantity = int(composite_item.original_quantity) * int(order_line.quantity)
                composite_item.unit = self.__get_product_details__(composite_item.sku).Unit

    def __get_product_details__(self, sku) -> InputDetailProduct:
        try:
            return [item for item in self.products if item.Product_Id == sku][0]
        except Exception:
            raise OrderError(message=f"Cannot found sku {sku} from resource. Please check again.")

    def __get_product_information__(self):
        return sum([prod.Product for prod in self.item_information], [])
