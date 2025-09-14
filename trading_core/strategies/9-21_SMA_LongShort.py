from datetime import datetime, time

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
        self.in_position = False
        self.position_side = None  # "long" or "short"
        self.entry_price = None
        self.sl_price_long = None
        self.sl_price_short = None
        self.entry_time = None

    def _calc_sma(self, data, period):
        if len(data) < period:
            return None
        return sum(data[-period:]) / period

    def on_tick(self, timestamp: datetime, price: float):
        self.prices.append(price)
        self.lows.append(price)
        self.highs.append(price)

        current_time = timestamp.time()

        sma9 = self._calc_sma(self.prices, self.sma9_len)
        sma21 = self._calc_sma(self.prices, self.sma21_len)

        # Check if no open position: decide entry
        if not self.in_position and sma9 and sma21:
            # Long condition: close > both SMAs
            if price > sma9 and price > sma21:
                qty = self._calculate_quantity(price)
                if qty > 0:
                    self.order_manager.buy(self.symbol, qty, price, self.product_type)
                    self.in_position = True
                    self.position_side = "long"
                    self.entry_price = price
                    self.sl_price_long = min(self.lows[-1], price)
                    self.entry_time = timestamp
            # Short condition: close < both SMAs
            elif price < sma9 and price < sma21:
                qty = self._calculate_quantity(price)
                if qty > 0:
                    self.order_manager.sell(self.symbol, qty, price, self.product_type)
                    self.in_position = True
                    self.position_side = "short"
                    self.entry_price = price
                    self.sl_price_short = max(self.highs[-1], price)
                    self.entry_time = timestamp

        # Stop loss and exit management for long position
        if self.in_position and self.position_side == "long" and self.sl_price_long:
            if price <= self.sl_price_long:
                qty = self._calculate_quantity(self.entry_price)
                self.order_manager.sell(self.symbol, qty, price, self.product_type)
                self._reset_position()
            elif current_time >= self.exit_time_long:
                qty = self._calculate_quantity(self.entry_price)
                self.order_manager.sell(self.symbol, qty, price, self.product_type)
                self._reset_position()

        # Stop loss and exit management for short position
        if self.in_position and self.position_side == "short" and self.sl_price_short:
            if price >= self.sl_price_short:
                qty = self._calculate_quantity(self.entry_price)
                self.order_manager.buy(self.symbol, qty, price, self.product_type)
                self._reset_position()
            elif current_time >= self.exit_time_short:
                qty = self._calculate_quantity(self.entry_price)
                self.order_manager.buy(self.symbol, qty, price, self.product_type)
                self._reset_position()

    def _reset_position(self):
        self.in_position = False
        self.position_side = None
        self.entry_price = None
        self.sl_price_long = None
        self.sl_price_short = None
        self.entry_time = None
