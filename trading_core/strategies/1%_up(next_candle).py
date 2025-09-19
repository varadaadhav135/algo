from abc import abstractmethod
from datetime import datetime, timedelta
from trading_core.strategies.base_strategy import Strategy

class MomentumBreakoutStrategy(Strategy):
    """Enter long when price breaks above high of 1st 15-min candle if it moved >1%."""

    STRATEGY_NAME = "Momentum Breakout 15m"

    def __init__(self, symbol, order_manager, trade_type="Intraday",
                 sizing_type="Quantity", sizing_value=1):
        super().__init__(symbol, order_manager, trade_type,
                         sizing_type, sizing_value)
        self._current_day = None
        self._reset_day()

    def _reset_day(self):
        """Resets the strategy state for a new trading day."""
        # First 15-min candle tracking
        self._first_candle_open = None
        self._first_candle_high = None
        self._first_candle_low = None
        self._first_candle_close = None
        self._first_candle_complete = False
        # Trade state
        self._trade_taken_today = False
        self._entry_price = None
        self._target_price = None
        self._stop_price = None
        self._current_day = None

    def _restore_state_from_position(self, position: dict):
        self._entry_price = position.get('entry_price')
        if self._entry_price:
            self._target_price = self._entry_price * 1.02
            self._stop_price = self._entry_price * 0.99
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

        if self._current_day is None or timestamp.date() > self._current_day:
            self._reset_day()
            self._current_day = timestamp.date()

        # Initialize first candle
        if not self._first_candle_open:
            # Align to session start or first tick
            self._first_candle_open = price
            self._first_candle_high = price
            self._first_candle_low = price
            return

        # Build first 15-min candle
        candle_age = timestamp - timestamp.replace(minute=(timestamp.minute // 15)*15,
                                                  second=0, microsecond=0)
        if not self._first_candle_complete:
            # Update high/low
            self._first_candle_high = max(self._first_candle_high, price)
            self._first_candle_low = min(self._first_candle_low, price)
            # On close of first 15m
            if candle_age >= timedelta(minutes=15):
                self._first_candle_close = price
                self._first_candle_complete = True
                # Check >1% movement
                pct_move = abs(self._first_candle_high - self._first_candle_open) / self._first_candle_open
                if pct_move < 0.01:
                    # Cancel strategy if move <1%
                    self._first_candle_complete = False
                    self._first_candle_open = None
                return
            return

        # After first candle, look for breakout and manage trade
        if current_qty == 0 and not self._trade_taken_today:
            # Enter buy when price crosses above first candle high
            if price > self._first_candle_high:
                qty = self._calculate_quantity(price)
                if qty > 0:
                    self.order_manager.place_order(
                        symbol=self.symbol, qty=qty, side=1, order_type=2, timestamp=timestamp,
                        product_type=self.product_type, strategy_name=self.STRATEGY_NAME, price=price
                    )
                    self._entry_price = price
                    self._target_price = price * 1.02
                    self._stop_price = price * 0.99
                    self._trade_taken_today = True
        else:
            if current_qty > 0 and self._entry_price:
                # Manage existing trade
                should_exit, reason, exit_price = False, None, price
                if price >= self._target_price:
                    should_exit, reason, exit_price = True, "Target Hit", self._target_price
                elif price <= self._stop_price:
                    should_exit, reason, exit_price = True, "Stop Loss Hit", self._stop_price

                if should_exit:
                    qty_to_exit = abs(current_qty)
                    self.order_manager.place_order(
                        symbol=self.symbol, qty=qty_to_exit, side=-1, order_type=2, timestamp=timestamp,
                        product_type=self.product_type, strategy_name=self.STRATEGY_NAME,
                        entry_price=self._entry_price, exit_reason=reason, price=exit_price
                    )
                    self._reset_trade_state()

    def _reset_trade_state(self):
        """Reset state after exiting a trade."""
        self._entry_price = None
        self._target_price = None
        self._stop_price = None
