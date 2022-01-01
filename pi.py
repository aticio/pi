# Pi
import os
import configparser
import logging
import websocket
import json
import logging.handlers

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

# Market related variables
INTERVAL = cp["data"]["Interval"]
SYMBOL = cp["data"]["Symbol"]
BASE = cp["data"]["Base"]
QUOTE = cp["data"]["Quote"]
STEP_SIZE = int(cp["data"]["StepSize"])
COMMISSION_FEE = float(cp["data"]["CommissionFee"])
BRICK_SIZE = float(cp["data"]["BrickSize"])

# Risk related variables
POSITION_RISK = float(cp["risk"]["PositionRisk"])

# Other functional globals
IN_ORDER = False
POS = 0
POSITION_PRICE = 0.0


def main():
    global BINANCE_WEBSOCKET_ADDRESS

    BINANCE_WEBSOCKET_ADDRESS = BINANCE_WEBSOCKET_ADDRESS.replace("symbol", str.lower(SYMBOL))

    configure_logs()

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
    ticker_data = json.loads(message)
    ticker_price = float(ticker_data["c"])
    print(ticker_price)


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


if __name__ == "__main__":
    main()
