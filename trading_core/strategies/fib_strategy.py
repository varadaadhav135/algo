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
        self.fib_level_touched = None
        self.entry_time = time(9,45)
        self.position_price = None
        #self.trade_taken_today = False

    def on_tick(self, timestamp, data):
        if timestamp.time() <= self.first_candle_close_time:
            self.first_candle_close_price = data.get('ltp')
            return
        
        if timestamp.time() < self.entry_time:
            self.prices.append(data.get('ltp'))
            if data.get('ltp') < 0.6*self.first_candle_close_price:
                self.fib_level_touched = True
            return
        
        position_details = self.order_manager.get_open_position(self.symbol)
        is_my_trade = position_details and position_details.get('strategy') == self.STRATEGY_NAME
        current_qty = position_details.get('quantity', 0) if position_details else 0

        price = data.get('ltp', data.get('close'))
        if current_qty != 0:
            self._manage_open_position(price, timestamp, current_qty)
            return
        
        if timestamp.time() > self.entry_time:
            qty_to_trade = self._calculate_quantity(data.get('ltp'))
            if not self.fib_level_touched and data.get('ltp') > self.first_candle_close_price:
                self.order_manager.place_order(
                    symbol=self.symbol,qty=qty_to_trade,side=1,order_type=2, timestamp=timestamp,
                    product_type=self.product_type,strategy_name = self.STRATEGY_NAME,
                    entry_price=data.get('ltp'),price=data.get('ltp')
                )
                self.position_price = data.get('ltp')
        return
    
    def _manage_open_position(self, price: float, timestamp: datetime, current_qty: int):
        if price == self.position_price *1.16:
            #Sell the stock here
            pass