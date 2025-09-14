from datetime import datetime, time

class NiftySMA921LongStrategy(Strategy):
    """Long when close > 9SMA and 21SMA; SL is entry candle low; exit at 15:15 or stop."""

    STRATEGY_NAME = "Nifty_9_21_SMA_Long"

    def __init__(self, symbol, order_manager, trade_type="Intraday",
                 sizing_type="Quantity", sizing_value=1,
                 sma9_len=9, sma21_len=21,
                 exit_hour=15, exit_min=15):
        super().__init__(symbol, order_manager, trade_type, sizing_type, sizing_value)
        self.sma9_len = sma9_len
        self.sma21_len = sma21_len
        self.exit_time = time(exit_hour, exit_min)
        self.prices = []
        self.low_prices = []
        self.in_position = False
        self.entry_price = None
        self.sl_price = None
        self.entry_time = None

    def _calc_sma(self, data, period):
        if len(data) < period:
            return None
        return sum(data[-period:]) / period

    def on_tick(self, timestamp: datetime, price: float):
        self.prices.append(price)
        self.low_prices.append(price)  # For each tick, treat price as low

        current_time = timestamp.time()

        sma9 = self._calc_sma(self.prices, self.sma9_len)
        sma21 = self._calc_sma(self.prices, self.sma21_len)

        # Entry condition: close > both SMAs, flat position
        if not self.in_position and sma9 and sma21:
            if price > sma9 and price > sma21:
                qty = self._calculate_quantity(price)
                if qty > 0:
                    self.order_manager.buy(self.symbol, qty, price, self.product_type)
                    self.in_position = True
                    self.entry_price = price
                    self.sl_price = min(self.low_prices[-1], price)  # Low of entry candle
                    self.entry_time = timestamp

        # Stop-loss: position exists, stop is set, and price <= SL
        if self.in_position and self.sl_price:
            if price <= self.sl_price:
                qty = self._calculate_quantity(self.entry_price)
                self.order_manager.sell(self.symbol, qty, price, self.product_type)
                self._reset_position()

        # EOD exit at specified time
        if self.in_position and current_time >= self.exit_time:
            qty = self._calculate_quantity(self.entry_price)
            self.order_manager.sell(self.symbol, qty, price, self.product_type)
            self._reset_position()

    def _reset_position(self):
        self.in_position = False
        self.entry_price = None
        self.sl_price = None
        self.entry_time = None
