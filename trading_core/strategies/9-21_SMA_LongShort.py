from datetime import datetime, time
from trading_core.strategies.base_strategy import Strategy

class NiftySMA921LongShortStrategy(Strategy):
    """Long and Short using 9 & 21 SMA crossover with stop loss and timed exits."""

    STRATEGY_NAME = "Nifty_9_21_SMA_LongShort"

    def __init__(self, symbol, order_manager, trade_type="Intraday",
                 sizing_type="Quantity", sizing_value=1,
                 sma9_len=9, sma21_len=21,
                 exit_hour_long=15, exit_min_long=15,
                 exit_hour_short=15, exit_min_short=0):
        super().__init__(symbol, order_manager, trade_type, sizing_type, sizing_value)
        self.sma9_len = sma9_len
        self.sma21_len = sma21_len
        self.exit_time_long = time(exit_hour_long, exit_min_long)
        self.exit_time_short = time(exit_hour_short, exit_min_short)
        self.prices = []
        self.lows = []
        self.highs = []
        self.entry_price = None
        self.sl_price_long = None
        self.sl_price_short = None
        self.entry_time = None

    def _restore_state_from_position(self, position: dict):
        self.entry_price = position.get('entry_price')

    def _calc_sma(self, data, period):
        if len(data) < period:
            return None
        return sum(data[-period:]) / period

    def on_tick(self, timestamp: datetime, data: dict):
        price = data.get('ltp', data.get('close'))

        if not price:
            return

        position_details = self.order_manager.get_open_position(self.symbol)
        is_my_trade = position_details and position_details.get('strategy') == self.STRATEGY_NAME
        current_qty = position_details.get('quantity', 0) if position_details else 0

        if position_details and not is_my_trade:
            return

        self.prices.append(price)
        self.lows.append(price)
        self.highs.append(price)

        current_time = timestamp.time()

        sma9 = self._calc_sma(self.prices, self.sma9_len)
        sma21 = self._calc_sma(self.prices, self.sma21_len)

        # Check if no open position: decide entry
        if current_qty == 0 and sma9 and sma21:
            # Long condition: close > both SMAs
            if price > sma9 and price > sma21:
                qty = self._calculate_quantity(price)
                if qty > 0:
                    self.order_manager.place_order(
                        symbol=self.symbol, qty=qty, side=1, order_type=2, timestamp=timestamp,
                        product_type=self.product_type, strategy_name=self.STRATEGY_NAME, price=price
                    )
                    self.entry_price = price
                    self.sl_price_long = min(self.lows[-1], price)
                    self.entry_time = timestamp
            # Short condition: close < both SMAs
            elif price < sma9 and price < sma21:
                qty = self._calculate_quantity(price)
                if qty > 0:
                    self.order_manager.place_order(
                        symbol=self.symbol, qty=qty, side=-1, order_type=2, timestamp=timestamp,
                        product_type=self.product_type, strategy_name=self.STRATEGY_NAME, price=price
                    )
                    self.entry_price = price
                    self.sl_price_short = max(self.highs[-1], price)
                    self.entry_time = timestamp

        # Stop loss and exit management for long position
        if current_qty > 0 and self.sl_price_long:
            if price <= self.sl_price_long:
                qty_to_exit = abs(current_qty)
                self.order_manager.place_order(
                    symbol=self.symbol, qty=qty_to_exit, side=-1, order_type=2, timestamp=timestamp,
                    product_type=self.product_type, strategy_name=self.STRATEGY_NAME,
                    entry_price=self.entry_price, exit_reason="Stop Loss", price=price
                )
                self._reset_position()
            elif current_time >= self.exit_time_long:
                qty_to_exit = abs(current_qty)
                self.order_manager.place_order(
                    symbol=self.symbol, qty=qty_to_exit, side=-1, order_type=2, timestamp=timestamp,
                    product_type=self.product_type, strategy_name=self.STRATEGY_NAME,
                    entry_price=self.entry_price, exit_reason="EOD Exit", price=price
                )
                self._reset_position()

        # Stop loss and exit management for short position
        if current_qty < 0 and self.sl_price_short:
            if price >= self.sl_price_short:
                qty_to_exit = abs(current_qty)
                self.order_manager.place_order(
                    symbol=self.symbol, qty=qty_to_exit, side=1, order_type=2, timestamp=timestamp,
                    product_type=self.product_type, strategy_name=self.STRATEGY_NAME,
                    entry_price=self.entry_price, exit_reason="Stop Loss", price=price
                )
                self._reset_position()
            elif current_time >= self.exit_time_short:
                qty_to_exit = abs(current_qty)
                self.order_manager.place_order(
                    symbol=self.symbol, qty=qty_to_exit, side=1, order_type=2, timestamp=timestamp,
                    product_type=self.product_type, strategy_name=self.STRATEGY_NAME,
                    entry_price=self.entry_price, exit_reason="EOD Exit", price=price
                )
                self._reset_position()

    def _reset_position(self):
        self.entry_price = None
        self.sl_price_long = None
        self.sl_price_short = None
        self.entry_time = None
