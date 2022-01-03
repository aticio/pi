# Pi
import os
import configparser
import logging
import websocket
import json
import logging.handlers
from renko import Renko
import algoutils
from urllib.parse import urlencode
import hmac
import hashlib
import requests

cwd = os.path.dirname(os.path.realpath(__file__))
os.chdir(cwd)

# Configparser init
cp = configparser.ConfigParser()
cp.read(cwd + "/config.ini")

# Context info
BINANCE_URL = cp["context"]["BinanceUrl"]
BINANCE_WEBSOCKET_ADDRESS = cp["context"]["BinanceWebSocketAddress"]
KLINE_PATH = cp["context"]["KlinePath"]
SPOT_ACCOUNT_PATH = cp["context"]["SpotAccountPath"]
SPOT_ORDER_PATH = cp["context"]["SpotOrderPath"]
ISOLATED_MARGIN_ACCOUNT_PATH = cp["context"]["IsolatedMarginAccountPath"]
ISOLATED_MARGIN_TRANSFER_PATH = cp["context"]["IsolatedMarginTransferPath"]
ISOLATED_MARGIN_CREATE_PATH = cp["context"]["IsolatedMarginCreatePath"]
MARGIN_BORROW_PATH = cp["context"]["MarginBorrowPath"]
MARGIN_ORDER_PATH = cp["context"]["MarginOrderPath"]
MARGIN_REPAY_PATH = cp["context"]["MarginRepayPath"]
MARGIN_MAX_BORROWABLE_PATH = cp["context"]["MarginMaxBorrowablePath"]

# Auth
API_KEY = os.getenv("BINANCE_API_KEY")
SECRET = os.getenv("BINANCE_API_SECRET")

# Market related variables
INTERVAL = cp["data"]["Interval"]
SYMBOL = cp["data"]["Symbol"]
BASE = cp["data"]["Base"]
QUOTE = cp["data"]["Quote"]
STEP_SIZE = int(cp["data"]["StepSize"])
COMMISSION_FEE = float(cp["data"]["CommissionFee"])
BRICK_SIZE = float(cp["data"]["BrickSize"])
INITIAL_BRICK_OPEN = float(cp["data"]["InitialBrickOpen"])
INITIAL_BRICK_CLOSE = float(cp["data"]["InitialBrickClose"])


# Risk related variables
POSITION_RISK = float(cp["risk"]["PositionRisk"])

# Other functional globals
IN_ORDER = False
POS = 0
POSITION_PRICE = 0.0

# Creating empty renko object with giving empty list of price data
RENKO = Renko(BRICK_SIZE, [])


def main():
    global BINANCE_WEBSOCKET_ADDRESS

    BINANCE_WEBSOCKET_ADDRESS = BINANCE_WEBSOCKET_ADDRESS.replace("symbol", str.lower(SYMBOL))

    configure_logs()

    RENKO.add_single_custom_brick("down", INITIAL_BRICK_OPEN, INITIAL_BRICK_CLOSE)
    print(RENKO.bricks)
    logging.info(API_KEY)
    logging.info(SECRET)

    init_stream()


# Websocket functions
def init_stream():
    websocket.enableTrace(True)
    w_s = websocket.WebSocketApp(
        BINANCE_WEBSOCKET_ADDRESS,
        on_message=on_message,
        on_error=on_error,
        on_close=on_close
        )
    w_s.on_open = on_open
    w_s.run_forever()


def on_error(w_s, error):
    logging.error(error)


def on_close(w_s):
    logging.info("closing websocket connection, initiating again...")
    init_stream()


def on_open(w_s):
    logging.info("websocket connection opened")


def on_message(w_s, message):
    global POS

    ticker_data = json.loads(message)
    ticker_price = float(ticker_data["c"])

    RENKO.check_new_price(ticker_price)

    if POS == 1 and IN_ORDER is False:
        if RENKO.bricks[-1]["type"] == "down":
            exit_long()
            enter_short(RENKO.bricks[-1])

    if POS == -1 and IN_ORDER is False:
        if RENKO.bricks[-1]["type"] == "up":
            exit_short()
            enter_long(RENKO.bricks[-1])


# Preperation functions
def configure_logs():
    handler = logging.handlers.RotatingFileHandler(
        cwd + "/logs/" + SYMBOL + "_pos_tracker.log",
        maxBytes=10000000, backupCount=5)

    formatter = logging.Formatter(
        "%(asctime)s %(message)s", "%Y-%m-%d_%H:%M:%S")
    handler.setFormatter(formatter)

    logger = logging.getLogger()
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)


# Position related functions
def enter_long(brick):
    global POS
    global POSITION_PRICE
    global IN_ORDER

    IN_ORDER = True

    logging.info("Opening long position.")

    balance = get_margin_balance(QUOTE, SYMBOL, "quoteAsset")
    logging.info(f"Quote balance: {balance} {QUOTE}")

    if not balance:
        return

    share = (balance * POSITION_RISK) / (BRICK_SIZE * 2)
    share = algoutils.truncate_ceil(share, STEP_SIZE)
    logging.info(f"Calculated share: {share} {BASE}")

    max_borrowable_response = get_max_borrowable(QUOTE, SYMBOL)
    if not max_borrowable_response:
        return

    if (share * brick["close"]) - float(balance) > float(max_borrowable_response["amount"]):
        logging.info("Exceeding maximum borrowable limit.")
        logging.info(max_borrowable_response)
        max_borrowable = max_borrowable_response["amount"]
        amount_to_borrow = float(max_borrowable)
    elif (share * brick["close"]) - float(balance) < 0:
        amount_to_borrow = (share * brick["close"])
    else:
        amount_to_borrow = (share * brick["close"]) - float(balance)

    amount_to_borrow = algoutils.truncate_ceil(amount_to_borrow, 8)
    logging.info(f"Amount to borrow for quote: {amount_to_borrow} {QUOTE}")

    total_balance = algoutils.truncate_floor(amount_to_borrow + balance, 8)
    logging.info(f"Total quote balance for position: {total_balance} {QUOTE}")

    logging.info(f"Borrowing {QUOTE}")
    margin_borrow_response = margin_borrow(
        QUOTE,
        "TRUE",
        SYMBOL,
        amount_to_borrow)

    if not margin_borrow_response:
        return

    logging.info("Triggering buy order")
    margin_order_response = margin_order_quote(
        SYMBOL,
        "TRUE",
        "BUY",
        "MARKET",
        total_balance)

    logging.info(json.dumps(margin_order_response, sort_keys=True, indent=4))

    if not margin_order_response:
        return

    pos_share = float(margin_order_response["executedQty"]) - (float(margin_order_response["executedQty"]) * 0.001)
    logging.info(f"Base balance after margin buy (bought - commission): {pos_share} {BASE}")

    POS = 1
    POSITION_PRICE = brick["close"]

    IN_ORDER = False


def enter_short(brick):
    global POS
    global POSITION_PRICE
    global IN_ORDER

    IN_ORDER = True

    logging.info("Opening short position.")

    balance = get_margin_balance(QUOTE, SYMBOL, "quoteAsset")
    logging.info(f"Quote balance: {balance} {QUOTE}")

    if not balance:
        return

    share = (balance * POSITION_RISK) / (BRICK_SIZE * 2)
    share = algoutils.truncate_ceil(share, STEP_SIZE)
    logging.info(f"Calculated share: {share} {BASE}")

    amount_to_transfer = algoutils.truncate_floor(balance, 8)
    logging.info("amount to transfer %f", amount_to_transfer)

    logging.info("Transfering from SPOT to ISOLATED_MARGIN")
    transfer_response = isolated_margin_transfer(
        QUOTE,
        SYMBOL,
        amount_to_transfer,
        "SPOT",
        "ISOLATED_MARGIN")

    if not transfer_response:
        return

    max_borrowable_response = get_max_borrowable(BASE, SYMBOL)
    if not max_borrowable_response:
        return

    if share > float(max_borrowable_response["amount"]):
        logging.info("Exceeding maximum borrowable limit.")
        amount_to_borrow = float(max_borrowable_response["amount"])
    else:
        amount_to_borrow = share

    amount_to_borrow = algoutils.truncate_floor(amount_to_borrow, STEP_SIZE)
    logging.info(f"Amount to borrow: {amount_to_borrow} {BASE}")

    logging.info(f"Borrowing {BASE}")
    margin_borrow_response = margin_borrow(BASE, "TRUE", SYMBOL, amount_to_borrow)

    if not margin_borrow_response:
        return

    logging.info("Triggering order")
    margin_order_response = margin_order(
        SYMBOL,
        "TRUE",
        "SELL",
        "MARKET",
        amount_to_borrow)

    if not margin_order_response:
        return

    logging.info(json.dumps(margin_order_response, sort_keys=True, indent=4))

    POS = -1
    POSITION_PRICE = brick["close"]

    IN_ORDER = False


def exit_long():
    global POS
    global IN_ORDER
    global POS_SHARE

    IN_ORDER = True

    logging.info("Closing long position.")

    balance = get_margin_balance(BASE, SYMBOL, "baseAsset")
    logging.info(f"Base balance: {balance} {BASE}")

    amount_to_sell = algoutils.truncate_floor(balance, STEP_SIZE)

    if STEP_SIZE == 0:
        amount_to_sell = int(amount_to_sell)

    logging.info(f"Amount to sell: {amount_to_sell} {BASE}")
    logging.info("Triggering sell order.")

    margin_order_response = margin_order(
        SYMBOL,
        "TRUE",
        "SELL",
        "MARKET",
        amount_to_sell)

    if not margin_order_response:
        IN_ORDER = False
        return

    logging.info(json.dumps(margin_order_response, sort_keys=True, indent=4))

    margin_quote_debt = get_margin_debt(QUOTE, SYMBOL, "quoteAsset")
    if not margin_quote_debt:
        IN_ORDER = False
        return

    logging.info(f"Margin quote debt: {margin_quote_debt} {QUOTE}")
    logging.info("Repaying debt")

    margin_repay_amount = margin_quote_debt

    margin_repay_response = margin_repay(
        QUOTE,
        "TRUE",
        SYMBOL,
        margin_repay_amount)

    if not margin_repay_response:
        IN_ORDER = False
        return

    logging.info("Debt has been repaid")

    POS = 0
    IN_ORDER = False


def exit_short():
    global POS
    global IN_ORDER

    IN_ORDER = True

    logging.info("Closing short position.")
    logging.info("Getting total debt")
    margin_debt = get_margin_debt(BASE, SYMBOL, "baseAsset")

    if not margin_debt:
        IN_ORDER = False
        return

    logging.info(f"Margin debt (borrowed + interest): {margin_debt} {BASE}")
    amount_to_buy_repay = algoutils.truncate_ceil(margin_debt / (1 - COMMISSION_FEE), STEP_SIZE)
    logging.info(f"Amount to buy and repay (minimum amount that can pay the debt and commission): {amount_to_buy_repay} {BASE}")

    logging.info("Triggering buy order for closing position")
    margin_order_response = margin_order(
        SYMBOL, "TRUE", "BUY", "MARKET", amount_to_buy_repay)

    if not margin_order_response:
        IN_ORDER = False
        return

    logging.info(json.dumps(margin_order_response, sort_keys=True, indent=4))
    logging.info("Order has been filled")

    margin_base_free_balance = get_margin_free_balance(
        BASE, SYMBOL, "baseAsset")

    if not margin_base_free_balance:
        IN_ORDER = False
        return

    logging.info("Repaying debt")
    margin_repay_response = margin_repay(
        BASE, "TRUE", SYMBOL, margin_base_free_balance)

    if not margin_repay_response:
        IN_ORDER = False
        return

    logging.info("Debt has been repaid")
    logging.info("Getting margin account quote balance")

    margin_quote_balance = get_margin_balance(QUOTE, SYMBOL, "quoteAsset")

    if not margin_quote_balance:
        return

    amount_to_transfer_back = algoutils.truncate_floor(margin_quote_balance, 8)
    logging.info(amount_to_transfer_back)

    logging.info("Transfering from margin account to spot account")
    transfer_back_response = isolated_margin_transfer(
        QUOTE, SYMBOL, amount_to_transfer_back, "ISOLATED_MARGIN", "SPOT")

    if not transfer_back_response:
        return

    logging.info("Transfer has been completed")

    POS = 0
    IN_ORDER = False


# Spot account trade functions
def get_spot_balance(asset):
    timestamp = algoutils.get_current_timestamp()

    params = {"timestamp": timestamp, "recvWindow": 5000}
    query_string = urlencode(params)
    params["signature"] = hmac.new(SECRET.encode(
        "utf-8"), query_string.encode("utf-8"), hashlib.sha256).hexdigest()

    headers = {"X-MBX-APIKEY": API_KEY}

    try:
        response = requests.get(
            url=f"{BINANCE_URL}{SPOT_ACCOUNT_PATH}",
            params=params, headers=headers)
        response.raise_for_status()
        data = response.json()

        for _, balance in enumerate(data["balances"]):
            if balance["asset"] == asset:
                return float(balance["free"])
    except requests.exceptions.RequestException as err:
        logging.error(err)
        return None


def spot_order(order_symbol, side, type, quantity):
    timestamp = algoutils.get_current_timestamp()

    params = {
        "symbol": order_symbol, "side": side, "type": type,
        "quantity": quantity, "timestamp": timestamp, "recvWindow": 5000
    }
    query_string = urlencode(params)
    params["signature"] = hmac.new(SECRET.encode(
        "utf-8"), query_string.encode("utf-8"), hashlib.sha256).hexdigest()

    headers = {"X-MBX-APIKEY": API_KEY}

    try:
        response = requests.post(
            url=f"{BINANCE_URL}{SPOT_ORDER_PATH}",
            params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
        return data
    except requests.exceptions.RequestException as err:
        logging.error(err)
        logging.error(response.json())
        return None


def spot_order_quote(order_symbol, side, type, quote_quantity):
    timestamp = algoutils.get_current_timestamp()

    params = {
        "symbol": order_symbol, "side": side,
        "type": type, "quoteOrderQty": quote_quantity,
        "timestamp": timestamp, "recvWindow": 5000
    }
    query_string = urlencode(params)
    params["signature"] = hmac.new(SECRET.encode(
        "utf-8"), query_string.encode("utf-8"), hashlib.sha256).hexdigest()

    headers = {"X-MBX-APIKEY": API_KEY}

    try:
        response = requests.post(
            url=f"{BINANCE_URL}{SPOT_ORDER_PATH}",
            params=params,
            headers=headers)
        response.raise_for_status()
        data = response.json()
        return data
    except requests.exceptions.RequestException as err:
        logging.error(err)
        logging.error(response.json())
        return None


# Margin account trade functions
def margin_create(base, quote):
    t = algoutils.get_current_timestamp()
    params = {"base": base, "quote": quote, "timestamp": t}
    query_string = urlencode(params)
    params['signature'] = hmac.new(
        SECRET.encode('utf-8'),
        query_string.encode('utf-8'), hashlib.sha256).hexdigest()

    headers = {'X-MBX-APIKEY': API_KEY}
    r = requests.post(
        url=BINANCE_URL + ISOLATED_MARGIN_CREATE_PATH,
        params=params,
        headers=headers)
    data = r.json()
    print(data)


def isolated_margin_transfer(
        asset, order_symbol, amount, transfer_from, transfer_to):
    timestamp = algoutils.get_current_timestamp()
    params = {
        "asset": asset, "symbol": order_symbol,
        "amount": amount, "transTo": transfer_to,
        "transFrom": transfer_from,
        "recvWindow": 5000, "timestamp": timestamp
    }
    query_string = urlencode(params)
    params["signature"] = hmac.new(SECRET.encode(
        "utf-8"), query_string.encode("utf-8"), hashlib.sha256).hexdigest()

    headers = {"X-MBX-APIKEY": API_KEY}

    try:
        response = requests.post(
            url=f"{BINANCE_URL}{ISOLATED_MARGIN_TRANSFER_PATH}",
            params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
        return data
    except requests.exceptions.RequestException as err:
        logging.error(err)
        logging.error(response.json())
        return None


def margin_borrow(asset, is_isolated, order_symbol, amount):
    timestamp = algoutils.get_current_timestamp()

    params = {
        "asset": asset,
        "isIsolated": is_isolated,
        "symbol": order_symbol,
        "amount": amount,
        "recvWindow": 5000,
        "timestamp": timestamp
    }
    query_string = urlencode(params)
    params["signature"] = hmac.new(SECRET.encode(
        "utf-8"), query_string.encode("utf-8"), hashlib.sha256).hexdigest()

    headers = {"X-MBX-APIKEY": API_KEY}

    try:
        response = requests.post(
            url=f"{BINANCE_URL}{MARGIN_BORROW_PATH}",
            params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
        return data
    except requests.exceptions.RequestException as err:
        logging.error(err)
        logging.error(response.json())
        return None


def get_max_borrowable(asset, order_symbol):
    timestamp = algoutils.get_current_timestamp()

    params = {
        "asset": asset,
        "isolatedSymbol": order_symbol,
        "recvWindow": 5000,
        "timestamp": timestamp
    }
    query_string = urlencode(params)
    params["signature"] = hmac.new(SECRET.encode(
        "utf-8"), query_string.encode("utf-8"), hashlib.sha256).hexdigest()

    headers = {"X-MBX-APIKEY": API_KEY}

    try:
        response = requests.get(
            url=f"{BINANCE_URL}{MARGIN_MAX_BORROWABLE_PATH}",
            params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
        return data
    except requests.exceptions.RequestException as err:
        logging.error(err)
        logging.error(response.json())
        return None


def margin_order(order_symbol, is_isolated, side, type, quantity):
    timestamp = algoutils.get_current_timestamp()

    params = {
        "symbol": order_symbol,
        "isIsolated": is_isolated,
        "side": side,
        "type": type,
        "quantity": quantity,
        "timestamp": timestamp,
        "recvWindow": 5000
    }
    query_string = urlencode(params)
    params["signature"] = hmac.new(SECRET.encode(
        "utf-8"), query_string.encode("utf-8"), hashlib.sha256).hexdigest()

    headers = {"X-MBX-APIKEY": API_KEY}

    try:
        response = requests.post(
            url=f"{BINANCE_URL}{MARGIN_ORDER_PATH}",
            params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
        return data
    except requests.exceptions.RequestException as err:
        logging.error(err)
        logging.error(response.json())
        return None


def margin_order_quote(order_symbol, is_isolated, side, type, quote_quantity):
    timestamp = algoutils.get_current_timestamp()

    params = {
        "symbol": order_symbol,
        "isIsolated": is_isolated,
        "side": side,
        "type": type,
        "quoteOrderQty": quote_quantity,
        "timestamp": timestamp,
        "recvWindow": 5000
    }
    query_string = urlencode(params)
    params["signature"] = hmac.new(SECRET.encode(
        "utf-8"), query_string.encode("utf-8"), hashlib.sha256).hexdigest()

    headers = {"X-MBX-APIKEY": API_KEY}

    try:
        response = requests.post(
            url=f"{BINANCE_URL}{MARGIN_ORDER_PATH}",
            params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
        return data
    except requests.exceptions.RequestException as err:
        logging.error(err)
        logging.error(response.json())
        return None


def margin_repay(asset, is_isolated, order_symbol, amount):
    timestamp = algoutils.get_current_timestamp()

    params = {
        "asset": asset, "amount": amount, "isIsolated": is_isolated,
        "symbol": order_symbol, "recvWindow": 5000, "timestamp": timestamp
    }
    query_string = urlencode(params)
    params["signature"] = hmac.new(SECRET.encode(
        "utf-8"), query_string.encode("utf-8"), hashlib.sha256).hexdigest()

    headers = {"X-MBX-APIKEY": API_KEY}

    try:
        response = requests.post(
            url=f"{BINANCE_URL}{MARGIN_REPAY_PATH}",
            params=params, headers=headers)
        response.raise_for_status()
        data = response.json()
        return data
    except requests.exceptions.RequestException as err:
        logging.error(err)
        logging.error(response.json())
        return None


def get_margin_debt(asset, order_symbol, type):
    timestamp = algoutils.get_current_timestamp()

    params = {
        "symbols": order_symbol, "timestamp": timestamp, "recvWindow": 5000}
    query_string = urlencode(params)
    params["signature"] = hmac.new(SECRET.encode(
        "utf-8"), query_string.encode("utf-8"), hashlib.sha256).hexdigest()

    headers = {"X-MBX-APIKEY": API_KEY}

    try:
        response = requests.get(
            url=f"{BINANCE_URL}{ISOLATED_MARGIN_ACCOUNT_PATH}",
            params=params, headers=headers)
        response.raise_for_status()
        data = response.json()

        for _, balance in enumerate(data["assets"]):
            if balance[type]["asset"] == asset:
                logging.info(json.dumps(balance, sort_keys=True, indent=4))
                return (
                    float(
                        balance[type]["borrowed"]
                        ) + float(
                            balance[type]["interest"]))
    except requests.exceptions.RequestException as err:
        logging.error(err)
        return None


def get_margin_free_balance(asset, order_symbol, type):
    timestamp = algoutils.get_current_timestamp()

    params = {
        "symbols": order_symbol,
        "timestamp": timestamp, "recvWindow": 5000}
    query_string = urlencode(params)
    params["signature"] = hmac.new(SECRET.encode(
        "utf-8"), query_string.encode("utf-8"), hashlib.sha256).hexdigest()

    headers = {"X-MBX-APIKEY": API_KEY}

    try:
        response = requests.get(
            url=f"{BINANCE_URL}{ISOLATED_MARGIN_ACCOUNT_PATH}",
            params=params, headers=headers)
        response.raise_for_status()
        data = response.json()

        for _, balance in enumerate(data["assets"]):
            if balance[type]["asset"] == asset:
                logging.info(json.dumps(balance, sort_keys=True, indent=4))
                return float(balance[type]["free"])
    except requests.exceptions.RequestException as err:
        logging.error(err)
        return None


def get_margin_balance(asset, order_symbol, type):
    timestamp = algoutils.get_current_timestamp()

    params = {
        "symbols": order_symbol,
        "timestamp": timestamp, "recvWindow": 5000}
    query_string = urlencode(params)
    params["signature"] = hmac.new(SECRET.encode(
        "utf-8"), query_string.encode("utf-8"), hashlib.sha256).hexdigest()

    headers = {"X-MBX-APIKEY": API_KEY}

    try:
        response = requests.get(
            url=f"{BINANCE_URL}{ISOLATED_MARGIN_ACCOUNT_PATH}",
            params=params, headers=headers)
        response.raise_for_status()
        data = response.json()

        for _, balance in enumerate(data["assets"]):
            if balance[type]["asset"] == asset:
                logging.info(json.dumps(balance, sort_keys=True, indent=4))
                return float(balance[type]["netAsset"])
    except requests.exceptions.RequestException as err:
        logging.error(err)
        return None


if __name__ == "__main__":
    main()
