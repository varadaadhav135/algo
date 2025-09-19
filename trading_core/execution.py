# trading_bot/trading_core/execution.py
import logging
import json
import os
from datetime import datetime

logger = logging.getLogger(__name__)


class OrderManager:
    """Manages order placement, logs trade info, and persists positions."""

    def __init__(self, fyers_instance, log_callback=None, positions_file='positions.json', trade_history_file='trade_history.json'):
        self.fyers = fyers_instance
        # This allows the engine to pass its logging function to the OrderManager
        self.log_callback = log_callback
        self.positions_file = positions_file
        self.positions = self._load_positions()  # Tracks position qty: {'SYMBOL': qty}
        self.trade_history_file = trade_history_file

    def _load_positions(self):
        """Loads positions from the JSON file."""
        if os.path.exists(self.positions_file):
            try:
                with open(self.positions_file, 'r') as f:
                    positions = json.load(f)
                    self._log(f"Loaded {len(positions)} open positions from {self.positions_file}")
                    return positions
            except (json.JSONDecodeError, IOError) as e:
                self._log(f"Error loading positions file {self.positions_file}: {e}. Starting with empty positions.")
                return {}
        self._log("No positions file found. Starting with empty positions.")
        return {}

    def _save_positions(self):
        """Saves the current positions to the JSON file."""
        try:
            with open(self.positions_file, 'w') as f:
                json.dump(self.positions, f, indent=4)
        except IOError as e:
            self._log(f"Error saving positions to {self.positions_file}: {e}")

    def _log_trade(self, trade_details):
        """Appends a trade to the trade history file."""
        history = []
        if os.path.exists(self.trade_history_file):
            try:
                with open(self.trade_history_file, 'r') as f:
                    content = f.read()
                    if content:
                        history = json.loads(content)
            except (json.JSONDecodeError, IOError) as e:
                self._log(f"Could not read trade history file {self.trade_history_file}: {e}. Starting new history.")
                history = []

        history.append(trade_details)
        try:
            with open(self.trade_history_file, 'w') as f:
                json.dump(history, f, indent=4)
        except IOError as e:
            self._log(f"Error saving trade history to {self.trade_history_file}: {e}")

    def _log(self, message):
        """Logs a message using the provided callback, if available."""
        if self.log_callback:
            self.log_callback(message)
        else:
            # Fallback to console print if no callback is provided
            print(message)

    def get_position(self, symbol: str) -> int:
        """Returns the current position quantity for a symbol."""
        position = self.positions.get(symbol)
        return position.get('quantity', 0) if position else 0

    def get_open_position(self, symbol: str) -> dict | None:
        """Returns the full position details for a symbol, if one exists."""
        return self.positions.get(symbol)

    def place_order(self, symbol, qty, side, order_type, product_type="INTRADAY",
                    strategy_name=None, entry_price=None, exit_reason=None, price=None, **kwargs):
        trade_type = "BUY" if side == 1 else "SELL"
        price_value = price if price is not None else 'Market'

        # Build the detailed log message
        title = "--- TRADE EXIT ---" if exit_reason is not None else "--- TRADE ENTRY ---"
        timestamp = kwargs.get('timestamp')
        log_message = f"{title}\n"
        log_message += f"  Timestamp: {timestamp.strftime('%Y-%m-%d %H:%M:%S') if timestamp else 'N/A'}\n"
        log_message += f"  Symbol:    {symbol}\n"
        log_message += f"  Strategy:  {strategy_name or 'N/A'}\n"
        log_message += f"  Action:    {trade_type} @ {price_value}\n"
        log_message += f"  Quantity:  {qty}\n"

        pnl = 0
        # --- NEW: Calculate and log profit/loss on exit ---
        if exit_reason and entry_price and price:
            # Long position exits with a SELL (-1 side)
            if side == -1:
                pnl = (price - entry_price) * qty
            # Short position exits with a BUY (1 side)
            elif side == 1:
                pnl = (entry_price - price) * qty
            log_message += f"  P&L:     {pnl:.2f}\n"
            log_message += f"  Reason:  {exit_reason}\n"
        else:
            if exit_reason:
                log_message += f"  Reason:  {exit_reason}\n"
        # ----------------------------------------------------

        trade_record = {
            "timestamp": timestamp.isoformat() if timestamp else datetime.now().isoformat(),
            "symbol": symbol, "strategy": strategy_name or 'N/A', "action": trade_type,
            "price": price, "quantity": qty, "pnl": round(pnl, 2),
            "reason": exit_reason or "Entry"
        }
        self._log_trade(trade_record)

        # --- Update position state ---
        current_position_details = self.get_open_position(symbol)
        current_qty = self.get_position(symbol)
        new_qty = current_qty + (qty * side)

        if new_qty == 0:
            if symbol in self.positions:
                del self.positions[symbol]
        else:
            if not current_position_details:
                # New position. The `price` parameter is the execution price.
                self.positions[symbol] = {
                    'quantity': new_qty, 'strategy': strategy_name, 'entry_price': price,
                }
            else:
                self.positions[symbol]['quantity'] = new_qty
        self._save_positions()  # Save after every change
        log_message += f"\n  Position Change: {symbol} from {current_qty} to {new_qty}"
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