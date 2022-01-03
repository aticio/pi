#!/bin/bash
cd /opt/pi/
pip install -r requirements.txt -U
kill -9 $(ps -ef | grep "python3 /opt/pi/pi.py" | grep -v grep | awk '{print $2}')
BINANCE_API_KEY=$1
BINANCE_API_SECRET=$2
export BINANCE_API_KEY
export BINANCE_API_SECRET
nohup python3 /opt/pi/pi.py > /dev/null 2> /dev/null < /dev/null &