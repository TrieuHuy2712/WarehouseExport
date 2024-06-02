# This is a sample Python script.
import argparse
from datetime import datetime, timedelta

from src.Enums import SapoShop
from src.Factory.WarehouseOrderFactory import OrderAutoFactory
from src.OrderRequest import OrderRequest


def get_command_line_arguments():
    parser = argparse.ArgumentParser(description="Warehouse Export CLI")

    parser.add_argument('-a', '--auto', help='Run in auto mode')
    parser.add_argument('-s', '--shop', help='Run in auto mode', default=str(0))
    parser.add_argument('-d', '--days', help='Input from date and end date')

    args = parser.parse_args()

    return args


# Press the green button in the gutter to run the script.
if __name__ == '__main__':
    print('Warehouse Export')
    args = get_command_line_arguments()
    order_factory = OrderAutoFactory()
    order_request = OrderRequest()
    if args.auto:
        # Input from date
        order_request.from_date = (datetime.now().replace(hour=17, minute=00, second=00, microsecond=0) + timedelta(
            days=-1)).strftime('%Y-%m-%dT%H:%M:%SZ')
        # Input to date
        order_request.to_date = datetime.now().replace(hour=16, minute=59, second=59, microsecond=0).strftime('%Y-%m-%dT%H:%M:%SZ')

        # Submit order
        orders = order_factory.create_sapo_order(order_request, SapoShop(int(args.shop))).get_orders_by_date()
        order_factory.submit_order(orders)
    elif args.days:
        order_request.from_date = datetime.fromisoformat(
            input('Start Date Time YYYY-mm-dd HH:MM:SS: (Ex: 2024-03-23 12:00:00)')).strftime('%Y-%m-%dT%H:%M:%SZ')
        order_request.to_date = datetime.fromisoformat(
            input('End Date Time YYYY-mm-dd HH:MM:SS: (Ex: 2024-03-30 12:00:00)')).strftime('%Y-%m-%dT%H:%M:%SZ')
        # Submit order
        orders = order_factory.create_sapo_order(order_request, args.shop).get_orders_by_date()
        order_factory.submit_order(orders)



