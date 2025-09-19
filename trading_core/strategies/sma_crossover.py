from datetime import datetime
from trading_core.strategies.base_strategy import Strategy


class SMACrossoverStrategy(Strategy):
    STRATEGY_NAME = "SMA Crossover"

    def __init__(self, symbol, order_manager, trade_type="Intraday",
                 sizing_type="Quantity", sizing_value=1,
                 short_window=5, long_window=20):
        super().__init__(symbol, order_manager, trade_type, sizing_type, sizing_value)
        self.short_window = short_window
        self.long_window = long_window
        self.prices = []
        self.short_sma = None
        self.long_sma = None
        self.entry_price = None

    def _restore_state_from_position(self, position: dict):
        self.entry_price = position.get('entry_price')

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
        if len(self.prices) < self.long_window:
            return

        short_prices = self.prices[-self.short_window:]
        long_prices = self.prices[-self.long_window:]

        prev_short_sma = self.short_sma
        prev_long_sma = self.long_sma
        self.short_sma = sum(short_prices) / self.short_window
        self.long_sma = sum(long_prices) / self.long_window

        if prev_short_sma is None:
            return

        golden_cross = prev_short_sma <= prev_long_sma and self.short_sma > self.long_sma
        death_cross = prev_short_sma >= prev_long_sma and self.short_sma < self.long_sma

        if current_qty > 0 and death_cross:
            qty_to_exit = abs(current_qty)
            self.order_manager.place_order(
                symbol=self.symbol, qty=qty_to_exit, side=-1, order_type=2, timestamp=timestamp,
                product_type=self.product_type, strategy_name=self.STRATEGY_NAME,
                entry_price=self.entry_price, exit_reason="SMA Crossover", price=price
            )
            self.entry_price = None
            return

        if current_qty < 0 and golden_cross:
            qty_to_exit = abs(current_qty)
            self.order_manager.place_order(
                symbol=self.symbol, qty=qty_to_exit, side=1, order_type=2, timestamp=timestamp,
                product_type=self.product_type, strategy_name=self.STRATEGY_NAME,
                entry_price=self.entry_price, exit_reason="SMA Crossover", price=price
            )
            self.entry_price = None
            return

        if current_qty == 0:
            qty_to_trade = self._calculate_quantity(price)
            if qty_to_trade <= 0: return
            if golden_cross:
                self.order_manager.place_order(
                    symbol=self.symbol, qty=qty_to_trade, side=1, order_type=2, timestamp=timestamp,
                    product_type=self.product_type, strategy_name=self.STRATEGY_NAME,
                    price=price
                )
                self.entry_price = price
            elif death_cross:
                self.order_manager.place_order(
                    symbol=self.symbol, qty=qty_to_trade, side=-1, order_type=2, timestamp=timestamp,
                    product_type=self.product_type, strategy_name=self.STRATEGY_NAME,
                    price=price
                )
                self.entry_price = price