from datetime import datetime, time
import logging
from trading_core.strategies.base_strategy import Strategy

logger = logging.getLogger(__name__)

class FibStrategy(Strategy):
    STRATEGY_NAME = "Fib Strategy"

    def __init__(self, symbol, order_manager, trade_type="Intraday", sizing_type="Quantity", sizing_value=1):
        super().__init__(symbol, order_manager, trade_type, sizing_type, sizing_value)
        self.prices = []
        self.first_candle_close_time = time(9,30)
        self.first_candle_close_price = None
        self.first_candle_open_price = None
        self.is_tradeable = False
        self.fib_level_touched = None
        self.entry_time = time(9,45)
        self.position_price = None
        #self.trade_taken_today = False

    def on_tick(self, timestamp, data):
        if timestamp.time() <= self.first_candle_close_time:
            self.first_candle_close_price = data.get('ltp')
            self.first_candle_open_price = data.get('open')
            return
        
        if timestamp.time() < self.entry_time:
            self.prices.append(data.get('ltp'))
            if data.get('ltp') >= data.get("open")+ data.get("open")*1.01:
                self.is_tradeable = True
            else:
                self.is_tradeable = True
            if data.get('ltp') < (self.first_candle_close_price):
                self.fib_level_touched = True
            return
        
        position_details = self.order_manager.get_open_position(self.symbol)
        is_my_trade = position_details and position_details.get('strategy') == self.STRATEGY_NAME
        current_qty = position_details.get('quantity', 0) if position_details else 0

        if position_details and not is_my_trade:
            return  # Not our trade to manage

        if self._current_day is None or timestamp.date() > self._current_day:
            self._reset_day()
            self._current_day = timestamp.date()

        price = data.get('ltp', data.get('close'))

        if current_qty != 0:
            self._manage_open_position(price, timestamp, current_qty)
            return
        
        if timestamp.time() > self.entry_time:
            qty_to_trade = self._calculate_quantity(data.get('ltp'))
            if not self.fib_level_touched and self.is_tradeable:
                self.order_manager.place_order(
                    symbol=self.symbol,qty=qty_to_trade,side=1,order_type=2, timestamp=timestamp,
                    product_type=self.product_type,strategy_name = self.STRATEGY_NAME,
                    entry_price=data.get('ltp'),price=data.get('ltp')
                )
                self.position_price = data.get('ltp')
        return
    
    def _manage_open_position(self, price: float, timestamp: datetime, current_qty: int):
        if price == self.position_price *1.16:
            #Take profit
            qty_to_exit = abs(current_qty)
            side_to_exit = -1 if current_qty > 0 else 1
            self.order_manager.place_order(
                symbol=self.symbol, qty=qty_to_exit, side=side_to_exit, order_type=2, timestamp=timestamp,
                product_type=self.product_type, strategy_name=self.STRATEGY_NAME,
                entry_price=self.entry_price, price=price
            )
            self.trade_taken_today = True
        if price == self.position_price :
            qty_to_exit = abs(current_qty)
            side_to_exit = -1 if current_qty > 0 else 1
            self.order_manager.place_order(
                symbol=self.symbol, qty=qty_to_exit, side=side_to_exit, order_type=2, timestamp=timestamp,
                product_type=self.product_type, strategy_name=self.STRATEGY_NAME,
                entry_price=self.entry_price, price=price
            )
            self.trade_taken_today = True

    def _reset_day(self):
        self.fifteen_min_close_price = None
        self.trade_taken_today = False