import pandas as pd
import datetime
from datetime import datetime as dt
from pytz import timezone
import time

import alpaca_trade_api as alpaca
import json

from datetime import timedelta
import os.path
import config

api = alpaca.REST(config.API_KEY, config.SECRET_KEY, base_url='https://paper-api.alpaca.markets/', api_version = 'v2')
tickers = config.QQQ_SYMBOLS
global TICKERS 
TICKERS = tickers

def get_minute_data(tickers):
    
    def save_min_data(ticker):
        prices = api.get_trades(str(ticker), start = ((dt.now().astimezone(timezone('America/New_York'))) - timedelta(minutes=2)).isoformat(),
                                        end = ((dt.now().astimezone(timezone('America/New_York')))).isoformat(), 
                                        limit = 10000).df[['price']]
        prices.index = pd.to_datetime(prices.index, format = '%Y-%m-%d').strftime('%Y-%m-%d %H:%M')
        prices = prices[~prices.index.duplicated(keep='first')]

        quotes = api.get_quotes(str(ticker), start = ((dt.now().astimezone(timezone('America/New_York'))) - timedelta(minutes=2)).isoformat(),
                                        end = ((dt.now().astimezone(timezone('America/New_York')))).isoformat(), 
                                        limit = 10000).df[['ask_price']]
        quotes.index = pd.to_datetime(quotes.index, format = '%Y-%m-%d').strftime('%Y-%m-%d %H:%M')
        quotes = quotes[~quotes.index.duplicated(keep='first')]

        df = pd.merge(prices, quotes, how= 'inner', left_index=True, right_index= True)
        df.to_csv('tick_data/{}.csv'.format(ticker))
        print(ticker)

    for ticker in tickers:
        try:
            save_min_data(ticker)
        except Exception as e:
            tickers.pop(tickers.index(ticker))
            print("unable to save {} data - {}".format(ticker, e))
        


# Returns a list of most recent ROCs for all tickers
def return_ROC_list(tickers):
    ROC_tickers = []
    for i in range(len(tickers)):
        df = pd.read_csv('tick_data/{}.csv'.format(tickers[i]))
        df.set_index('timestamp', inplace= True)
        df.index = pd.to_datetime(df.index, format ='%Y-%m-%d').strftime('%Y-%m-%d %H:%M')
        ask = df['ask_price']
        rocs = (ask[ask.shape[0] - 1] - ask[ask.shape[0] -2])/(ask[ask.shape[0] - 2])*1000
        ROC_tickers.append(rocs) # [-1] forlast value (latest)
    return ROC_tickers

# compared ASK vs LTP
def compare_ask_ltp(tickers):
    
        if len(tickers) != 0:
            buy_stock = ''
            ROCs = return_ROC_list(tickers)
            max_ROC = max(ROCs)

            if max_ROC <= 0:
                return 0
            max_ROC_index = ROCs.index(max_ROC)

            for i in range(len(tickers)):
                buy_stock_init = tickers[max_ROC_index]
                df = pd.read_csv('tick_data/{}.csv'.format(buy_stock_init))
                df.set_index('timestamp', inplace= True)
                df.index = pd.to_datetime(df.index, format ='%Y-%m-%d').strftime('%Y-%m-%d %H:%M')

                # list to keep track of number of ask_prices > price
                buy_condition = []
                ask_col = df.columns.get_loc('ask_price')
                price_col = df.columns.get_loc('price')
                for i in range(df.shape[0] - 2, df.shape[0]):
                    buy_condition.append(df.iloc[i, ask_col] > df.iloc[i,price_col])

                if buy_condition[-1] == True:
                    buy_stock = buy_stock_init
                    return buy_stock
                else:
                    tickers.pop(max_ROC_index)
                    ROCs.pop(max_ROC_index)
                    if(len(tickers)==0):
                        return -1
                    max_ROC = max(ROCs)
                    max_ROC_index =  ROCs.index(max_ROC)
        else: tickers = TICKERS

# returns which stock to buy
def stock_to_buy(tickers):
        entry_buy = compare_ask_ltp(tickers)
        return entry_buy

def algo(tickers):

    # Calculates ROC
    # Checks for stock with highest ROC and if ask_price > price
    # Returns ticker to buy
    stock = stock_to_buy(tickers)
    return stock


def buy(stock_to_buy: str):
    
    cashBalance = api.get_account().cash
    price_stock = api.get_latest_trade(str(stock_to_buy)).price
    targetPositionSize = ((float(cashBalance)) / (price_stock)) # Calculates required position size
    api.submit_order(str(stock_to_buy), targetPositionSize, "buy", "market", "day") # Markeyt order to open position    
    
    mail_content = '''ALERT
    
    BUY Order Placed for {}: {} Shares at ${}'''.format(stock_to_buy, targetPositionSize, price_stock)
    
    if os.path.isfile('Orders.csv'):
        df = pd.read_csv('Orders.csv')
        df.drop(columns= 'Unnamed: 0', inplace = True)
        df.loc[len(df.index)] = [((dt.now()).astimezone(timezone('America/New_York'))).strftime("%H:%M:%S"), stock_to_buy, 'buy',
                                 price_stock, targetPositionSize, targetPositionSize*price_stock, api.get_account().cash] 
    else:    
        df = pd.DataFrame()
        df[['Time', 'Ticker', 'Type', 'Price', 'Quantity', 'Total', 'Acc Balance']] = ''
        df.loc[len(df.index)] = [((dt.now()).astimezone(timezone('America/New_York'))).strftime("%H:%M:%S"), stock_to_buy, 'buy',
                                 price_stock, targetPositionSize, targetPositionSize*price_stock, api.get_account().cash] 
    df.to_csv('Orders.csv')
    return mail_content

def sell(current_stock):
    # sells current_stock
    quantity = float(api.get_position(str(current_stock)).qty)    
    sell_price = api.get_latest_trade(str(current_stock)).price
    api.cancel_all_orders() # cancels all pending (to be filled) orders 
    api.close_position(str(current_stock)) # sells current stock
    
    mail_content = '''ALERT

    SELL Order Placed for {}: {} Shares at ${}'''.format(current_stock, quantity, sell_price)
    
    df = pd.read_csv('Orders.csv')
    df.drop(columns= 'Unnamed: 0', inplace = True)
    df.loc[len(df.index)] = [((dt.now()).astimezone(timezone('America/New_York'))).strftime("%H:%M:%S"), current_stock, 'sell', sell_price, quantity, quantity*sell_price, api.get_account().cash] 
    
#     with open('Orders.csv', 'a') as f:
#         df.to_csv(f, header=f.tell()==0)
    df.to_csv('Orders.csv')
    return mail_content

def check_rets(current_stock):
    # checks returns for stock in portfolio (api.get_positions()[0].symbol)
    returns = float(api.get_position(str(current_stock)).unrealized_plpc)*100
    print("{} profit/loss percent: {}%".format(current_stock, returns))
    if (returns >= 0.1):
        mail_content = sell(current_stock)
    else: 
        mail_content = 0              
    return mail_content

def mail_alert(content, delay):
    print(content)

def main():
    
    if api.get_clock().is_open == True:
    # sends mail when bot starts running
        mail_content = 'The bot started running on {} at {} UTC'.format(dt.now().strftime('%Y-%m-%d'), dt.now().strftime('%H:%M:%S'))
        mail_alert(mail_content, 0)

    while True:
        """
        if api.get_account().pattern_day_trader == True:
            mail_alert('Pattern day trading notification, bot is stopping now', 0)
            break
        """
        tickers = TICKERS
        try:
            if api.get_clock().is_open == True:
                # check if we have made the first ever trade yet, if yes, timeframe = 1 min, else trade at 10:00 am
                if float(api.get_account().cash) > 10:
                    get_minute_data(tickers)
                    stock_to_buy = algo(tickers)

                    if stock_to_buy == 0:
                        print('All ROCs are <= 0')
                        time.sleep(2)
                        continue
                    elif stock_to_buy == -1:
                        print('All Ask < LTP')
                        time.sleep(2)
                        continue
                        
                    # checks if stock_to_buy exists in positions
                    # doesn't buy if LTP for stock_to_buy > avg_entry_price
                    else:
                        num_stocks = len(api.list_positions())
                        curr_stocks = []

                        if num_stocks != 0:
                            for i in range(num_stocks):
                                curr_stocks.append(api.list_positions()[i])
                                
                            if stock_to_buy in curr_stocks:
                                if api.get_latest_trade(stock_to_buy).price > float(api.get_position(stock_to_buy).avg_entry_price):
                                    print('LTP for {} > Average Entry Price'.format(stock_to_buy))
                                    time.sleep(2)
                                    continue

                    try:
                        if api.get_activities()[0].order_status == 'partially_filled':
                            api.cancel_all_orders()
                    except:
                        pass
                    mail_content = buy(stock_to_buy)
                    mail_alert(mail_content, 5)
                    time.sleep(3)
                    continue

                else:
                        
                    num_stocks = len(api.list_positions())
                    current_stocks = []
                    mail_content_list = []
                    
                    for pos in range(num_stocks):
                        current_stocks.append(api.list_positions()[pos].symbol)
                        
                    for stock in current_stocks:
                        mail_content = check_rets(stock)
                        mail_content_list.append(mail_content)
                        
                    if any(mail_content_list):
                        for mail in mail_content_list:
                            if mail != 0:
                                mail_alert(mail, 0)
                    else:
                        time.sleep(3)

            else:
                time.sleep(300)
                if api.get_clock().is_open == True:
                    continue
                else:
                    mail_content = 'The market is closed now'
                    mail_alert(mail_content, 0)
                    print(mail_content)
                    break
        except Exception as e:
            print(e)
            continue

    if api.get_clock().is_open == False:
        # sends mail when bot starts running
        mail_content = 'The bot stopped running on {} at {} UTC'.format(dt.now().strftime('%Y-%m-%d'), dt.now().strftime('%H:%M:%S'))
        mail_alert(mail_content, 0)
            
if __name__ == '__main__':
    main()
