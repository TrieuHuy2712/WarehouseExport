from enum import Enum


class SapoShop(Enum):
    QuocCoQuocNghiep = 0
    ThaoDuocGiang = 1


class SapoChannel(Enum):
    All = 0
    Ecommerce = 1
    Pos = 2


class Category(Enum):
    Auto = 0
    API = 1


class Channel(Enum):
    WEB = 0
    SAPO = 1
