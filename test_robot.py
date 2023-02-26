import json
import time as time_lib
import pprint
import pathlib
import operator
import pandas as pd

from datetime import datetime
from datetime import timedelta
from configparser import ConfigParser

from pyrobot.robot import PyRobot
from pyrobot.indicators import Indicators
from pyrobot.trades import Trade

from td.client import TDClient

# Grab configuration values.
config = ConfigParser()
config.read('config/config.ini')

CLIENT_ID = config.get('main', 'CLIENT_ID')
REDIRECT_URI = config.get('main', 'REDIRECT_URI')
CREDENTIALS_PATH = config.get('main', 'JSON_PATH')
ACCOUNT_NUMBER = config.get('main', 'ACCOUNT_NUMBER')

# Initalize the robot.
trading_robot = PyRobot(
    client_id=CLIENT_ID,
    redirect_uri=REDIRECT_URI,
    credentials_path=CREDENTIALS_PATH,
    paper_trading=True, 
    trading_account=ACCOUNT_NUMBER
)

# Create a Portfolio
trading_robot_portfolio = trading_robot.create_portfolio()

# define trading symbol
trading_symbol = 'FCEL'

# Add a single position
trading_robot_portfolio.add_position(
    symbol=trading_symbol,
    asset_type='equity'
)

# Grab historical prices, first define the start date and end date.
start_date = datetime.today()
end_date = start_date - timedelta(days=30)

# Grab the historical prices.
historical_prices = trading_robot.grab_historical_prices(
    start=end_date,
    end=start_date,
    bar_size=1,
    bar_type='minute'
)

pprint.pprint(historical_prices['candles'])

# Convert data to a Data Frame.
stock_frame = trading_robot.create_stock_frame(
    data=historical_prices['aggregated']
)

pprint.pprint(stock_frame.frame.head())

# We can also add the stock frame to the Portfolio object.
trading_robot.portfolio.stock_frame = stock_frame

# Additionally the historical prices can be set as well.
trading_robot.portfolio.historical_prices = historical_prices

# Portfolio Variance
pprint.pprint(trading_robot.portfolio.portfolio_metrics())

# Create an indicator Object.
indicator_client = Indicators(price_data_frame=stock_frame)

# Add the RSI Indicator.
indicator_client.rsi(period=14, column_name='rsi14')

# Add the 200 day simple moving average.
indicator_client.sma(period=200, column_name='sma200')

# Add the 50 day simple moving average.
indicator_client.sma(period=50, column_name='sma50')

# Add the 50 day exponentials moving average.
indicator_client.ema(period=50, column_name='ema50')

pprint.pprint(stock_frame.frame.tail())

# Add a signal to check for.
indicator_client.set_indicator_signal_compare(
    indicator_1='sma50',
    indicator_2='sma200',
    condition_buy=operator.ge,
    condition_sell=operator.le
)

print(trading_robot.stock_frame.frame.tail())

# Create a new Trade Object
new_long_trade = trading_robot.create_trade(
    trade_id='long_enter',
    enter_or_exit='enter',
    long_or_short='long',
    order_type='mkt'
)

# Add an Order Leg.
new_long_trade.instrument(
    symbol=trading_symbol,
    quantity=1,
    asset_type='EQUITY'
)

# Print out the order.
pprint.pprint(new_long_trade.order)

# Create a new Trade Object
new_exit_trade = trading_robot.create_trade(
    trade_id='long_exit',
    enter_or_exit='exit',
    long_or_short='long',
    order_type='mkt'
)

# Add an Order Leg.
new_exit_trade.instrument(
    symbol=trading_symbol,
    quantity=1,
    asset_type='EQUITY'
)

# Print out the order.
pprint.pprint(new_exit_trade.order)

def default(obj):
    if isinstance(obj, TDClient):
        return str(obj)

with open(file='order_strategies/json', mode='w+') as fp:
    json.dump(obj=[new_long_trade.to_dict(), new_exit_trade.to_dict()], 
              fp=fp, 
              default=default,
              indent=4
    )

# # Make it Good Till Cancel.
# new_long_trade.good_till_cancel(cancel_time=datetime.now())

# # Change the session
# new_long_trade.modify_session(session='am')

# # Add a Stop Loss Order with the Main Order.
# new_long_trade.add_stop_loss(
#     stop_size=.10,
#     percentage=False
# )

# # Check for signals.
# signals = indicator_client.check_signals()

# # Print the Head.
# print(trading_robot.stock_frame.frame.head())

# Print the Signals.
# pprint.pprint(signals)

# Define a trading dictionary.
trades_dict = {
    trading_symbol: {
	'buy': {
  		'trade_func': trading_robot.trades['long_enter'],
   		'trade_id': trading_robot.trades['long_enter'].trade_id
	},
	'sell': {
  		'trade_func': trading_robot.trades['long_exit'],
   		'trade_id': trading_robot.trades['long_exit'].trade_id
	}
    }
}

# define the ownership
ownership_dict = {
    trading_symbol: False
}


# intialize an order variable
order: Trade = None

while trading_robot.regular_market_open:

    # Grab the latest bar.
    latest_bars = trading_robot.get_latest_bar()

    # Add to the Stock Frame.
    stock_frame.add_rows(data=latest_bars)

    # Refresh the Indicators.
    indicator_client.refresh()

    print("="*50)
    print("Current StockFrame:")
    print("-"*50)
    print(stock_frame.symbol_groups.tail())
    print("-"*50)
    print("")

    # Check for signals.
    signals = indicator_client.check_signals()

    # define the buy and sell signals
    buys = signals['buys'].to_list()
    sells = signals['sells'].to_list()

    print("="*50)
    print("Current signals:")
    print("-"*50)
    print("Symbols: {}".format(list(trades_dict.keys())[0]))
    print("Ownership Status: {}".format(list(ownership_dict[trading_symbol])))
    print("buy signals: {}".format(buys))
    print("sell signals: {}".format(sells))
    print("-"*50)
    print("")
    
    if ownership_dict[trading_symbol] is False and buys:
		# Execute Trades.
        trading_robot.execute_signals(
			signals=signals,
			trades_to_execute=trades_dict
		)

        ownership_dict[trading_symbol] = True
        order : Trade = trades_dict[trading_symbol]['buy']['trade_func']

    if ownership_dict[trading_symbol] is True and sells:
		# Execute Trades.
        trading_robot.execute_signals(
			signals=signals,
			trades_to_execute=trades_dict
		)
        
        ownership_dict[trading_symbol] = False
        order : Trade = trades_dict[trading_symbol]['sell']['trade_func']

    # Grab the last bar.
    last_bar_timestamp = trading_robot.stock_frame.frame.tail(
        n=1
    ).index.get_level_values(1)

    # Wait till the next bar.
    trading_robot.wait_till_next_bar(last_bar_timestamp=last_bar_timestamp)

    if order:
        order.check_status()

