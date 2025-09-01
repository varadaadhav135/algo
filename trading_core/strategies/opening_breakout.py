from datetime import datetime, time
import logging
from trading_core.strategies.base_strategy import Strategy

logger = logging.getLogger(__name__)


class OpeningBreakoutStrategy(Strategy):
    STRATEGY_NAME = "Opening Breakout"

    def __init__(self, symbol, order_manager, trade_type="Intraday",
                 sizing_type="Quantity", sizing_value=1,
                 threshold=1.0, stoploss=1.0, target=2.0):
        super().__init__(symbol, order_manager, trade_type, sizing_type, sizing_value)
        self.threshold_percent = threshold
        self.stoploss_percent = stoploss
        self.target_percent = target

        self.candle_close_time = time(9, 30)
        self.market_close_time = time(15, 15)
        self.fifteen_min_close_price = None
        self.position = None
        self.entry_price = None
        self.trade_taken_today = False
        self._current_day = None

    def on_tick(self, timestamp: datetime, price: float):
        if self._current_day is None or timestamp.date() > self._current_day:
            self._reset_day()
            self._current_day = timestamp.date()

        if self.position:
            self._manage_open_position(price, timestamp)
            return

        if self.fifteen_min_close_price is None and timestamp.time() >= self.candle_close_time:
            self.fifteen_min_close_price = price

        if not self.position and not self.trade_taken_today and self.fifteen_min_close_price is not None:
            self._look_for_entry_signal(price, timestamp)

    def _manage_open_position(self, price: float, timestamp: datetime):
        should_exit, reason = False, None
        if self.position == 'long':
            if price >= self.entry_price * (1 + self.target_percent / 100):
                should_exit, reason = True, "Target Profit Hit"
            elif price <= self.entry_price * (1 - self.stoploss_percent / 100):
                should_exit, reason = True, "Stop Loss Hit"
        elif self.position == 'short':
            if price <= self.entry_price * (1 - self.target_percent / 100):
                should_exit, reason = True, "Target Profit Hit"
            elif price >= self.entry_price * (1 + self.stoploss_percent / 100):
                should_exit, reason = True, "Stop Loss Hit"

        if self.trade_type == "Intraday" and timestamp.time() >= self.market_close_time:
            should_exit, reason = True, "Intraday Auto Square-Off"

        if should_exit:
            qty_to_trade = self._calculate_quantity(price)
            if qty_to_trade <= 0: return

            side_to_exit = -1 if self.position == 'long' else 1
            self.order_manager.place_order(
                symbol=self.symbol, qty=qty_to_trade, side=side_to_exit, order_type=2, timestamp=timestamp,
                product_type=self.product_type, strategy_name=self.STRATEGY_NAME,
                entry_price=self.entry_price, exit_reason=reason, price=price
            )
            self.position = None
            self.trade_taken_today = True

    def _look_for_entry_signal(self, price: float, timestamp: datetime):
        qty_to_trade = self._calculate_quantity(price)
        if qty_to_trade <= 0: return

        breakout_high = self.fifteen_min_close_price * (1 + self.threshold_percent / 100)
        breakout_low = self.fifteen_min_close_price * (1 - self.threshold_percent / 100)

        if price > breakout_high:
            self.order_manager.place_order(
                symbol=self.symbol, qty=qty_to_trade, side=1, order_type=2, timestamp=timestamp,
                product_type=self.product_type, strategy_name=self.STRATEGY_NAME,
                entry_price=price, price=price
            )
            self.position = 'long'
            self.entry_price = price
        elif price < breakout_low:
            self.order_manager.place_order(
                symbol=self.symbol, qty=qty_to_trade, side=-1, order_type=2, timestamp=timestamp,
                product_type=self.product_type, strategy_name=self.STRATEGY_NAME,
                entry_price=price, price=price
            )
            self.position = 'short'
            self.entry_price = price

    def _reset_day(self):
        self.fifteen_min_close_price = None
        self.trade_taken_today = False