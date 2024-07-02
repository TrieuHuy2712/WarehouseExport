# This is a sample Python script.
import argparse
from datetime import datetime, timedelta
from typing import List

from src.Enums import SapoShop, Category, Channel
from src.Factory.WarehouseOrderFactory import OrderAutoFactory, OrderAPIFactory, WarehouseOrderFactory
from src.Model.Order import Order
from src.OrderRequest import OrderRequest


def get_command_line_arguments():
    parser = argparse.ArgumentParser(description="Warehouse Export CLI")

    parser.add_argument('-a', '--auto', help='Run in auto mode')
    parser.add_argument('-s', '--shop', help='Run in auto mode', default=str(0))
    parser.add_argument('-d', '--days', help='Input from date and end date')

    args = parser.parse_args()

    return args


def get_dates():
    from_date = (datetime.now().replace(hour=17, minute=0, second=0, microsecond=0) + timedelta(days=-1)).strftime('%Y-%m-%dT%H:%M:%SZ')
    to_date = datetime.now().replace(hour=16, minute=59, second=59, microsecond=0).strftime('%Y-%m-%dT%H:%M:%SZ')
    return from_date, to_date


def get_user_dates():
    from_date = datetime.fromisoformat(input('Start Date Time YYYY-mm-dd HH:MM:SS: (Ex: 2024-03-23 12:00:00)')).strftime('%Y-%m-%dT%H:%M:%SZ')
    to_date = datetime.fromisoformat(input('End Date Time YYYY-mm-dd HH:MM:SS: (Ex: 2024-03-30 12:00:00)')).strftime('%Y-%m-%dT%H:%M:%SZ')
    return from_date, to_date


def process_orders(order_request: OrderRequest, shop_type) -> List[Order]:
    order_factory = WarehouseOrderFactory.set_category_request(Category.Auto)
    if shop_type == 3:
        # Case Web
        order_factory = WarehouseOrderFactory.set_category_request(Category.API)
        orders = order_factory.create_web_order(order_request).get_orders_by_date()
        order_factory.submit_order(orders, channel= Channel.WEB)
    else:
        # Case Shop: QuocCoQuocNghiep, ThaoDuocGiang
        orders = order_factory.create_sapo_order(order_request, SapoShop(shop_type)).get_orders_by_date()
        order_factory.submit_order(orders, channel= Channel.SAPO)



# Press the green button in the gutter to run the script.
if __name__ == '__main__':
    print('Warehouse Export')
    args = get_command_line_arguments()
    order_request = OrderRequest()
    orders = []
    if args.auto:
        order_request.from_date, order_request.to_date = get_dates()
        process_orders(order_request, int(args.shop))
    elif args.days:
        order_request.from_date, order_request.to_date = get_user_dates()
        process_orders(order_request, int(args.shop))






