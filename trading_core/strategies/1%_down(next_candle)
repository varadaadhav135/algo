from abc import ABC, abstractmethod
from datetime import datetime, timedelta

class FifteenMinBreakdownStrategy(Strategy):
    """Enter short if 2nd 15-min candle breaks low of 1st 15-min candle given <1% move."""
    
    STRATEGY_NAME = "15MinBreakdown"
    
    def __init__(self, symbol, order_manager, trade_type="Intraday",
                 sizing_type="Quantity", sizing_value=1):
        super().__init__(symbol, order_manager, trade_type,
                         sizing_type, sizing_value)
        # State for candle aggregation
        self._first_candle_start = None
        self._first_candle_high = None
        self._first_candle_low = None
        self._first_candle_close = None
        self._second_candle_start = None
        self._entered = False
        self._entry_price = None
    
    def on_tick(self, timestamp: datetime, price: float):
        # Initialize first candle
        if self._first_candle_start is None:
            # Round down to nearest 15-minute block
            minute = (timestamp.minute // 15) * 15
            self._first_candle_start = timestamp.replace(minute=minute, second=0, microsecond=0)
            self._first_candle_high = price
            self._first_candle_low = price
            self._first_candle_close = price
            return
        
        # Update first 15-min candle until 15 minutes have passed
        first_end = self._first_candle_start + timedelta(minutes=15)
        if timestamp < first_end:
            self._first_candle_high = max(self._first_candle_high, price)
            self._first_candle_low = min(self._first_candle_low, price)
            self._first_candle_close = price
            return
        
        # After first 15-min block completes, check movement
        if self._second_candle_start is None:
            move_pct = (self._first_candle_high - self._first_candle_low) / self._first_candle_low * 100
            if move_pct >= 1:
                # Reset to next block if movement is too high (>=1%)
                self._reset_candles(timestamp)
                return
            # Start second candle aggregation
            self._second_candle_start = first_end
            self._second_candle_high = price
            self._second_candle_low = price
            self._second_candle_close = price
            return
        
        # Update second 15-min candle until it completes or entry triggers
        second_end = self._second_candle_start + timedelta(minutes=15)
        if timestamp < second_end and not self._entered:
            self._second_candle_high = max(self._second_candle_high, price)
            self._second_candle_low = min(self._second_candle_low, price)
            self._second_candle_close = price
            # Check breakdown below first low
            if price < self._first_candle_low:
                qty = self._calculate_quantity(price)
                if qty > 0:
                    self.order_manager.sell(self.symbol, qty, price, self.product_type)
                    self._entered = True
                    self._entry_price = price
            return
        
        # Manage exit if entered
        if self._entered:
            target = self._entry_price * 0.98  # 2% below selling price
            stop_loss = self._entry_price * 1.01  # 1% above selling price
            if price <= target or price >= stop_loss:
                qty = self._calculate_quantity(price)
                # Exit entire position (buy to cover short)
                self.order_manager.buy(self.symbol, qty, price, self.product_type)
                # Reset for next setup
                self._reset_candles(timestamp)
            return
        
        # If second candle completes without entry, reset to next two candles
        if timestamp >= second_end:
            self._reset_candles(timestamp)
    
    def _reset_candles(self, timestamp: datetime):
        """Reset state to begin new first 15-min candle at current timestamp."""
        self._first_candle_start = None
        self._first_candle_high = None
        self._first_candle_low = None
        self._first_candle_close = None
        self._second_candle_start = None
        self._entered = False
        self._entry_price = None
        # Re-process this tick as start of new first candle
        if hasattr(self, '_second_candle_close') and self._second_candle_close:
            self.on_tick(timestamp, self._second_candle_close)

