from abc import ABC, abstractmethod
from datetime import datetime, timedelta
from trading_core.strategies.base_strategy import Strategy

class DailyBreakdownStrategy(Strategy):
    """Enter short if price breaks low of first qualifying 15-min candle (<1% move OR red candle >1%)."""
    
    STRATEGY_NAME = "DailyBreakdown"
    
    def __init__(self, symbol, order_manager, trade_type="Intraday",
                 sizing_type="Quantity", sizing_value=1):
        super().__init__(symbol, order_manager, trade_type,
                         sizing_type, sizing_value)
        # State for first qualifying candle
        self._first_candle_start = None
        self._first_candle_high = None
        self._first_candle_low = None
        self._first_candle_open = None
        self._first_candle_close = None
        self._breakdown_level = None
        self._qualification_date = None
        
        # Current candle aggregation
        self._current_candle_start = None
        self._current_candle_high = None
        self._current_candle_low = None
        self._current_candle_open = None
        
        # Trade management
        self._entry_price = None
        self._entry_date = None

    def _restore_state_from_position(self, position: dict):
        self.entry_price = position.get('entry_price')
        # Note: _entry_date is not persisted, will be None on restore.
        # This seems acceptable for the current logic.

    def on_tick(self, timestamp: datetime, data: dict):
        price = data.get('ltp', data.get('close'))

        if not price:
            return

        position_details = self.order_manager.get_open_position(self.symbol)
        is_my_trade = position_details and position_details.get('strategy') == self.STRATEGY_NAME
        current_qty = position_details.get('quantity', 0) if position_details else 0

        if position_details and not is_my_trade:
            return

        current_date = timestamp.date()
        
        # Start new current candle if needed
        if self._current_candle_start is None:
            # Round down to nearest 15-minute block
            minute = (timestamp.minute // 15) * 15
            self._current_candle_start = timestamp.replace(minute=minute, second=0, microsecond=0)
            self._current_candle_high = price
            self._current_candle_low = price
            self._current_candle_open = price
        
        # Check if we need to complete current candle and start new one
        current_candle_end = self._current_candle_start + timedelta(minutes=15)
        if timestamp >= current_candle_end:
            # Process completed candle before starting new one
            self._process_completed_candle(price)
            # Start new candle
            minute = (timestamp.minute // 15) * 15
            self._current_candle_start = timestamp.replace(minute=minute, second=0, microsecond=0)
            self._current_candle_high = price
            self._current_candle_low = price
            self._current_candle_open = price
        else:
            # Update current candle
            self._current_candle_high = max(self._current_candle_high, price)
            self._current_candle_low = min(self._current_candle_low, price)
        
        # Check for entry if we have a breakdown level and not entered
        if (self._breakdown_level is not None and 
            current_qty == 0 and
            self._qualification_date is not None):
            
            # Only trade on same day as qualification
            if current_date == self._qualification_date:
                if price < self._breakdown_level:
                    qty = self._calculate_quantity(price)
                    if qty > 0:
                        self.order_manager.place_order(
                            symbol=self.symbol, qty=qty, side=-1, order_type=2, timestamp=timestamp,
                            product_type=self.product_type, strategy_name=self.STRATEGY_NAME, price=price
                        )
                        self._entry_price = price
                        self._entry_date = current_date
        
        # Manage exit if entered
        if current_qty < 0 and self._entry_price:
            target = self._entry_price * 0.98  # 2% below selling price
            stop_loss = self._entry_price * 1.01  # 1% above selling price
            if price <= target or price >= stop_loss:
                qty_to_exit = abs(current_qty)
                # Exit short position (buy to cover)
                self.order_manager.place_order(
                    symbol=self.symbol, qty=qty_to_exit, side=1, order_type=2, timestamp=timestamp,
                    product_type=self.product_type, strategy_name=self.STRATEGY_NAME,
                    entry_price=self._entry_price, exit_reason="SL/TP Hit", price=price
                )
                # Reset trade state but keep breakdown level for rest of day
                self._entry_price = None
                self._entry_date = None
        
        # Reset breakdown level at end of trading day
        if (self._qualification_date is not None and 
            current_date > self._qualification_date):
            self._reset_qualification()
    
    def _process_completed_candle(self, current_price: float):
        """Process the completed 15-minute candle."""
        if (self._current_candle_high is None or 
            self._current_candle_low is None or
            self._current_candle_open is None):
            return
        
        current_candle_close = current_price
        
        # If we don't have a qualified first candle yet, check if this one qualifies
        if self._breakdown_level is None:
            # Check condition 1: Movement less than 1%
            move_pct = ((self._current_candle_high - self._current_candle_low) / 
                       self._current_candle_low * 100)
            
            # Check condition 2: Red candle with movement greater than 1%
            is_red_candle = current_candle_close < self._current_candle_open
            red_candle_move_pct = ((self._current_candle_open - current_candle_close) / 
                                  self._current_candle_open * 100) if self._current_candle_open > 0 else 0
            
            # Qualify if either condition is met
            condition1 = move_pct < 1  # Low movement
            condition2 = is_red_candle and red_candle_move_pct > 1  # Red candle with >1% drop
            
            if condition1 or condition2:
                # This candle qualifies as our first qualifying candle
                self._first_candle_start = self._current_candle_start
                self._first_candle_high = self._current_candle_high
                self._first_candle_low = self._current_candle_low
                self._first_candle_open = self._current_candle_open
                self._first_candle_close = current_candle_close
                self._breakdown_level = self._current_candle_low
                self._qualification_date = self._current_candle_start.date()
    
    def _reset_qualification(self):
        """Reset qualification state to look for new qualifying candle."""
        self._first_candle_start = None
        self._first_candle_high = None
        self._first_candle_low = None
        self._first_candle_open = None
        self._first_candle_close = None
        self._breakdown_level = None
        self._qualification_date = None
