from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
from ibapi.order import *

import argparse
import json
import requests
import configparser

import threading
import time

# Configuration
config = configparser.ConfigParser()
config.read('/var/www/tws_api/settings.ini')

host = config['TWS']['host']
port = int(config['TWS']['port'])
client_id = int(config['TWS']['client_id'])

url = config['BACK']['url']
token = config['BACK']['token']


parser = argparse.ArgumentParser()
parser.add_argument("-account", "--account", required=True)
parser.add_argument("-s", "--symbol", required=True)
parser.add_argument("-st", "--symbol_type", required=True)
parser.add_argument("-a", "--action", required=True)
parser.add_argument("-t", "--type", required=True)
parser.add_argument("-q", "--quantity", required=True)
parser.add_argument("-tif", "--tif", required=False)
parser.add_argument("--orth", action=argparse.BooleanOptionalAction)
parser.add_argument("-lp", "--limit_price", required=False)
parser.add_argument("-sp", "--stop_price", required=False)
parser.add_argument("-tsp", "--trail_stop_price", required=False)

params = parser.parse_args()
# print(params)

class IBapi(EWrapper, EClient):

    def __init__(self):
        EClient.__init__(self, self)

    def nextValidId(self, orderId: int):
        super().nextValidId(orderId)
        self.nextorderId = orderId
        # print('The next valid order id is: ', self.nextorderId)

    def execDetails(self, reqId, contract, execution):
        print('Order Executed: ', reqId, contract.symbol, contract.secType, contract.currency, execution.execId, execution.orderId, execution.shares)
        print('execDetails', execution)
    
    def orderStatus(self, orderId , status:str, filled, remaining, avgFillPrice:float, permId:int,parentId:int, lastFillPrice:float, clientId:int, whyHeld:str, mktCapPrice: float):
        # print(json.dumps({ 'command' : 'orderStatus', 'orderId' : orderId, 'status' : status, 'filled' : filled, 'remaining' : remaining, 'avgFillPrice' : avgFillPrice, 'permId' : permId, 'parentId' : parentId, 'lastFillPrice' : lastFillPrice}, default=str))
        sendResult({ 'command' : 'orderStatus', 'orderId' : orderId, 'status' : status, 'filled' : filled, 'remaining' : remaining, 'avgFillPrice' : avgFillPrice, 'permId' : permId, 'parentId' : parentId, 'lastFillPrice' : lastFillPrice});


def run_loop():
    app.run()
    
def sendResult(send):
    requests.post(url, data={ 'api_token' : token, 'data' : json.dumps(send, default=str) } )

def makeContract(symbol, type, exchange = 'SMART', currency = 'USD'):
    contract = Contract()
    contract.symbol = symbol
    contract.secType = type
    contract.exchange = exchange
    contract.currency = currency
    
    return contract

#Create order object
def makeOrder(orderId, account, action, type, tif = 'DAY', orth = False, quantity = 0, limit_price = None, stop_price = None, trail_stop_price = None):
    order = Order()
    
    order.transmit = True
    
    order.outsideRth = orth
    order.account = account
    order.orderId = orderId
    order.action = action
    order.orderType = type
    order.tif = tif
    order.totalQuantity = float(quantity)
    
    if limit_price != None:
        order.lmtPrice = float(limit_price)
    if stop_price != None:
        order.auxPrice = float(stop_price)
    if trail_stop_price != None:
        order.trailStopPrice = float(trail_stop_price)
        
    return order

app = IBapi()
app.connect(host, port, client_id)

app.nextorderId = None

#Start the socket in a thread
api_thread = threading.Thread(target=run_loop, daemon=True)
api_thread.start()

#Check if the API is connected via orderid
while True:
    if isinstance(app.nextorderId, int):
        # print('connected')
        # print()
        break
    else:
        # print('waiting for connection')
        time.sleep(1)


order = makeOrder(app.nextorderId, params.account, params.action, params.type, params.tif, params.orth, params.quantity, params.limit_price, params.stop_price, params.trail_stop_price)
contract = makeContract(params.symbol, params.symbol_type)

#Place order
print(json.dumps({ 'command' : 'placeOrder', 'orderId' : order.orderId, 'order' : order, 'contract' : contract }, default=str))
# sendResult({ 'command' : 'placeOrder', 'orderId' : order.orderId, 'order' : order, 'contract' : contract })
app.placeOrder(order.orderId, contract, order)

app.nextorderId += 1

#wait for callbacks
time.sleep(5)

app.disconnect()
