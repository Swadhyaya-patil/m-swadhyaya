# angleone_integration.py
import logging
import pandas as pd
from SmartApi import SmartConnect
from pyotp import TOTP
from SmartApi.smartWebSocketV2 import SmartWebSocketV2

logger = logging.getLogger(__name__)

class AngleOneClient:
    def __init__(self, api_key, client_id, mpin, totp_token):
        self.api_key = api_key
        self.client_id = client_id
        self.mpin = mpin
        self.totp_token = totp_token
        self.session_token = None
        instrument_url = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
        self.angle_script_master = pd.read_json(instrument_url)
    
    def login(self):
        logger.info(f"Logging in user {self.client_id}")
        self.session_token = "dummy_session_token"
        self.angel_obj = SmartConnect(self.api_key)
        # self.api_key = angel_secret[0]
        # print("self.angel_obj {}".format(self.angel_obj))
        data = self.angel_obj.generateSession(self.client_id,self.mpin,TOTP(self.totp_token).now())
        # print("data {}".format(data))
        angel_WS_tocken = self.angel_obj.getfeedToken()
        self.angel_WS_tocken = data["data"]["jwtToken"]
        # print("angel_WS_tocken {}".format(angel_WS_tocken))
        self.angel_WS_Obj  = SmartWebSocketV2(data["data"]["jwtToken"], self.api_key, self.client_id, angel_WS_tocken)
        # print("self.angel_WS_Obj  {}".format(self.angel_WS_Obj ))
        # instrument_url = "https://margincalculator.angelbroking.com/OpenAPI_File/files/OpenAPIScripMaster.json"
        # self.angle_script_master = pd.read_json(instrument_url)
        return True

    def place_order(self, script_name, qty, price, order_type="BUY"):
        logger.info(f"Placing {order_type} order: {script_name}, qty={qty}, price={price}")
        exchange="NSE"
        params = {
                    "variety":"NORMAL",
                    "tradingsymbol":"{}-EQ".format(script_name),
                    "symboltoken":self.token_lookup(script_name),
                    "transactiontype":order_type,
                    "exchange":exchange,
                    "ordertype":"LIMIT",
                    "producttype":"DELIVERY",
                    "duration":"DAY",
                    "price":price,
                    "quantity":qty
                    }
        response = self.angel_obj.placeOrder(params)
        # print (response)
        # return response
        return response
    

    def place_TSL_order(self, script_name, qty, price, order_type="SELL"):
        logger.info(f"Placing {order_type} order: {script_name}, qty={qty}, price={price}")
        print(f"Placing {order_type} order: {script_name}, qty={qty}, price={price}")
        exchange="NSE"
        params = {
                    # "variety":"STOPLOSS",
                    # "tradingsymbol":"{}-EQ".format(script_name),
                    # "symboltoken":self.token_lookup(script_name),
                    # "transactiontype":order_type,
                    # "exchange":exchange,
                    # "ordertype":order_type,
                    # "producttype":"DELIVERY",
                    # "duration":"DAY",
                    # "price":price,
                    # "triggerprice": price*1.0025,  # The stop loss trigger price
                    # "quantity":qty
                    "variety":"STOPLOSS",
                    "tradingsymbol":"{}-EQ".format(script_name),
                    "symboltoken": self.token_lookup(script_name),
                    "transactiontype":order_type,
                    "exchange":exchange,
                    # "ordertype":order_type,
                    "ordertype":"STOPLOSS_LIMIT",
                    "producttype":"DELIVERY",
                    "duration":"DAY",
                    "price":price,
                    "triggerprice": round(price*1.0025,2),  # The stop loss trigger price
                    "quantity":qty
                    }
        response = self.angel_obj.placeOrder(params)
        print (response)
        # return response
        return response
    
    
    def token_lookup(self, ticker):
        eq_ticker = ticker+"-EQ"
        result = self.angle_script_master.loc[(self.angle_script_master["name"] == ticker) & \
                    (self.angle_script_master["exch_seg"] == "NSE") &\
                    (self.angle_script_master["symbol"] == eq_ticker) , "token"].iloc[0]
        return result
 
    def get_positions(self):
        return self.angel_obj.position()
    
    def get_holding(self):
        return self.angel_obj.holding()

    def get_order_book(self):
        """Fetch order book from broker"""
        try:
            response = self.angel_obj.orderBook()
            if response.get('status'):
                return response.get('data', [])
            else:
                logger.error(f"Failed to get order book: {response}")
                return []
        except Exception as e:
            logger.error(f"Exception in get_order_book: {e}")
            return []

    def cancel_order(self, order_id, variety ="STOPLOSS" ):
        """
        Cancel order by broker order id and variety.
        """
        try:
            params = {
                'variety': variety,   # must provide
                'orderid': order_id
            }
            print(f"Cancel order {order_id} (variety={variety})  (params = {params})")
            response = self.angel_obj.cancelOrder(order_id,variety)
            if response.get('status'):
                logger.info(f"✅ Cancelled order {order_id} (variety={variety})")
                return True
            else:
                logger.error(f"Failed to cancel order {order_id}: {response}")
                return False
        except Exception as e:
            logger.error(f"Exception in cancel_order({order_id}): {e}")
            return False

    def ltpData(self, script_name):
        exchange="NSE"
        tradingsymbol= "{}-EQ".format(script_name)
        symboltoken = self.token_lookup(script_name)
        response = self.angel_obj.ltpData(exchange,tradingsymbol,symboltoken)
        return response

def validate_user_credentials(api_key, client_id, mpin, totp_token):
    try:
        if api_key.startswith('C') and client_id and mpin and totp_token:
            return True, "Login successful"
        else:
            return False, "Invalid credentials"
    except Exception as e:
        return False, f"Error validating credentials: {str(e)}"
