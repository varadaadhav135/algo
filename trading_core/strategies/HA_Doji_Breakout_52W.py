from datetime import datetime
import math
from trading_core.strategies.base_strategy import Strategy

class HADojiBreakout52WStrategy(Strategy):
    """HA Doji breakout near 52W high with weekly RSI filter and SMA exit."""

    STRATEGY_NAME = "HA_Doji_Breakout_52W"

    def __init__(self, symbol, order_manager, trade_type="Intraday",
                 sizing_type="Percentage", sizing_value=10,
                 weeks_52=52, trading_days_per_week=5,
                 min_drop_pct=1.0, max_drop_pct=15.0,
                 ha_doji_body_to_range=0.15,
                 sl_pct=6.0,
                 sma_tf="D", sma_len=20,
                 rsi_tf="W", rsi_len=14,
                 rsi_thresh=50.0,
                 use_confirm_close=True):
        super().__init__(symbol, order_manager, trade_type, sizing_type, sizing_value)
        self.weeks_52 = weeks_52
        self.trading_days_per_week = trading_days_per_week
        self.lookback_bars = weeks_52 * trading_days_per_week
        self.min_drop_pct = min_drop_pct
        self.max_drop_pct = max_drop_pct
        self.ha_doji_body_to_range = ha_doji_body_to_range
        self.sl_pct = sl_pct
        self.sma_len = sma_len
        self.rsi_len = rsi_len
        self.rsi_thresh = rsi_thresh
        self.use_confirm_close = use_confirm_close

        # State variables
        self.ha_open_prev = None
        self.last_doji_high = None
        self.last_doji_index = None
        self.ha_open = None

        # Store recent bars data: list of dicts with keys: open, high, low, close, ha_close, ha_open, ha_high, ha_low
        self.bars = []

        # Store closing prices for 52-week high and daily SMA calculations
        self.close_prices = []

        # Store weekly RSI values (simplified placeholder, in practice requires external data)
        self.weekly_rsi = None

        self.entry_price = None
        self.stop_loss_price = None

    def _restore_state_from_position(self, position: dict):
        self.entry_price = position.get('entry_price')
        if self.entry_price:
            self.stop_loss_price = self.entry_price * (1 - self.sl_pct / 100.0)

    def on_tick(self, timestamp: datetime, data: dict):
        """
        data should contain keys for OHLC, e.g.:
          'open', 'high', 'low', 'close' for backtesting from candles
          'open_price', 'high_price', 'low_price', 'close_price' for live data
        """
        position_details = self.order_manager.get_open_position(self.symbol)
        is_my_trade = position_details and position_details.get('strategy') == self.STRATEGY_NAME
        current_qty = position_details.get('quantity', 0) if position_details else 0

        if position_details and not is_my_trade:
            return
            
        # Extract OHLC from data, supporting both live and backtest keys
        o = data.get('open', data.get('open_price'))
        h = data.get('high', data.get('high_price'))
        l = data.get('low', data.get('low_price'))
        c = data.get('close', data.get('close_price', data.get('ltp')))

        if any(v is None for v in [o, h, l, c]):
            # Not enough data to proceed
            return

        # Use 'c' (close or ltp) for quantity and position management
        price = c

        # Compute HA close
        ha_close = (o + h + l + c) / 4.0

        # Compute HA open
        if self.ha_open_prev is None:
            ha_open = (o + c) / 2.0
        else:
            ha_open = (self.ha_open_prev + self.bars[-1]['ha_close']) / 2.0

        ha_high = max(h, ha_open, ha_close)
        ha_low = min(l, ha_open, ha_close)
        ha_body = abs(ha_close - ha_open)
        ha_range = ha_high - ha_low

        # Store bar
        bar = {
            'open': o, 'high': h, 'low': l, 'close': c,
            'ha_close': ha_close, 'ha_open': ha_open,
            'ha_high': ha_high, 'ha_low': ha_low,
            'ha_body': ha_body, 'ha_range': ha_range
        }
        self.bars.append(bar)
        self.ha_open_prev = ha_open

        # Determine if current bar is HA Doji
        doji = ha_range > 0 and (ha_body <= self.ha_doji_body_to_range * ha_range)
        if doji:
            self.last_doji_high = ha_high
            self.last_doji_index = len(self.bars) - 1

        # Update close prices for 52-week high (daily assumed)
        self.close_prices.append(c)
        if len(self.close_prices) > self.lookback_bars:
            self.close_prices.pop(0)

        # Calculate 52-week high
        if len(self.close_prices) < self.lookback_bars:
            return  # wait for enough data
        highest_52w = max(self.close_prices)

        # Calculate drop percent from 52-week high
        drop_pct = (highest_52w - c) / highest_52w * 100.0

        # Check if price inside 1% - 15% drop range
        in_52w_range = self.min_drop_pct <= drop_pct <= self.max_drop_pct

        # Placeholder for weekly RSI calculation: assume RSI > rsi_thresh for simplicity
        rsi_ok = True  # Would need weekly data integration for real RSI

        # Breakout condition: price crosses stored last Doji high
        breakout_price_condition = False
        if self.last_doji_high is not None:
            if self.use_confirm_close:
                breakout_price_condition = c > self.last_doji_high
            else:
                breakout_price_condition = h > self.last_doji_high

        # Entry condition based on breakout, RSI, drop range, and flat position
        if (self.last_doji_high is not None and
            breakout_price_condition and
            in_52w_range and
            rsi_ok and current_qty == 0):

            qty = self._calculate_quantity(price)
            if qty > 0:
                self.order_manager.place_order(
                    symbol=self.symbol, qty=qty, side=1, order_type=2, timestamp=timestamp,
                    product_type=self.product_type, strategy_name=self.STRATEGY_NAME, price=price
                )
                self.entry_price = price
                self.stop_loss_price = self.entry_price * (1 - self.sl_pct / 100.0)

        # Manage stop loss exit
        if current_qty > 0:
            if self.stop_loss_price and l <= self.stop_loss_price:
                # On exit, we close the entire position.
                qty_to_exit = abs(current_qty)
                self.order_manager.place_order(
                    symbol=self.symbol, qty=qty_to_exit, side=-1, order_type=2, timestamp=timestamp,
                    product_type=self.product_type, strategy_name=self.STRATEGY_NAME,
                    entry_price=self.entry_price, exit_reason="Stop Loss", price=self.stop_loss_price
                )
                self._reset_position()

        # Exit condition: daily close below daily 20 SMA (not implemented here, requires daily SMA data input)
        # Could be integrated with external daily SMA updates

    def _reset_position(self):
        self.entry_price = None
        self.stop_loss_price = None
