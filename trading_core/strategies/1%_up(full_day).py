from datetime import datetime, timedelta
from trading_core.strategies.base_strategy import Strategy

class DailyBreakoutStrategy(Strategy):
    """Enter long if price crosses high of the first 15-min candle given >1% move anytime in the day."""

    STRATEGY_NAME = "DailyBreakout"

    def __init__(self, symbol, order_manager, trade_type="Intraday",
                 sizing_type="Quantity", sizing_value=1):
        super().__init__(symbol, order_manager, trade_type,
                         sizing_type, sizing_value)
        self._first_candle_start = None
        self._first_high = None
        self._first_low = None
        self._trade_taken_today = False
        self._entry_price = None
        self._current_day = None

    def _restore_state_from_position(self, position: dict):
        self.entry_price = position.get('entry_price')
        self._trade_taken_today = True

    def on_tick(self, timestamp: datetime, data: dict):
        price = data.get('ltp', data.get('close'))

        if not price:
            return

        position_details = self.order_manager.get_open_position(self.symbol)
        is_my_trade = position_details and position_details.get('strategy') == self.STRATEGY_NAME
        current_qty = position_details.get('quantity', 0) if position_details else 0

        if position_details and not is_my_trade:
            return

        # Reset state on new trading day
        if self._current_day is None or timestamp.date() != self._current_day:
            self._reset_day(timestamp, price)

        # Aggregate first 15-min candle
        first_end = self._first_candle_start + timedelta(minutes=15)
        if timestamp < first_end:
            self._first_high = max(self._first_high, price)
            self._first_low = min(self._first_low, price)
            return

        move_pct = (self._first_high - self._first_low) / self._first_low * 100
        first_move_ok = move_pct > 1

        # If not in a trade and haven't traded today, check for entry
        if first_move_ok and current_qty == 0 and not self._trade_taken_today:
            if price > self._first_high:
                qty = self._calculate_quantity(price)
                if qty > 0:
                    self.order_manager.place_order(
                        symbol=self.symbol, qty=qty, side=1, order_type=2, timestamp=timestamp,
                        product_type=self.product_type, strategy_name=self.STRATEGY_NAME, price=price
                    )
                    self._entry_price = price
                    self._trade_taken_today = True
            return

        # Manage exit if entered
        if current_qty > 0 and self._entry_price:
            target = self._entry_price * 1.02
            stop_loss = self._entry_price * 0.99
            if price >= target or price <= stop_loss:
                qty_to_exit = abs(current_qty)
                self.order_manager.place_order(
                    symbol=self.symbol, qty=qty_to_exit, side=-1, order_type=2, timestamp=timestamp,
                    product_type=self.product_type, strategy_name=self.STRATEGY_NAME,
                    entry_price=self._entry_price, exit_reason="SL/TP Hit", price=price
                )
                self._reset_trade_state()
            return

    def _reset_trade_state(self):
        self._entry_price = None

    def _reset_day(self, timestamp: datetime, price: float):
        """Initialize first candle and reset flags for a new trading day."""
        minute = (timestamp.minute // 15) * 15
        self._first_candle_start = timestamp.replace(minute=minute, second=0, microsecond=0)
        self._first_high = price
        self._first_low = price
        self._trade_taken_today = False
        self._entry_price = None
        self._current_day = timestamp.date()
