from abc import abstractmethod
from datetime import datetime, timedelta

class MomentumBreakoutStrategy(Strategy):
    """Enter long when price breaks above high of 1st 15-min candle if it moved >1%."""

    STRATEGY_NAME = "Momentum Breakout 15m"

    def __init__(self, symbol, order_manager, trade_type="Intraday",
                 sizing_type="Quantity", sizing_value=1):
        super().__init__(symbol, order_manager, trade_type,
                         sizing_type, sizing_value)
        # First 15-min candle tracking
        self._first_candle_open = None
        self._first_candle_high = None
        self._first_candle_low = None
        self._first_candle_close = None
        self._first_candle_complete = False

        # Trade state
        self._in_trade = False
        self._entry_price = None
        self._target_price = None
        self._stop_price = None

    def on_tick(self, timestamp: datetime, price: float):
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
        if not self._in_trade:
            # Enter buy when price crosses above first candle high
            if price > self._first_candle_high:
                qty = self._calculate_quantity(price)
                if qty > 0:
                    order = self.order_manager.place_limit_buy(
                        symbol=self.symbol,
                        quantity=qty,
                        price=price,
                        product_type=self.product_type
                    )
                    self._in_trade = True
                    self._entry_price = price
                    self._target_price = price * 1.02
                    self._stop_price = price * 0.99
        else:
            # Manage existing trade
            if price >= self._target_price:
                # Exit at target
                self.order_manager.place_limit_sell(
                    symbol=self.symbol,
                    quantity=self.order_manager.get_position(self.symbol),
                    price=self._target_price,
                    product_type=self.product_type
                )
                self._reset()
            elif price <= self._stop_price:
                # Exit at stop loss
                self.order_manager.place_market_sell(
                    symbol=self.symbol,
                    quantity=self.order_manager.get_position(self.symbol),
                    product_type=self.product_type
                )
                self._reset()

    def _reset(self):
        """Reset state after exiting a trade."""
        self._in_trade = False
        self._entry_price = None
        self._target_price = None
        self._stop_price = None
        # Do not re-init first candle; one trade per day

