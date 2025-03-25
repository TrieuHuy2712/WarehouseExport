import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime

import numpy as np
import pandas as pd
from selenium.common import NoSuchElementException, ElementClickInterceptedException
from selenium.webdriver import Keys, ActionChains
from selenium.webdriver.common.by import By

from src.AppConfig import AppConfig
from src.Enums import Channel
from src.Exceptions import OrderError
from src.Model.Item import Item
from src.Model.Order import Order
from src.utils import set_up_logger, get_value_of_config, attempt_check_exist_by_xpath, \
    attempt_check_can_clickable_by_xpath, check_element_exist, check_element_not_exist


class AutomationMisaOrder:
    _thread_local = threading.local()

    def __init__(self, orders: list[Order], channel: Channel == Channel.SAPO):
        self.orders = orders
        self.logging = set_up_logger("Warehouse_Export")
        self.handle_orders = []
        self.channel = channel
        self.attempt = 1
        self.chunk_orders = [chunk.tolist() for chunk in
                             np.array_split(self.orders, int(get_value_of_config("chunk_size")))
                             if len(chunk) > 0]
        self.missing_orders = []

    def get_driver(self):
        """Trả về WebDriver riêng cho từng thread"""
        if not hasattr(self._thread_local, "driver"):
            self._thread_local.driver = AppConfig.get_chrome_driver()
        return self._thread_local.driver

    def send_orders_to_misa(self):
        try:
            with ThreadPoolExecutor(max_workers=len(self.chunk_orders)) as executor:
                futures = {executor.submit(self.send_orders, i + 1, chunk) for i, chunk in enumerate(self.chunk_orders)}

            self.logging.info(
                msg=f"[Misa-{self.channel.name}] "
                    f"Missing orders in running: {','.join({o.code for o in self.get_list_missing_orders()})}")
            self.logging.info(
                msg=f"[Misa-{self.channel.name}] "
                    f"Retry for missing orders: {','.join({o.code for o in self.get_list_missing_orders()})}")

            while len(self.get_list_missing_orders()) > 0 and self.attempt <= 10:
                self.missing_orders = self._get_list_missing_orders()
                self.chunk_orders = [chunk.tolist() for chunk in
                                     np.array_split(self.missing_orders, int(get_value_of_config("chunk_size")))
                                     if len(chunk) > 0]

                self.logging.info(
                    msg=f"[Misa-Sapo] Retry create missing order at {self.attempt}")  # Retry missing orders
                self.send_orders_to_misa()
                self.attempt = self.attempt + 1
        except Exception as e:
            self.logging.critical(msg=f"[Misa-{self.channel.name}] Automation Misa Order got error at : {e}")
        finally:
            self.logging.info(
                msg=f"[Misa-{self.channel.name}] "
                    f"Not handle orders: {','.join({o.code for o in self._get_list_missing_orders()})}")
            AppConfig().destroy_instance()

    def send_orders(self, chunk_id, orders: list[Order]):
        try:
            driver = self.get_driver()
            self.open_website(thread_id=chunk_id, driver=driver)
            time.sleep(3)
            self.authentication(driver=driver)
            driver.maximize_window()
            self.go_to_internal_accounting_data_page(driver=driver)
            self.handler_create_list_invoice(orders, driver=driver, thread_id=chunk_id)
        except Exception as e:
            self.logging.critical(msg=f"[Misa-{self.channel.name}] Automation Misa Order got error at : {e}")
        finally:
            self.logging.info(
                msg=f"[Misa-SAPO] Not handle orders at threads {chunk_id}: {','.join(o.code for o in self.orders if o.code not in self.handle_orders)}")
            # AppConfig().destroy_instance()
            self.close_driver()
            self.logging.info(msg=f"[Misa-SAPO] Completed automation Misa Order at thread {chunk_id}")

    def handler_create_list_invoice(self, orders: list[Order], driver, thread_id):
        for order in orders:
            try:
                self.go_to_warehouse_page(driver)
                self.create_detail_warehouse_invoice(order, driver)
                self.handle_orders.append(order.code)  # Add infor handled orders
            except OrderError as ex:
                self.logging.critical(
                    msg=f"[Misa-{self.channel.name}] Automation Misa Order {order.code} got error at : {ex.message}")
                self.open_website(thread_id=thread_id, driver=driver)

    def get_list_missing_orders(self) -> list[Order]:
        return [o for o in self.orders if o.code not in self.handle_orders]

    def create_detail_warehouse_invoice(self, order: Order, driver):
        try:
            # Input customer name
            input_customer_xpath = ('//div[text()="Tên khách hàng"]/parent::div/parent::div/parent::div/following'
                                    '-sibling::div//input')
            attempt_check_exist_by_xpath(input_customer_xpath, driver=driver)
            driver.find_element(By.XPATH, input_customer_xpath).send_keys(
                f"{get_value_of_config('environment')} Mã đơn hàng: {order.code}(Bán hàng qua {order.source_name})")

            # Input certificate number
            certificate_number_xpath = '//div[text()="Số chứng từ"]/parent::div/parent::div/parent::div/following-sibling::div//input'
            attempt_check_exist_by_xpath(certificate_number_xpath, driver=driver)

            current_certificate_number = driver.find_element(By.XPATH, certificate_number_xpath).get_attribute('value')
            unix_time = str(int(time.time() * 1000))
            new_certificate_number = current_certificate_number[:7] + '-' + unix_time

            driver.find_element(By.XPATH, certificate_number_xpath).send_keys(Keys.CONTROL + "a")
            driver.find_element(By.XPATH, certificate_number_xpath).send_keys(Keys.DELETE)

            driver.find_element(By.XPATH, certificate_number_xpath).send_keys(new_certificate_number)

            # Input detail
            if self.channel == Channel.SAPO:
                sku_quantity = self.__calculate_warehouse_quantity_item_by_SAPO__(order.order_line_items)
            else:
                sku_quantity = self.__calculate_warehouse_quantity_item_by_WEB__(order.order_line_items)
            add_line_button_xpath = '//div[normalize-space(text())="Thêm dòng"]/ancestor::button'

            for i in range(0, len(sku_quantity)):
                attempt_check_exist_by_xpath(add_line_button_xpath, driver=driver)
                time.sleep(2)

            current_row = 1
            for sku, quantity in sku_quantity.items():
                if current_row > 1:
                    driver.find_element(By.XPATH, add_line_button_xpath).click()
                    time.sleep(2)
                self.set_warehouse_data_for_table(sku, quantity, current_row, driver=driver)
                current_row += 1

            # Add commercial discount
            # self.set_invoice_appendix(order=order)
            # Save invoice
            save_button_xpath = '//button[@shortkey-target="Save"]'
            self.__action_click_with_xpath__(save_button_xpath, driver=driver)
            self.escape_current_invoice(driver=driver)
            self.logging.info(f"[Misa Warehouse] Created order {order.code}.")
        except Exception as e:
            self.logging.error(
                msg=f"[Misa Warehouse] Created warehouse {order.code} failed. got error: {e} Retry again")
            self.escape_current_invoice(driver=driver)
            self.go_to_warehouse_page(driver=driver)
            self.create_detail_warehouse_invoice(order=order, driver=driver)

    def set_invoice_appendix(self, order: Order, driver):
        created_date = datetime.strptime(order.created_on, '%Y-%m-%dT%H:%M:%SZ')
        note_button_xpath = '//div[normalize-space(text())="Thêm ghi chú"]/parent::button'

        # Company discount amount
        if sum(float(item.discount_amount) for item in order.order_line_items) > 0:
            # Click add new note line in the table
            self.__action_click_with_xpath__(xpath=note_button_xpath, driver=driver)
            company_discount_note_xpath = f'//table[@class="ms-table"]/tbody/tr[last()]/td[4]/div'
            self.__action_click_with_xpath__(company_discount_note_xpath, driver=driver)

            # Get the last line of table
            attempt_check_can_clickable_by_xpath(f'{company_discount_note_xpath}//input', driver=driver)
            col = driver.find_element(By.XPATH, f'{company_discount_note_xpath}//input')
            col.send_keys(f"Khuyến mãi của công ty theo chương trình khuyến mãi "
                          f"{created_date.month}/{created_date.year} "
                          f"trên sàn {order.source_name}")

        # Commercial discount amount
        if sum(float(item.distributed_discount_amount) for item in order.order_line_items) > 0:
            # Click add new note line in the table
            attempt_check_exist_by_xpath(note_button_xpath, driver=driver)
            driver.find_element(By.XPATH, note_button_xpath).click()
            commercial_discount_note_xpath = f'//table[@class="ms-table"]/tbody/tr[last()]/td[4]/div'
            self.__action_click_with_xpath__(commercial_discount_note_xpath, driver=driver)
            # Get the last line of table
            attempt_check_can_clickable_by_xpath(f'{commercial_discount_note_xpath}//input', driver=driver)
            col = driver.find_element(By.XPATH, f'{commercial_discount_note_xpath}//input')
            col.send_keys(f"Khuyến mãi trên sàn {order.source_name} theo chương trình khuyến mãi "
                          f"của sàn {created_date.month}/{created_date.year} ")

        # Click add new note line in the table
        self.__action_click_with_xpath__(note_button_xpath, driver=driver)
        note_xpath = f'//table[@class="ms-table"]/tbody/tr[last()]/td[4]/div'
        self.__action_click_with_xpath__(note_xpath, driver=driver)
        # Get the last line of table
        attempt_check_can_clickable_by_xpath(f'{note_xpath}//input', driver=driver)
        col = driver.find_element(By.XPATH, f'{note_xpath}//input')
        col.send_keys(f"Bổ sung đơn hàng ngày "
                      f"{created_date.day}/{created_date.month}/{created_date.year} "
                      f"(Mã đơn hàng: {order.code})")

    def set_warehouse_data_for_table(self, sku, quantity, current_row, driver):

        # SKU Code
        sku_xpath = f'//table[@class="ms-table"]/tbody/tr[{current_row}]/td[3]/div'
        self.__action_click_with_xpath__(sku_xpath, driver=driver)
        attempt_check_can_clickable_by_xpath(f'{sku_xpath}//input', driver=driver)
        col = driver.find_element(By.XPATH, f'{sku_xpath}//input')
        col.send_keys(sku)
        col.send_keys(Keys.TAB)

        # Warehouse
        warehouse_xpath = f'//table[@class="ms-table"]/tbody/tr[{current_row}]/td[5]/div'
        self.__action_click_with_xpath__(warehouse_xpath, driver=driver)
        self.__action_click_with_xpath__(f'{warehouse_xpath}//input', driver=driver)
        col = driver.find_element(By.XPATH, f'{warehouse_xpath}//input')
        col.send_keys(Keys.CONTROL, 'a')
        col.send_keys(Keys.DELETE)
        col.send_keys(get_value_of_config("warehouse_id"))
        time.sleep(2)
        col.send_keys(Keys.TAB)

        # Quantity
        quantity_xpath = f'//table[@class="ms-table"]/tbody/tr[{current_row}]/td[9]/div'
        self.__action_click_with_xpath__(quantity_xpath, driver=driver)
        attempt_check_can_clickable_by_xpath(f'{quantity_xpath}//input', driver=driver)
        col = driver.find_element(By.XPATH, f'{quantity_xpath}//input')
        col.send_keys(Keys.CONTROL + "a")
        col.send_keys(Keys.DELETE)
        time.sleep(2)
        col.send_keys(quantity)
        col.send_keys(Keys.TAB)

        # Check SKU is valid
        error_icon = f'//table[@class="ms-table"]/tbody/tr[{current_row}]/td[3]//div[contains(@class,"cell-error-icon")]'
        if check_element_exist(error_icon, driver=driver):
            self.escape_current_invoice(driver=driver)
            self.__action_click_with_xpath__('//div[@id="message-box"]//div[contains(text(),"Không")]/parent::button',
                                             driver=driver)
            raise OrderError(message=f"[Misa] Cannot found the Product {sku} in the system.")

    def open_website(self, thread_id, driver):
        self.logging.info("[Misa] Thread run {}".format(thread_id))
        url = get_value_of_config("misa_url")
        driver.get(url)

    def go_to_warehouse_page(self, driver):
        # Check expand collapse
        self.expand_menu_attribute(driver)

        # Click warehouse tag
        warehouse_xpath = '//div[text()="Kho"]/parent::a'
        self.__action_click_with_xpath__(warehouse_xpath, driver=driver)

        # Click export warehouse
        export_warehouse_xpath = '(//div[normalize-space(text())="Xuất kho"])[1]'
        self.__action_click_with_xpath__(export_warehouse_xpath, driver=driver)

        # Click add button
        add_invoice_xpath = '//div[normalize-space(text())="Thêm"]/parent::button'
        self.__action_click_with_xpath__(add_invoice_xpath, driver=driver)

    def authentication(self, driver):
        # Input email
        email_xpath = '//input[@name="username"]'
        attempt_check_exist_by_xpath(email_xpath, driver=driver)
        driver.find_element(By.XPATH, email_xpath).send_keys(get_value_of_config("misa_login"))

        # Input password
        password_xpath = '//input[@name="pass"]'
        attempt_check_exist_by_xpath(password_xpath, driver=driver)
        driver.find_element(By.XPATH, password_xpath).send_keys(get_value_of_config("misa_password"))

        # Click login button
        button_xpath = '//button[@objname="jBtnLogin"]'
        attempt_check_can_clickable_by_xpath(button_xpath, driver=driver)
        driver.find_element(By.XPATH, button_xpath).click()

        # Check_current_session
        session_xpath = '//div[text()="Tiếp tục đăng nhập"]/parent::button'
        try:
            attempt_check_exist_by_xpath(session_xpath, driver=driver)
            driver.find_element(By.XPATH, session_xpath).click()
        except NoSuchElementException as e:
            self.logging.info(msg="No users use this account")
        finally:
            return

    def go_to_internal_accounting_data_page(self, driver):
        current_db_name = get_value_of_config('header_current_db_name')
        db_button_xpath = '//div[@class="header-current-db-name"]'
        attempt_check_exist_by_xpath(db_button_xpath, driver=driver)
        if driver.find_element(By.XPATH, db_button_xpath).text != current_db_name:
            driver.find_element(By.XPATH, db_button_xpath).click()
            table_db_button = f'//p[@title="{current_db_name}"]//ancestor::table'
            self.__action_click_with_xpath__(table_db_button, driver=driver)
            attempt_check_exist_by_xpath(
                '//div[@class="title-branch"]/following-sibling::div/div[@class="title-header"]', driver=driver)

    def escape_current_invoice(self, driver):
        # Escape
        attempt_check_can_clickable_by_xpath('//div[contains(@class,"close-btn header")]', driver=driver)
        driver.find_element(By.XPATH, '//div[contains(@class,"close-btn header")]').click()

        # Check if existed after unit time
        if not check_element_not_exist('//div[@class="title"]', timeout=30, driver=driver):
            self.escape_current_invoice(driver=driver)

    @staticmethod
    def __calculate_warehouse_quantity_item_by_SAPO__(line_items: list[Item]) -> dict:
        data = []

        for item in line_items:
            if item.is_composite:
                for it in item.composite_item_domains:
                    data.append((it.sku, it.quantity))
            else:
                data.append((item.sku, item.quantity))

        df = pd.DataFrame(data, columns=['sku', 'quantity'])
        sku_quantity = df.groupby('sku')['quantity'].sum().to_dict()

        return sku_quantity

    @staticmethod
    def __calculate_warehouse_quantity_item_by_WEB__(lines_items: list[Item]) -> dict:
        composite_items = sum([item.composite_item_domains for item in lines_items], [])
        df = pd.DataFrame(composite_items)
        result_df = df.groupby('sku')['quantity'].sum().reset_index()
        return result_df.set_index('sku').to_dict()['quantity']

    def __action_click_with_xpath__(self, xpath, driver):
        try:
            attempt_check_can_clickable_by_xpath(xpath, driver=driver)
            driver.find_element(By.XPATH, xpath).click()
        except ElementClickInterceptedException as e:
            element = driver.find_element(By.XPATH, xpath)
            ActionChains(driver).move_to_element(element).click().perform()
        except NoSuchElementException as e:
            raise OrderError(message=f"No such element. {e}")
        except Exception as e:
            raise OrderError(message=f"Cannot click element. {e}")

    def close_driver(self):
        """Đóng WebDriver của thread hiện tại nếu tồn tại."""
        if hasattr(self._thread_local, "driver"):
            self._thread_local.driver.quit()
            del self._thread_local.driver  # Xóa WebDriver khỏi thread-local storage

    def _get_list_missing_orders(self) -> list[Order]:
        return [o for o in self.orders if o.code not in self.handle_orders]

    def expand_menu_attribute(self, driver):
        attempt_check_exist_by_xpath('//div[@id="menu-container"]', driver=driver)
        menu_attribute_xpath = driver.find_element(By.ID, 'menu-container')
        if "expand" not in menu_attribute_xpath.get_attribute("class"):
            # Click collapse button
            collapse_button_xpath = "//div[contains(@class, 'collapse-option')]//div[contains(@class, 'menu-item') and contains(@class, 'router-link-active')]"
            attempt_check_exist_by_xpath(collapse_button_xpath, driver=driver)
            self.__action_click_with_xpath__(collapse_button_xpath, driver=driver)
