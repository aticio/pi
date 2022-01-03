#!/bin/bash
BINANCE_API_KEY=$1
BINANCE_API_SECRET=$2
export BINANCE_API_KEY
export BINANCE_API_SECRET
cd /opt/pi/
nohup python3 /opt/pi/pi.py > /dev/null 2> /dev/null < /dev/null &