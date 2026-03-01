API_KEY ="7b6dbc18-c4dc-49e4-bd68-0c1a3b8156d6"
API_SECRET = "u17wvai7p6"
OLD_ACCESS_TOKEN = "eyJ0eXAiOiJKV1QiLCJrZXlfaWQiOiJza192MS4wIiwiYWxnIjoiSFMyNTYifQ.eyJzdWIiOiI0QUE3RkwiLCJqdGkiOiI2OGEyMTU1YTdjNzk0ODMxYzA2Nzg3OWUiLCJpc011bHRpQ2xpZW50IjpmYWxzZSwiaXNQbHVzUGxhbiI6ZmFsc2UsImlhdCI6MTc1NTQ1Mjc2MiwiaXNzIjoidWRhcGktZ2F0ZXdheS1zZXJ2aWNlIiwiZXhwIjoxNzU1NDY4MDAwfQ.c9EZM4F4w7OlvV6GbRu0KdihWo45709BovNylrYW2yw"
CLIENT_ID ="4AA7FL"

ACCESS_TOKEN = "eyJ0eXAiOiJKV1QiLCJrZXlfaWQiOiJza192MS4wIiwiYWxnIjoiSFMyNTYifQ.eyJzdWIiOiI0QUE3RkwiLCJqdGkiOiI2OTA4ZTViN2Y2NzIxMDYwYWQ3YjEzN2EiLCJpc011bHRpQ2xpZW50IjpmYWxzZSwiaXNQbHVzUGxhbiI6ZmFsc2UsImlhdCI6MTc2MjE5MDc3NSwiaXNzIjoidWRhcGktZ2F0ZXdheS1zZXJ2aWNlIiwiZXhwIjoxNzYyMjA3MjAwfQ.h_dZfVWkWRDqPHzlmn1lr9V8f3dAoup018Czv3utGIc"

import logging
import json
import os
from datetime import datetime
from typing import Optional

import upstox_client
from upstox_client.api import OrderApi, PortfolioApi, MarketQuoteApi
from upstox_client.rest import ApiException


logger = logging.getLogger(__name__)

class UpstoxClient:
    def __init__(self, api_key: str = None, client_id: str = None, mpin: str = None, totp_token: str = None,
                 instrument_master_path: Optional[str] = None):
        self.api_key = api_key
        self.client_id = client_id
        self.mpin = mpin
        self.totp_token = totp_token

        self.upstox_client_instance = None
        self.access_token = None

        self.instrument_master = {}
        if instrument_master_path:
            try:
                if instrument_master_path.lower().endswith(".json"):
                    with open(instrument_master_path, "r") as f:
                        self.instrument_master = json.load(f)
                else:
                    import csv
                    with open(instrument_master_path, newline='') as csvfile:
                        reader = csv.DictReader(csvfile)
                        for row in reader:
                            exchanger = row.get("exchange", "NSE")
                            symbol = row.get("symbol") or row.get("tradingsymbol")
                            token = row.get("instrument_token") or row.get("token")
                            if symbol and token:
                                self.instrument_master.setdefault(exchanger, {})[symbol] = token
                logger.info(f"Loaded instrument master from {instrument_master_path}")
            except Exception as e:
                logger.warning(f"Could not load instrument master: {e}")

    def login(self):
        logger.info(f"UpstoxClient: Logging in user {self.client_id}")
        try:
            # The SDK expects that you obtain a session and get an `access_token`
            # See README & documentation of SDK. Example:
            # 1) Use upstox_client.Configuration to configure token
            # 2) Create ApiClient and OrderApiV3 etc.
            # For simplicity here, assume you already have a valid access_token.
            
            configuration = upstox_client.Configuration()
            configuration.access_token = self.access_token or "<YOUR_ACCESS_TOKEN>"  # fill in
            api_client = upstox_client.ApiClient(configuration)
            self.order_api = OrderApiV3(api_client)
            self.quote_api = MarketQuoteApi(api_client)
            self.portfolio_api = PortfolioApi(api_client)
            self.upstox_client_instance = api_client
            logger.info("UpstoxClient: Login successful")
            return True
        except Exception as e:
            logger.error(f"UpstoxClient: login error: {e}")
            return False

    def token_lookup(self, ticker: str, exchange: str = "NSE"):
        exch = exchange.upper()
        try:
            if exch in self.instrument_master and ticker in self.instrument_master[exch]:
                return self.instrument_master[exch][ticker]
            eq_key = f"{ticker}"
            if exch in self.instrument_master and eq_key in self.instrument_master[exch]:
                return self.instrument_master[exch][eq_key]
            raise KeyError(f"Token not found for {ticker} on {exch}")
        except Exception as e:
            logger.error(f"Token lookup failed for {ticker}: {e}")
            raise

    def place_order(self, script_name, qty, price, order_type="BUY"):
        logger.info(f"UpstoxClient: place_order {order_type} {script_name} qty={qty} price={price}")
        try:
            token = self.token_lookup(script_name)
            body = upstox_client.PlaceOrderV3Request(
                quantity=qty,
                product="D",
                validity="DAY",
                price=price,
                instrument_token=token,
                order_type="LIMIT",
                transaction_type=order_type,
                disclosed_quantity=0,
                trigger_price=0.0,
                is_amo=False,
                slice=False
            )
            resp = self.order_api.place_order(body)
            return {"status": True, "data": resp.to_dict(), "message": "Order placed"}
        except ApiException as e:
            logger.error(f"UpstoxClient place_order ApiException: {e}")
            return {"status": False, "message": str(e)}

    def place_TSL_order(self, script_name, qty, price, order_type="SELL"):
        logger.info(f"UpstoxClient: place_TSL_order {script_name} qty={qty} price={price}")
        try:
            token = self.token_lookup(script_name)
            # Using stoploss-limit style: set trigger_price = price
            body = upstox_client.PlaceOrderV3Request(
                quantity=qty,
                product="D",
                validity="DAY",
                price=price,
                instrument_token=token,
                order_type="SL",  # stop loss order type per Upstox docs
                transaction_type=order_type,
                disclosed_quantity=0,
                trigger_price=price,
                is_amo=False,
                slice=False
            )
            resp = self.order_api.place_order(body)
            return {"status": True, "data": resp.to_dict(), "message": "TSL placed"}
        except ApiException as e:
            logger.error(f"UpstoxClient place_TSL_order ApiException: {e}")
            return {"status": False, "message": str(e)}

    def get_holding(self):
        logger.info("UpstoxClient: get_holding")
        try:
            resp = self.portfolio_api.get_holdings()
            return {"status": True, "data": resp.to_dict()}
        except ApiException as e:
            logger.error(f"get_holding ApiException: {e}")
            return {"status": False, "message": str(e)}

    def get_order_book(self):
        logger.info("UpstoxClient: get_order_book")
        try:
            resp = self.order_api.get_order_book()
            orders = resp.to_dict().get("data", [])
            return orders
        except ApiException as e:
            logger.error(f"get_order_book ApiException: {e}")
            return []

    def cancel_order(self, order_id, variety="STOPLOSS"):
        logger.info(f"UpstoxClient: cancel_order {order_id}")
        try:
            resp = self.order_api.cancel_order(order_id)
            return True
        except ApiException as e:
            logger.error(f"cancel_order ApiException: {e}")
            return False

    def ltpData(self, script_name):
        logger.info(f"UpstoxClient: ltpData {script_name}")
        try:
            token = self.token_lookup(script_name)
            resp = self.quote_api.get_ltp([token])
            # resp.data might be list of objects
            ltp = None
            for item in resp.to_dict().get("data", []):
                if item.get("instrument_token") == token:
                    ltp = item.get("last_traded_price")
                    break
            return {"data": {"ltp": ltp}}
        except ApiException as e:
            logger.error(f"ltpData ApiException: {e}")
            return {"data": {"ltp": None}, "status": False, "message": str(e)}

    def place_market_sell(self, script_name, qty):
        logger.info(f"UpstoxClient: place_market_sell {script_name} qty={qty}")
        try:
            token = self.token_lookup(script_name)
            body = upstox_client.PlaceOrderV3Request(
                quantity=qty,
                product="D",
                validity="DAY",
                price=0.0,
                instrument_token=token,
                order_type="MARKET",
                transaction_type="SELL",
                disclosed_quantity=0,
                trigger_price=0.0,
                is_amo=False,
                slice=False
            )
            resp = self.order_api.place_order(body)
            return {"status": True, "data": resp.to_dict(), "message": "Market sell placed"}
        except ApiException as e:
            logger.error(f"place_market_sell ApiException: {e}")
            return {"status": False, "message": str(e)}



# import upstox_client
# from upstox_client.rest import ApiException

# print("Testing 01")
# configuration = upstox_client.Configuration()
# print(f"configuration {configuration}")
# configuration.access_token = API_SECRET

# api_instance = upstox_client.OrderApiV3(upstox_client.ApiClient(configuration))
# print(f"api_instance {api_instance}")
# body = upstox_client.PlaceOrderV3Request(quantity=1, product="D", validity="DAY", price=0, 
#                                         instrument_token="NSE_EQ|INE528G01035", order_type="MARKET", 
#                                         transaction_type="BUY", disclosed_quantity=0, trigger_price=0, 
#                                         is_amo=False, slice=True)

# print(f"body {body}")
# try:
#     api_response = api_instance.place_order(body)
#     print(api_response)
# except ApiException as e:
#     print("Exception when calling OrderApiV3->place_order: %s\n" % e)


import requests

url = 'https://api.upstox.com/v2/login/authorization/token'
headers = {
    'accept': 'application/json',
    'Content-Type': 'application/x-www-form-urlencoded',
}

data = {
    'code': f'{ACCESS_TOKEN}',
    'client_id': f'{API_KEY}',
    'client_secret': f'{API_SECRET}',
    'redirect_uri': r'http://127.0.0.1',
    'grant_type': 'authorization_code',
}
print(data)
response = requests.post(url, headers=headers, data=data)

print(response.status_code)
print(response.json())
