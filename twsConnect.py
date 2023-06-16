from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
from ibapi.order import Order
from ibapi.execution import ExecutionFilter

import configparser
import json
import requests
from flask import Flask, request
import threading
import time
import signal

# Configuration
config = configparser.ConfigParser()
config.read('settings.ini')

tws_host = config['TWS']['host']
tws_port = int(config['TWS']['port'])
tws_client_id = int(config['TWS']['client_id'])

host = config['HTTP']['host']
port = int(config['HTTP']['port'])

url = config['BACK']['url']
token = config['BACK']['token']


class IBapi(EWrapper, EClient):

    requests = {}
    
    def __init__(self):
        EClient.__init__(self, self)
    
    def connectionClosed(self):
        super().connectionClosed()
        print('tws connection closed')
        
    def addRequest(self, id, command, data = {}):
        print('addRequest', 'id =', id, type(id))
        self.requests[id] = { 'id' : id, 'command' : command, 'data' : data, 'error' : { 'status' : False, 'list' : [] }, 'end' : False, 'time' : { 'start' : getMilliseconds() , 'end' : None } }
        
    # Error handling function
    def error(self, reqId, errorCode, errorString, advancedOrderRejectJson=""):
        # super().error(reqId, errorCode, errorString, advancedOrderRejectJson)
        print("error: reqId =", reqId, "errorCode =", errorCode, 'errorString =', errorString, 'advanced =', advancedOrderRejectJson)
        # key = str(reqId)
        # print('reqId =', reqId, type(reqId))
        if (reqId in self.requests):
            error = { 'code' : errorCode, 'dateTime' : getMilliseconds(), 'text' : errorString, 'advanced' : advancedOrderRejectJson }
            self.requests[reqId]['error']['list'].append(error)
            if errorCode not in [ 399, 2109 ]:
                self.requests[reqId]['error']['status'] = True
                # self.requests[reqId]['end'] = True
        
    def nextValidId(self, orderId: int):
        super().nextValidId(orderId)
        self.nextorderId = orderId
    
    def symbolSamples(self, reqId, contractDescriptions):
        super().symbolSamples(reqId, contractDescriptions)
        if (reqId in self.requests):
            self.requests[reqId]['data']['samples'] = []
            for contractDescription in contractDescriptions:
                self.requests[reqId]['data']['samples'].append({ 'derivativeSecTypes' : contractDescription.derivativeSecTypes, 'contract' : vars(contractDescription.contract) })
            self.requests[reqId]['end'] = True
        else:
            print('symbolSamples error id: ', reqId, contractDescription)
            
    def contractDetails(self, reqId, contractDetails):
        super().contractDetails(reqId, contractDetails)
        if (reqId in self.requests):
            contractDetails.contract = vars(contractDetails.contract)
            
            self.requests[reqId]['data']['details'] = vars(contractDetails)
            self.requests[reqId]['end'] = True
        else:
            print('contractDetails error id: ', reqId, vars(contractDetails))
      
    def execDetails(self, reqId, contract, execution):
        super().execDetails(reqId, contract, execution)
        data = { 'reqId' : reqId, 'contract' : vars(contract), 'execution' : vars(execution)}
        # print(json.dumps(data, default=str))
        if (reqId in self.requests):
            if self.requests[reqId]['command'] == 'executions':
                self.requests[reqId]['data']['details'][execution.permId] = data
        # sendResult({ 'command' : 'execDetails', 'id' : execution.execId, 'contract' : vars(contract), 'execution' : vars(execution) })
        
    def execDetailsEnd(self, reqId):
        super().execDetailsEnd(reqId)
        print('execDetailsEnd: ', reqId)
        if (reqId in self.requests):
            self.requests[reqId]['end'] = True
        
    def commissionReport(self, commissionReport):
        super().commissionReport(commissionReport)
        data = vars(commissionReport)
        # realizedPNL yield_
        # if data.realizedPNL == 1.7976931348623157e+308:
            # data.realizedPNL = None
        # print(json.dumps(data, default=str))
        for each in self.requests:
            if self.requests[each]['command'] == 'executions':
                self.requests[each]['data']['commission'].append(data)
        
    def orderStatus(self, orderId, status, filled, remaining, avgFillPrice, permId, parentId, lastFillPrice, clientId, whyHeld, mktCapPrice):
        super().orderStatus(orderId, status, filled, remaining, avgFillPrice, permId, parentId, lastFillPrice, clientId, whyHeld, mktCapPrice)
        data = { 'command' : 'orderStatus', 'dateTime' : getMilliseconds(), 'orderId' : orderId, 'status' : status, 'filled' : filled, 'remaining' : remaining, 'avgFillPrice' : avgFillPrice, 'permId' : permId, 'parentId' : parentId, 'lastFillPrice' : lastFillPrice }
        # print(data)
        if (orderId in self.requests):
            if self.requests[orderId]['command'] == 'placeOrder':
                self.requests[orderId]['data']['status'].append(data)
                self.requests[orderId]['end'] = True
            elif self.requests[orderId]['command'] == 'cancelOrder':
                self.requests[orderId]['data']['status'].append(data)
                self.requests[orderId]['end'] = True
        else:
            foundOrders = False
            for each in self.requests:
                if self.requests[each]['command'] == 'orders':
                    foundOrders = True
                    self.requests[each]['data']['status'].append(data)
            if (not foundOrders):
                sendResult(data)
        
    def openOrder(self, orderId, contract, order, orderState):
        super().openOrder(orderId, contract, order, orderState)
        if (order.filledQuantity == 170141183460469231731687303715884105727):
            order.filledQuantity = None
        data = { 'command' : 'openOrder', 'dateTime' : getMilliseconds(), 'contract' : vars(contract), 'order' : vars(order) , 'status' : orderState.status }
        # print(data)
        if (orderId in self.requests):
            if self.requests[orderId]['command'] == 'placeOrder':
                self.requests[orderId]['data']['orders'][order.permId] = data
        else:
            for each in self.requests:
                if self.requests[each]['command'] == 'orders':
                    self.requests[each]['data']['orders'][order.permId] = data
    
    def openOrderEnd(self):
        super().openOrderEnd()
        for each in self.requests:
            if self.requests[each]['command'] == 'orders':
                self.requests[each]['end'] = True
        print('openOrderEnd')
        
    def completedOrder(self, contract, order, orderState):
        super().completedOrder(contract, order, orderState)
        if (order.filledQuantity == 170141183460469231731687303715884105727):
            order.filledQuantity = None
        data = { 'command' : 'completedOrder', 'dateTime' : getMilliseconds(), 'contract' : vars(contract), 'order' : vars(order) , 'status' : orderState.status }
        foundOrders = False
        for each in self.requests:
            if self.requests[each]['command'] == 'orders':
                foundOrders = True
                self.requests[each]['data']['orders'][order.permId] = data
        if (not foundOrders):
            sendResult(data)
        # print('completedOrder', vars(contract), vars(order), vars(orderState))
        
    def completedOrdersEnd(self):
        super().completedOrdersEnd()
        print('completedOrdersEnd')

    def managedAccounts(self, accountsList):
        super().managedAccounts(accountsList)
        # print('managedAccounts: ', accountsList)
        for each in self.requests:
            if self.requests[each]['command'] == 'accounts':
                self.requests[each]['data'] = accountsList
                self.requests[each]['end'] = True
        
    def positionMulti(self, reqId, account, modelCode, contract, pos, avgCost):
        super().positionMulti(reqId, account, modelCode, contract, pos, avgCost)
        data = { 'account_id' : account, 'contract' : vars(contract), 'quantity' : pos, 'avgCost' : avgCost }
        # print(data)
        if (reqId in self.requests):
            self.requests[reqId]['data']['positions'].append(data)
        else:
            print(json.dumps({ 'command': 'positionMulti error id', 'data' : data }, default=str))
        
    def positionMultiEnd(self, reqId):
        super().positionMultiEnd(reqId)
        print(reqId)
        if (reqId in self.requests):
            self.requests[reqId]['end'] = True
        else:
            print('positionMultiEnd error id: ', reqId)
        
#    def historicalData(self, reqId, bar):
#        print("HistoricalData. ReqId:", reqId, "BarData.", bar)
#        
#    def historicalDataEnd(self, reqId: int, start: str, end: str):
#        super().historicalDataEnd(reqId, start, end)
#        print("HistoricalDataEnd. ReqId:", reqId, "from", start, "to", end)
        

def getMilliseconds():
    return round(time.time()*1000)

def tws_loop():
    tws.run()
    
def http_loop():
    http.run(host=host,port=port)
    
def signal_handler(signal, frame):
    print()
    print('Try exiting')
    
    tws.disconnect()
    # while not tws.connection:
        # print(api_thread.is_alive())
    time.sleep(1)
    # else:        
        # sys.exit(0)
    
    
def sendResult(send):
   requests.post(url, data={ 'api_token' : token, 'data' : json.dumps(send, default=str) } )

def waitResponse(id, command, wait = 5):

    # print('waitResponse: ', id, command)
    responce = {
        'command' : command,
        'result' : {},
        'error' : False,
        'errorText' : '',
    }
    
    while wait > 0:
        if tws.requests[id]['end']:
            responce['result'] = tws.requests[id]
            responce['result']['time']['end'] = getMilliseconds()
            # responce['error'] = responce['result']['error']['status']
            del tws.requests[id]
            print('waitResponse end: ', tws.requests)
            # print(responce)
            return json.dumps(responce, default=str)
        else:
            wait -= 0.1
            time.sleep(0.1)
    else:
        responce['result'] = tws.requests[id]
        responce['result']['time']['end'] = getMilliseconds()
        responce['error'] = True
        responce['errorText'] = 'request waiting time exceeded'
        del tws.requests[id]
        print('waitResponse error end: ', tws.requests)
        return json.dumps(responce, default=str)

#Create contract object
# def makeContract(symbol, type, conId=None, exchange='SMART:ARCA', currency='USD'):
def makeContract(params):
    contract = Contract()

    # if not params:
    if 'symbol' in params and 'symbol_type' in params and 'currency' in params:    
        contract.symbol = params['symbol']
        contract.secType = params['symbol_type']
        contract.currency = params['currency']
    if 'lexchange' in params and params['lexchange'] != None:
        contract.primaryExchange = params['lexchange']
    if 'conid' in params and params['conid'] != None:
        contract.conId = params['conid']
        
    if 'exchange' in params:
        contract.exchange = params['exchange']
    else:
        contract.exchange = 'SMART'

    # print('contract: ', vars(contract))
    return contract
    
#Create order object
def makeOrder(orderId, params):
    order = Order()
    
    order.transmit = True
    
    order.outsideRth = params['orth']
    order.account = params['account']
    order.orderId = orderId
    order.action = params['action']
    order.orderType = params['type']
    order.tif = params['tif']
    order.totalQuantity = float(params['quantity'])
    
    if 'limit_price' in params:
        order.lmtPrice = float(params['limit_price'])
    if 'stop_price' in params:
        order.auxPrice = float(params['stop_price'])
    if 'trail_stop_price' in params:
        order.trailStopPrice = float(params['trail_stop_price'])
    
    # print('makeOrder: ', vars(order))
        
    return order

tws = IBapi()

tws.connect(tws_host, tws_port, tws_client_id)

tws.nextorderId = None

http = Flask(__name__)

@http.route('/api_status', methods=['POST'])
def apiStatus():
    return json.dumps({ 'command' : 'api_status', 'requests' : tws.requests }, default=str)

# @http.route('/get_time', methods=['POST'])
# def getTime():
#    
#     fName = 'getTime'
#     identification=getMilliseconds()
#     tws.addRequest(id=identification, command=fName, data={ 'start' : time.time() })
#     # tws.reqCurrentTime()
#    
#     return waitResponse(id=identification, command=fName)

@http.route('/find_symbol', methods=['POST'])
def findSymbol():
    
    params = json.loads(request.form['data'])
    print(params)
    
    fName = 'findSymbol'
    identification=tws.nextorderId
    tws.addRequest(id=identification, command=fName, data={})
    
    tws.reqMatchingSymbols(reqId=identification, pattern=params['pattern'])
    tws.nextorderId += 1
    
    return waitResponse(id=identification, command=fName)
    
@http.route('/symbol_detail', methods=['POST'])
def symbolDetail():    
    
    params = json.loads(request.form['data'])
    print(params)
    
    fName = 'symbolDetail'
    identification=tws.nextorderId
    tws.addRequest(id=identification, command=fName, data={})

    contract = makeContract(params)
    tws.reqContractDetails(identification, contract)
    tws.nextorderId += 1
    
    return waitResponse(id=identification, command=fName)

@http.route('/place_order', methods=['POST'])
def placeOrder():
    
    params = json.loads(request.form['data'])
    print('placeOrder: ', params)
    
    fName = 'placeOrder'
    identification=tws.nextorderId
    tws.addRequest(id=identification, command=fName, data={ 'orders' : {}, 'status' : [] })
    
    order = makeOrder(orderId=identification, params=params)
    contract = makeContract(params)
    
    # tws.reqCurrentTime() # ???
    tws.placeOrder(identification, contract, order)
    tws.nextorderId += 1
    
    return waitResponse(id=identification, command=fName)

@http.route('/cancel_order', methods=['POST'])
def cancelOrder():
    
    params = json.loads(request.form['data'])
    print(params)
    
    fName = 'cancelOrder'
    identification = int(params['orderId'])
    tws.addRequest(id=identification, command=fName, data={ 'orders' : {}, 'status' : [] })
    
    tws.cancelOrder(identification, '')
    
    return waitResponse(id=identification, command=fName, wait=1)

@http.route('/orders', methods=['POST'])
def orders():
        
    fName = 'orders'
    identification = getMilliseconds()
    tws.addRequest(id=identification, command=fName, data={ 'orders' : {}, 'status' : [] })
    
    tws.reqCompletedOrders(False)
    tws.reqOpenOrders()
    # tws.reqAllOpenOrders()
    
    return waitResponse(id=identification, command=fName, wait=10)

@http.route('/executions', methods=['POST'])
def executions():
    
    fName = 'executions'
    identification=tws.nextorderId
    tws.addRequest(id=identification, command=fName, data={ 'details' : {}, 'commission' : [] })
    
    filter = ExecutionFilter()
    tws.reqExecutions(identification, filter)
    tws.nextorderId += 1
    
    return waitResponse(id=identification, command=fName)

@http.route('/accounts', methods=['POST'])
def accounts():
    
    fName = 'accounts'
    identification = getMilliseconds()
    tws.addRequest(id=identification, command=fName, data={})
    
    tws.reqManagedAccts()

    return waitResponse(id=identification, command=fName)

@http.route('/positions', methods=['POST'])
def positions():
    
    params = json.loads(request.form['data'])
    print(params)
    
    fName = 'positions'
    identification=tws.nextorderId
    tws.addRequest(id=identification, command=fName, data={ 'positions' : [] })

    tws.reqPositionsMulti(reqId=identification, account=params['account_id'], modelCode='')
    tws.nextorderId += 1
     
    return waitResponse(id=identification, command=fName)

# ???
# @http.route('/historical_data', methods=['POST'])
# def historicalData():
#    
#     params = json.loads(request.form['data'])
#     print(params)
#    
#     tws.historicalList = []
#     tws.endHistoricalList = False
#     contract = makeContract(symbol=params['symbol'], type=params['symbol_type'], conId=params['conId'], currency=params['currency'])
#    
#     tws.reqHistoricalData(tws.nextorderId, contract, '', '1 M', '1 day', 'TRADES', 0, 1, False, [])
#    
#     wait_seconds = tws_wait
#     while wait_seconds > 0:
#         if tws.endHistoricalList:
#             return json.dumps({ 'command' : 'historicalData', 'error' : False, 'result' : tws.historicalList }, default=str)
#         else:
#             wait_seconds -= 0.1
#             time.sleep(0.1)
#     else:
#         return json.dumps({ 'command' : 'historicalData', 'error' : True, 'result' : 'request waiting time exceeded' }, default=str)

#Start the socket in a thread
api_thread = threading.Thread(target=tws_loop, daemon=True)
api_thread.start()

#Start the flask in a thread
flask_thread = threading.Thread(target=http_loop, daemon=True)
flask_thread.start()

#Check if the API is connected via orderid
while True:
    if isinstance(tws.nextorderId, int):
        print('connected')
        tws.reqAutoOpenOrders(True)
        print()
        break
    else:
        print('waiting for connection')
        time.sleep(1)

if __name__ == "__main__":
    signal.signal(signal.SIGINT, signal_handler)

#wait for callbacks
# time.sleep(10)
# print('close connection')
# tws.disconnect()
