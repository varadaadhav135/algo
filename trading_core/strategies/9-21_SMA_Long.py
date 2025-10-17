from datetime import datetime, time
from trading_core.strategies.base_strategy import Strategy

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
        self.entry_price = None
        self.sl_price = None
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
        self.low_prices.append(price)  # For each tick, treat price as low

        current_time = timestamp.time()

        # EOD exit at specified time
        if current_qty > 0 and current_time >= self.exit_time:
            qty_to_exit = abs(current_qty)
            self.order_manager.place_order(
                symbol=self.symbol, qty=qty_to_exit, side=-1, order_type=2, timestamp=timestamp,
                product_type=self.product_type, strategy_name=self.STRATEGY_NAME,
                entry_price=self.entry_price, exit_reason="EOD Exit", price=price
            )
            self._reset_position()
            return

        sma9 = self._calc_sma(self.prices, self.sma9_len)
        sma21 = self._calc_sma(self.prices, self.sma21_len)

        # Entry condition: close > both SMAs, flat position
        if current_qty == 0 and sma9 and sma21:
            if price > sma9 and price > sma21:
                qty = self._calculate_quantity(price)
                if qty > 0:
                    self.order_manager.place_order(
                        symbol=self.symbol, qty=qty, side=1, order_type=2, timestamp=timestamp,
                        product_type=self.product_type, strategy_name=self.STRATEGY_NAME, price=price
                    )
                    self.entry_price = price
                    self.sl_price = min(self.low_prices[-1], price)  # Low of entry candle
                    self.entry_time = timestamp

        # Stop-loss: position exists, stop is set, and price <= SL
        if current_qty > 0 and self.sl_price:
            if price <= self.sl_price:
                qty_to_exit = abs(current_qty)
                self.order_manager.place_order(
                    symbol=self.symbol, qty=qty_to_exit, side=-1, order_type=2, timestamp=timestamp,
                    product_type=self.product_type, strategy_name=self.STRATEGY_NAME,
                    entry_price=self.entry_price, exit_reason="Stop Loss", price=price
                )
                self._reset_position()

    def _reset_position(self):
        self.entry_price = None
        self.sl_price = None
        self.entry_time = None
