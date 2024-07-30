import time
from datetime import datetime

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
    attempt_check_can_clickable_by_xpath, check_element_can_clickable, check_element_exist, check_element_not_exist


class AutomationMisaOrder:
    def __init__(self, orders: list[Order], channel: Channel == Channel.SAPO):
        self.orders = orders
        self.logging = set_up_logger("Warehouse_Export")
        self.driver = AppConfig().chrome_driver
        self.handle_orders = []
        self.channel = channel
        self.attempt = 1

    def send_orders_to_misa(self):
        try:
            self.open_website()
            self.authentication()
            self.driver.maximize_window()
            self.go_to_internal_accounting_data_page()
            self.handler_create_list_invoice(self.orders)
            self.logging.info(
                msg=f"[Misa-{self.channel.name}] Missing orders in running: {','.join({o.code for o in self.get_list_missing_orders()})}")
            self.logging.info(
                msg=f"[Misa-{self.channel.name}] Retry for missing orders: {','.join({o.code for o in self.get_list_missing_orders()})}")

            while len(self.get_list_missing_orders()) > 0 and self.attempt <= 10:
                missing_orders = self.get_list_missing_orders()
                self.logging.info(
                    msg=f"[Misa-{self.channel.name}] Retry create missing order at {self.attempt}")
                self.handler_create_list_invoice(missing_orders) # Retry missing orders
                self.attempt = self.attempt + 1
        except Exception as e:
            self.logging.critical(msg=f"[Misa-{self.channel.name}] Automation Misa Order got error at : {e}")
        finally:
            self.logging.info(
                msg=f"[Misa-{self.channel.name}] Not handle orders: {','.join({o.code for o in self.get_list_missing_orders()})}")
            AppConfig().destroy_instance()

    def handler_create_list_invoice(self, orders: list[Order]):
        for order in orders:
            try:
                self.go_to_warehouse_page()
                self.create_detail_warehouse_invoice(order)
                self.handle_orders.append(order.code)  # Add infor handled orders
            except OrderError as ex:
                self.logging.critical(msg=f"[Misa-{self.channel.name}] Automation Misa Order {order.code} got error at : {ex.message}")
                self.open_website()

    def get_list_missing_orders(self) -> list[Order]:
        return [o for o in self.orders if o.code not in self.handle_orders]

    def create_detail_warehouse_invoice(self, order: Order):
        try:
            # Input customer name
            input_customer_xpath = '//div[text()="Tên khách hàng"]/parent::div/parent::div/parent::div/following-sibling::div//input'
            attempt_check_exist_by_xpath(input_customer_xpath)
            self.driver.find_element(By.XPATH, input_customer_xpath).send_keys(
                f"{get_value_of_config('environment')} Mã đơn hàng: {order.code}(Bán hàng qua {order.source_name})")

            # Input detail
            if self.channel == Channel.SAPO:
                sku_quantity = self.__calculate_warehouse_quantity_item_by_SAPO__(order.order_line_items)
            else:
                sku_quantity = self.__calculate_warehouse_quantity_item_by_WEB__(order.order_line_items)
            add_line_button_xpath = '//div[normalize-space(text())="Thêm dòng"]/ancestor::button'

            for i in range(0, len(sku_quantity)):
                attempt_check_exist_by_xpath(add_line_button_xpath)
                time.sleep(2)

            current_row = 1
            for sku, quantity in sku_quantity.items():
                if current_row > 1:
                    self.driver.find_element(By.XPATH, add_line_button_xpath).click()
                    time.sleep(2)
                self.set_warehouse_data_for_table(sku, quantity, current_row)
                current_row += 1

            # Add commercial discount
            #self.set_invoice_appendix(order=order)
            # Save invoice
            save_button_xpath = '//button[@shortkey-target="Save"]'
            self.__action_click_with_xpath__(save_button_xpath)
            self.escape_current_invoice()
            self.logging.info(f"[Misa Warehouse] Created order {order.code}.")
        except Exception as e:
            self.logging.error(msg=f"[Misa Warehouse] Created warehouse {order.code} failed.")
            raise OrderError(message=f"Have error in create Misa warehouse. {e}")

    def set_invoice_appendix(self, order: Order):
        created_date = datetime.strptime(order.created_on, '%Y-%m-%dT%H:%M:%SZ')
        note_button_xpath = '//div[normalize-space(text())="Thêm ghi chú"]/parent::button'

        # Company discount amount
        if sum(float(item.discount_amount) for item in order.order_line_items) > 0:
            # Click add new note line in the table
            self.__action_click_with_xpath__(xpath=note_button_xpath)
            company_discount_note_xpath = f'//table[@class="ms-table"]/tbody/tr[last()]/td[4]/div'
            self.__action_click_with_xpath__(company_discount_note_xpath)

            # Get the last line of table
            attempt_check_can_clickable_by_xpath(f'{company_discount_note_xpath}//input')
            col = self.driver.find_element(By.XPATH, f'{company_discount_note_xpath}//input')
            col.send_keys(f"Khuyến mãi của công ty theo chương trình khuyến mãi "
                          f"{created_date.month}/{created_date.year} "
                          f"trên sàn {order.source_name}")

        # Commercial discount amount
        if sum(float(item.distributed_discount_amount) for item in order.order_line_items) > 0:
            # Click add new note line in the table
            attempt_check_exist_by_xpath(note_button_xpath)
            self.driver.find_element(By.XPATH, note_button_xpath).click()
            commercial_discount_note_xpath = f'//table[@class="ms-table"]/tbody/tr[last()]/td[4]/div'
            self.__action_click_with_xpath__(commercial_discount_note_xpath)
            # Get the last line of table
            attempt_check_can_clickable_by_xpath(f'{commercial_discount_note_xpath}//input')
            col = self.driver.find_element(By.XPATH, f'{commercial_discount_note_xpath}//input')
            col.send_keys(f"Khuyến mãi trên sàn {order.source_name} theo chương trình khuyến mãi "
                          f"của sàn {created_date.month}/{created_date.year} ")

        # Click add new note line in the table
        self.__action_click_with_xpath__(note_button_xpath)
        note_xpath = f'//table[@class="ms-table"]/tbody/tr[last()]/td[4]/div'
        self.__action_click_with_xpath__(note_xpath)
        # Get the last line of table
        attempt_check_can_clickable_by_xpath(f'{note_xpath}//input')
        col = self.driver.find_element(By.XPATH, f'{note_xpath}//input')
        col.send_keys(f"Bổ sung đơn hàng ngày "
                      f"{created_date.day}/{created_date.month}/{created_date.year} "
                      f"(Mã đơn hàng: {order.code})")

    def set_warehouse_data_for_table(self, sku, quantity, current_row):
        # SKU Code
        sku_xpath = f'//table[@class="ms-table"]/tbody/tr[{current_row}]/td[3]/div'
        self.__action_click_with_xpath__(sku_xpath)
        attempt_check_can_clickable_by_xpath(f'{sku_xpath}//input')
        col = self.driver.find_element(By.XPATH, f'{sku_xpath}//input')
        col.send_keys(sku)
        col.send_keys(Keys.TAB)

        # Warehouse
        warehouse_xpath = f'//table[@class="ms-table"]/tbody/tr[{current_row}]/td[5]/div'
        self.__action_click_with_xpath__(warehouse_xpath)
        self.__action_click_with_xpath__(f'{warehouse_xpath}//input')
        col = self.driver.find_element(By.XPATH, f'{warehouse_xpath}//input')
        col.send_keys(Keys.CONTROL, 'a')
        col.send_keys(Keys.DELETE)
        col.send_keys(get_value_of_config("warehouse_id"))

        # Quantity
        quantity_xpath = f'//table[@class="ms-table"]/tbody/tr[{current_row}]/td[9]/div'
        self.__action_click_with_xpath__(quantity_xpath)
        attempt_check_can_clickable_by_xpath(f'{quantity_xpath}//input')
        col = self.driver.find_element(By.XPATH, f'{quantity_xpath}//input')
        col.send_keys(quantity)
        col.send_keys(Keys.TAB)

        # Check SKU is valid
        error_icon = f'//table[@class="ms-table"]/tbody/tr[{current_row}]/td[3]//div[contains(@class,"cell-error-icon")]'
        if check_element_exist(error_icon):
            self.escape_current_invoice()
            self.__action_click_with_xpath__('//div[@id="message-box"]//div[contains(text(),"Không")]/parent::button')
            raise OrderError(message=f"[Misa] Cannot found the Product {sku} in the system.")

    def open_website(self):
        url = get_value_of_config("misa_url")
        self.driver.get(url)

    def go_to_warehouse_page(self):
        # Click warehouse tag
        warehouse_xpath = '//div[text()="Kho"]/parent::a'
        self.__action_click_with_xpath__(warehouse_xpath)

        # Click export warehouse
        export_warehouse_xpath = '(//div[normalize-space(text())="Xuất kho"])[1]'
        self.__action_click_with_xpath__(export_warehouse_xpath)

        # Click add button
        add_invoice_xpath = '//div[normalize-space(text())="Thêm"]/parent::button'
        self.__action_click_with_xpath__(add_invoice_xpath)

    def authentication(self):
        # Input email
        email_xpath = '//input[@name="username"]'
        attempt_check_exist_by_xpath(email_xpath)
        self.driver.find_element(By.XPATH, email_xpath).send_keys(get_value_of_config("misa_login"))

        # Input password
        password_xpath = '//input[@name="pass"]'
        attempt_check_exist_by_xpath(password_xpath)
        self.driver.find_element(By.XPATH, password_xpath).send_keys(get_value_of_config("misa_password"))

        # Click login button
        button_xpath = '//div[@objname="jBtnLogin"]'
        attempt_check_can_clickable_by_xpath(button_xpath)
        self.driver.find_element(By.XPATH, button_xpath).click()

        # Check_current_session
        session_xpath = '//div[text()="Tiếp tục đăng nhập"]/parent::button'
        try:
            attempt_check_exist_by_xpath(session_xpath)
            self.driver.find_element(By.XPATH, session_xpath).click()
        except NoSuchElementException as e:
            self.logging.info(msg="No users use this account")
        finally:
            return

    def go_to_internal_accounting_data_page(self):
        current_db_name = get_value_of_config('header_current_db_name')
        db_button_xpath = '//div[@class="header-current-db-name"]'
        attempt_check_exist_by_xpath(db_button_xpath)
        if self.driver.find_element(By.XPATH, db_button_xpath).text != current_db_name:
            self.driver.find_element(By.XPATH, db_button_xpath).click()
            table_db_button = f'//p[@title="{current_db_name}"]//ancestor::table'
            self.__action_click_with_xpath__(table_db_button)
            attempt_check_exist_by_xpath('//div[@class="title-branch"]/following-sibling::div/div[@class="title-header"]')

    def escape_current_invoice(self):
        # Escape
        attempt_check_can_clickable_by_xpath('//div[contains(@class,"close-btn header")]')
        self.driver.find_element(By.XPATH, '//div[contains(@class,"close-btn header")]').click()

        # Check if existed after unit time
        if not check_element_not_exist('//div[@class="title"]', timeout=30):
            self.escape_current_invoice()

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

    def __action_click_with_xpath__(self, xpath):
        try:
            attempt_check_can_clickable_by_xpath(xpath)
            self.driver.find_element(By.XPATH, xpath).click()
        except ElementClickInterceptedException as e:
            element = self.driver.find_element(By.XPATH, xpath)
            ActionChains(self.driver).move_to_element(element).click().perform()
        except NoSuchElementException as e:
            raise OrderError(message=f"No such element. {e}")
        except Exception as e:
            raise OrderError(message=f"Cannot click element. {e}")
