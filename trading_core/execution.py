# trading_bot/trading_core/execution.py
import logging

logger = logging.getLogger(__name__)


class OrderManager:
    """Manages order placement and logs detailed trade information."""

    def __init__(self, fyers_instance, log_callback=None):
        self.fyers = fyers_instance
        # This allows the engine to pass its logging function to the OrderManager
        self.log_callback = log_callback
        self.orders = {}

    def _log(self, message):
        """Logs a message using the provided callback, if available."""
        if self.log_callback:
            self.log_callback(message)
        else:
            # Fallback to console print if no callback is provided
            print(message)

    def place_order(self, symbol, qty, side, order_type, product_type="INTRADAY",
                    strategy_name=None, entry_price=None, exit_reason=None, price=None, **kwargs):
        trade_type = "BUY" if side == 1 else "SELL"
        price_value = price if price is not None else 'Market'

        # Build the detailed log message
        title = "--- TRADE EXIT ---" if exit_reason is not None else "--- TRADE ENTRY ---"
        log_message = f"{title}\n"
        log_message += f"  Timestamp: {kwargs.get('timestamp').strftime('%Y-%m-%d %H:%M:%S')}\n"
        log_message += f"  Symbol:    {symbol}\n"
        log_message += f"  Strategy:  {strategy_name or 'N/A'}\n"
        log_message += f"  Action:    {trade_type} @ {price_value}\n"
        log_message += f"  Quantity:  {qty}\n"

        # --- NEW: Calculate and log profit/loss on exit ---
        if exit_reason and entry_price and price:
            # Long position exits with a SELL (-1 side)
            if side == -1:
                pnl = (price - entry_price) * qty
            # Short position exits with a BUY (1 side)
            elif side == 1:
                pnl = (entry_price - price) * qty
            else:
                pnl = 0
            log_message += f"  P&L:     {pnl:.2f}\n"
            log_message += f"  Reason:  {exit_reason}\n"
        else:
            if exit_reason:
                log_message += f"  Reason:  {exit_reason}\n"
        # ----------------------------------------------------

        log_message += "--------------------"
        self._log(log_message)

        # --- The actual order placement logic (currently in mock mode) ---
        data = {
            "symbol": symbol, "qty": qty, "type": order_type,
            "side": side, "productType": product_type, "limitPrice": 0,
            "stopPrice": 0, "validity": "DAY", "disclosedQty": 0,
            "offlineOrder": False,
        }

        # To enable real trading, you would uncomment the following lines:
        # try:
        #     response = self.fyers.place_order(data=data)
        #     # ... handle response ...
        # except Exception as e:
        #     self._log(f"  ORDER FAILED: {e}")