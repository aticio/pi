# Pi
import os
import configparser
import renko

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
    print(BRICK_SIZE)


if __name__ == "__main__":
    main()
