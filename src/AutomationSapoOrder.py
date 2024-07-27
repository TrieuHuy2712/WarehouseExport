import json
import math
from typing import List

import requests
from selenium.webdriver.common.by import By

from src.AppConfig import AppConfig
from src.Enums import SapoShop
from src.IRetrieveOrder import SAPO
from src.Model.Item import CompositeItem, Item
from src.Model.Order import Order
from src.OrderRequest import OrderRequest
from src.utils import set_up_logger, get_value_of_config, get_item_information, check_element_can_clickable, \
    parse_time_to_vietnam_zone, parse_time_to_GMT


def _update_product_with_sub_product(product, item, sub_product):
    product.price = sub_product["price"] * item.quantity
    product.sku = sub_product["sub_sku"]
    product.product_name = sub_product["sub_name"]
    product.quantity = item.quantity


class AutomationSapoOrder(SAPO):
    def __init__(self, shop: SapoShop, order: OrderRequest = None):
        self.driver = AppConfig().chrome_driver
        self.logging = set_up_logger("Warehouse_Export")
        self.domain = self.get_domain(shop)
        self.orders = []
        self.from_date = parse_time_to_GMT(order.from_date)
        self.to_date = parse_time_to_GMT(order.to_date)
        self.to_search_order = order.orders
        self.payment_methods = []
        self.item_information = get_item_information()
        self.order_sources = []
        self.is_complete = order.is_complete_order_status
        self.is_composite_fulfillment_status = order.is_fulfilled_status

    def get_orders_by_date(self) -> List[Order]:
        try:
            self.open_website()
            self.authentication()
            self.click_domain_shop()
            self.driver.maximize_window()
            self.handle_windows()
            self.go_to_order_page()
            # Get payment method
            self.payment_methods = self.get_payment_methods()
            self.order_sources = self.get_order_sources()
            is_empty_search = len(self.to_search_order) > 0
            self.filter_orders_date_time(is_available_search_order=is_empty_search)
            self.logging.info(msg=f"Begin search API at orders {self.domain}")
            for order in self.orders:
                try:
                    self.get_information_order(order)
                    self.get_order_source(order)
                    order.created_on = parse_time_to_vietnam_zone(order.created_on)
                except Exception as e:
                    self.logging.critical(msg=f"[Date]Automation Sapo Order got error at get at order {order.code} "
                                              f"by date: {e}")
        except Exception as e:
            self.logging.critical(msg=f"[Date]Automation Sapo Order got error at get orders by date: {e}")
        finally:
            AppConfig().destroy_instance()
            self.logging.info(
                msg=f"[Date] List API at {self.domain} has been found on from Sapo API : {','.join([order.code for order in self.orders])}")
            return self.orders

    def open_website(self):
        url = get_value_of_config("sapo_url")
        self.driver.get(url)

    def authentication(self):
        self.input_login_phone()
        self.input_login_password()
        self.click_login_button()

    def click_domain_shop(self):
        if get_value_of_config('sapo_quoc_co_shop') in self.domain:
            xpath = f'// span[text()="{get_value_of_config("sapo_quoc_co_shop")}"]/parent::div'
        elif get_value_of_config('sapo_giang_shop') in self.domain:
            xpath = f'// span[text()="{get_value_of_config("sapo_giang_shop")}"]/parent::div'
        check_element_can_clickable(xpath, By.XPATH)
        self.driver.find_element(By.XPATH, xpath).click()

    def get_information_order(self, order):
        for item in order.order_line_items:
            if item.price != '0':
                item.discount_rate = str(round(float(item.discount_value) * 100 / float(item.price), 2))
            information_item = self.find_item_by_id(item_id=item.barcode)
            # Check sku in composite process
            if item.is_composite:
                self._process_composite_item(item)
            elif item.sku in list(set(i.Item_Id for i in self.item_information)):
                self.get_combo_item(item=item)
            elif information_item is not None:
                self._update_item_from_information(item, information_item)

    def get_combo_item(self, item: Item):
        list_composite_item = [it for it in self.item_information if item.sku == it.Item_Id]
        composite_item = list_composite_item[0]
        item.is_composite = True
        for detail in composite_item.Product:
            item.composite_item_domains.append(
                CompositeItem(sku=detail.Product_Id,
                              unit=detail.Unit,
                              product_name=detail.Product_Name,
                              quantity=item.quantity * detail.Product_Quantity))

    def _process_composite_item(self, item):
        composite_items = self._fetch_composite_items(item.variant_id)
        for product in item.composite_item_domains:
            for sub_product in composite_items:
                if product.product_id == sub_product["sub_product_id"]:
                    self._update_product_from_sub_product(product, item, sub_product)

    def _update_product_from_sub_product(self, product, item, sub_product):
        information_sub_item = self.find_item_by_sub_id(item.barcode, sub_product["sub_sku"])
        if information_sub_item:
            self._update_product_with_information(product, item, information_sub_item)
        else:
            _update_product_with_sub_product(product, item, sub_product)

    def find_item_by_sub_id(self, item_id, product_id):
        for item in self.item_information:
            if item.Item_Id == item_id:
                sub_product = [sub_item for sub_item in item.Product if sub_item.Product_Id == product_id]
                if len(sub_product) > 0:
                    return sub_product[0]

    @staticmethod
    def _update_product_with_information(product, item, information):
        product.sku = information.Product_Id
        product.product_name = information.Product_Name
        product.quantity = information.Product_Quantity * item.quantity
        product.unit = information.Unit

    @staticmethod
    def _update_item_from_information(item, information):
        item.product_name = information.Product[0].Product_Name
        item.unit = information.Product[0].Unit

    def _fetch_composite_items(self, variant_id):
        try:
            response = requests.get(
                f"{self.domain}/admin/variants/search.json?page=1&limit=250&status=active%2Cinactive%2Cdeleted&ids={variant_id}",
                cookies=self.get_website_cookie()
            )
            response.raise_for_status()
            return json.loads(response.text)['variants'][0]['composite_items']
        except requests.RequestException as e:
            print(f"Error fetching composite items: {e}")
            return []

    def find_item_by_id(self, item_id):
        try:
            return [item for item in self.item_information if item.Item_Id == item_id][0]
        except:
            return None

    def filter_orders_date_time(self, is_available_search_order=False):
        limit = 100

        meta_data = self.get_meta_order_from_page()
        total_page = math.ceil(meta_data.get("total") / limit)

        for page in range(1, total_page + 1 if total_page > 1 else 2):
            list_order = self.get_list_order_from_page(page)

            if not is_available_search_order:
                self.orders.extend(list_order)
                self.to_search_order.extend([order.code for order in list_order])
            else:
                list_current_orders = [order.code for order in list_order]
                self.to_search_order = list(set(self.to_search_order) & set(list_current_orders))
                self.orders.extend([order for order in list_order if order.code in self.to_search_order])

    def get_list_order_from_page(self, page):
        status = "finalized" if self.is_complete else ""
        string_json = requests.get(f'{self.domain}/admin/orders.json?page={page}'
                                   f'&limit=100'
                                   f'&status={status}'
                                   f'&created_on_max={self.to_date}'
                                   f'&created_on_min={self.from_date}'
                                   f'&return_status=unreturned'
                                   f'{"&composite_fulfillment_status=fulfilled" if self.is_composite_fulfillment_status else ""}'
                                   # f'&source_id=7925877,7771008,6677743,6671556,6671548,6671547,6671550,6671549,6671545',
                                   f'&source_id={self.order_sources}',
                                   cookies=self.get_website_cookie())
        parse_json = json.loads(string_json.text)['orders']
        return [Order.from_dict(order) for order in parse_json]

    def get_meta_order_from_page(self):
        status = "finalized" if self.is_complete else ""
        string_json = requests.get(f'{self.domain}/admin/orders.json?page=1'
                                   f'&limit=100'
                                   f'&status={status}'
                                   f'&created_on_max={self.to_date}'
                                   f'&created_on_min={self.from_date}'
                                   f'&return_status=unreturned'
                                   f'{"&composite_fulfillment_status=fulfilled" if self.is_composite_fulfillment_status else ""}'
                                   f'&source_id={self.order_sources}',
                                   cookies=self.get_website_cookie())
        return json.loads(string_json.text)['metadata']

    def get_order_sources(self):
        string_json = requests.get(f'{self.domain}/admin/order_sources.json?query=&page=1'
                                   f'&limit=100',
                                   cookies=self.get_website_cookie())
        order_sources = json.loads(string_json.text)['order_sources']
        default_sources = get_value_of_config('order_sources').split(',')
        id_sources = [str(sources.get("id")) for sources in order_sources if sources.get("name") in default_sources]
        return ','.join(id_sources)

    def handle_windows(self):
        sale_order = '//span[text()="Đơn hàng"]'
        check_element_can_clickable(sale_order, By.XPATH)

        default_window = self.driver.window_handles[0]
        handle_window = self.driver.window_handles[1]
        self.driver.switch_to.window(window_name=default_window)
        self.driver.close()
        self.driver.switch_to.window(window_name=handle_window)

    def go_to_order_page(self):
        sale_order = '//span[text()="Đơn hàng"]'
        check_element_can_clickable(sale_order, By.XPATH)
        self.driver.find_element(By.XPATH, sale_order).click()

        admin_order = '//a[@href="/admin/orders"]'
        check_element_can_clickable(admin_order, By.XPATH)
        self.driver.find_element(By.XPATH, admin_order).click()

    def input_login_phone(self):
        phone = get_value_of_config("sapo_phone")
        self.driver.find_element(By.XPATH, '//*[@id="username"]').send_keys(phone)

    def input_login_password(self):
        password = get_value_of_config("sapo_password")
        self.driver.find_element(By.XPATH, '//*[@id="password"]').send_keys(password)

    def click_login_button(self):
        self.driver.find_element(By.XPATH, '//*[@id="pos-login-form"]/div[4]/button').click()

    def get_payment_methods(self):
        string_json = requests.get(
            f"{self.domain}/admin/payment_methods.json?in_types=online%2Ccash%2Cmpos%2Ctransfer%2Cpoint%2Ccod%2Cpayment_gateway%2Cqr_code%2Cinstallment%2Cpayment_portal%2Cvietqr_basic&include_inactive=true",
            cookies=self.get_website_cookie())
        string_json = json.loads(string_json.text)['payment_methods']
        return string_json

    def get_website_cookie(self):
        return {cookie['name']: cookie['value'] for cookie in self.driver.get_cookies()}

    def get_order_source(self, order: Order):
        json_request = requests.get(f"{self.domain}/admin/order_sources/{order.source_id}.json",
                                    cookies=self.get_website_cookie())
        string_json = json.loads(json_request.text)['order_source']
        order.source_name = string_json['name']

    @staticmethod
    def get_domain(shop: SapoShop):
        if shop == SapoShop.QuocCoQuocNghiep:
            return f"https://{get_value_of_config('sapo_quoc_co_shop')}"
        elif shop == SapoShop.ThaoDuocGiang:
            return f"https://{get_value_of_config('sapo_giang_shop')}"
        return ''
