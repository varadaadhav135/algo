from datetime import datetime, timedelta
from trading_core.strategies.base_strategy import Strategy

class NiftySwingBreakoutTrendStrategy(Strategy):
    """Swing breakout with daily trend filter, risk management: 1:2 SL-TP."""

    STRATEGY_NAME = "Nifty_Swing_Breakout_Trend"

    def __init__(self, symbol, order_manager, trade_type="Intraday",
                 sizing_type="Quantity", sizing_value=1,
                 daily_sma_length=20, swing_length=5):
        super().__init__(symbol, order_manager, trade_type, sizing_type, sizing_value)
        self.daily_sma_length = daily_sma_length
        self.swing_length = swing_length

        # Store historical daily closes for daily SMA
        self.daily_closes = []

        # Store intraday bars to identify swings
        # Each bar: dict with keys 'high', 'low', 'close', 'timestamp'
        self.bars = []

        # Trade state
        self.entry_price = None
        self.sl = None
        self.tp = None

    def _restore_state_from_position(self, position: dict):
        self.entry_price = position.get('entry_price')
        # Note: SL/TP are not restored, they will be recalculated on the next tick.
        # This is a limitation if the swing points are not available immediately on restart.

    def on_tick(self, timestamp: datetime, data: dict):
        price = data.get('ltp', data.get('close'))
        if not price:
            return

        position_details = self.order_manager.get_open_position(self.symbol)
        is_my_trade = position_details and position_details.get('strategy') == self.STRATEGY_NAME
        current_qty = position_details.get('quantity', 0) if position_details else 0

        if position_details and not is_my_trade:
            return

        # For simplicity, assume one tick per bar close
        # Append tick close to bars list; in real scenarios aggregate bars externally
        bar_data = {
            'high': data.get('high', price),
            'low': data.get('low', price),
            'close': price, 'timestamp': timestamp
        }
        self.bars.append(bar_data)

        # Update daily close list at day boundaries
        if not self.daily_closes or self.daily_closes[-1][0].date() != timestamp.date():
            # new day
            self.daily_closes.append((timestamp, price))
        else:
            self.daily_closes[-1] = (timestamp, price)
        # Calculate daily SMA on close prices
        close_prices = [c[1] for c in self.daily_closes[-self.daily_sma_length:]]
        if len(close_prices) < self.daily_sma_length:
            return  # Wait for enough data

        daily_sma = sum(close_prices) / len(close_prices)
        daily_close = close_prices[-1]

        trend_long = daily_close > daily_sma
        trend_short = daily_close < daily_sma

        # Proceed to check swing points
        swing_high = self._get_pivot_high()
        swing_low = self._get_pivot_low()

        # Entry logic
        if current_qty == 0:
            if trend_long and swing_high is not None and price > swing_high['value']:
                # Long entry
                qty = self._calculate_quantity(price)
                if qty > 0:
                    self.order_manager.place_order(
                        symbol=self.symbol, qty=qty, side=1, order_type=2, timestamp=timestamp,
                        product_type=self.product_type, strategy_name=self.STRATEGY_NAME, price=price
                    )
                    self.entry_price = price
                    self.sl = swing_high['low']
                    self.tp = price + (price - self.sl) * 2
            elif trend_short and swing_low is not None and price < swing_low['value']:
                qty = self._calculate_quantity(price)
                if qty > 0:
                    self.order_manager.place_order(
                        symbol=self.symbol, qty=qty, side=-1, order_type=2, timestamp=timestamp,
                        product_type=self.product_type, strategy_name=self.STRATEGY_NAME, price=price
                    )
                    self.entry_price = price
                    self.sl = swing_low['high']
                    self.tp = price - (self.sl - price) * 2

        # Manage existing position exits with SL and TP
        if current_qty != 0:
            if current_qty > 0:  # Long position
                if price <= self.sl or price >= self.tp:
                    qty_to_exit = abs(current_qty)
                    self.order_manager.place_order(
                        symbol=self.symbol, qty=qty_to_exit, side=-1, order_type=2, timestamp=timestamp,
                        product_type=self.product_type, strategy_name=self.STRATEGY_NAME,
                        entry_price=self.entry_price, exit_reason="SL/TP Hit", price=price
                    )
                    self._reset_trade()
            elif current_qty < 0:  # Short position
                if price >= self.sl or price <= self.tp:
                    qty_to_exit = abs(current_qty)
                    self.order_manager.place_order(
                        symbol=self.symbol, qty=qty_to_exit, side=1, order_type=2, timestamp=timestamp,
                        product_type=self.product_type, strategy_name=self.STRATEGY_NAME,
                        entry_price=self.entry_price, exit_reason="SL/TP Hit", price=price
                    )
                    self._reset_trade()

    def _reset_trade(self):
        self.entry_price = None
        self.sl = None
        self.tp = None

    def _get_pivot_high(self):
        """Return dict of pivot high {'index', 'value', 'low'} if found, else None."""
        count = self.swing_length
        bars = self.bars
        if len(bars) < 2 * count + 1:
            return None
        for i in range(count, len(bars) - count):
            center = bars[i]['high']
            if all(center > bars[j]['high'] for j in range(i - count, i)) and \
               all(center > bars[j]['high'] for j in range(i + 1, i + count + 1)):
                return {
                    'index': i,
                    'value': center,
                    'low': bars[i]['low']
                }
        return None

    def _get_pivot_low(self):
        """Return dict of pivot low {'index', 'value', 'high'} if found, else None."""
        count = self.swing_length
        bars = self.bars
        if len(bars) < 2 * count + 1:
            return None
        for i in range(count, len(bars) - count):
            center = bars[i]['low']
            if all(center < bars[j]['low'] for j in range(i - count, i)) and \
               all(center < bars[j]['low'] for j in range(i + 1, i + count + 1)):
                return {
                    'index': i,
                    'value': center,
                    'high': bars[i]['high']
                }
        return None
