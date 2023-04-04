import requests
from requests.exceptions import ConnectionError
import json


class YandexMarketEcomru:
    def __init__(self, token: str):

        self.token = token

        self.headers = {
            "Authorization": f'Bearer {self.token}',
            "Content-Type": "application/json; charset=utf-8",
            "Accept": "application/json"
        }

    @staticmethod
    def read_res(res):
        """вспомогательная функция"""
        try:
            return res.json()
        except:
            return res.text

    def sales_boost(self,
                    business_id: int,
                    sku_list: list[int],
                    bids_list: list[int]
                    ):
        """
        Запускает буст продаж — создает и включает кампанию, добавляет в нее товары и назначает на них ставки.
        https://yandex.ru/dev/market/partner-api/doc/ru/reference/bids/putBidsForBusiness
        """

        url = f"https://api.partner.market.yandex.ru/businesses/{business_id}/bids"

        if len(sku_list) != len(bids_list):
            return {"message": "incorrect params"}
        elif len(sku_list) > 1500 or len(bids_list) > 1500:
            return {"message": "incorrect params"}
        else:
            bids = [{"sku": sku, "bid": bid} for sku, bid in zip(sku_list, bids_list)]

        body = {"bids": bids}

        try:
            res = requests.put(url, headers=self.headers, data=json.dumps(body))

            if res.status_code == 200:
                return {"code": res.status_code, "message": "success", "result": self.read_res(res)}

            elif res.status_code == 400:
                return {"code": res.status_code, "message": "Bad Request", "result": self.read_res(res)}

            elif res.status_code == 401:
                return {"code": res.status_code, "message": "Unauthorized", "result": self.read_res(res)}

            elif res.status_code == 403:
                return {"code": res.status_code, "message": "Forbidden", "result": self.read_res(res)}

            elif res.status_code == 404:
                return {"code": res.status_code, "message": "Not Found", "result": self.read_res(res)}

            elif res.status_code == 420:
                return {"code": res.status_code, "message": "Method Failure", "result": self.read_res(res)}

            elif res.status_code == 500:
                return {"code": res.status_code, "message": "Internal Server Error", "result": self.read_res(res)}

        except ConnectionError:
            return {"message": "connection error"}

        except:
            return {"message": "unknown error"}
