# trading_bot/trading_core/data_handler.py
import pandas as pd
from datetime import datetime, timedelta
from concurrent.futures import ThreadPoolExecutor


class LiveDataHandler:
    """Processes live ticks from the WebSocket using a thread pool for efficiency."""

    def __init__(self, active_strategies, log_queue=None):
        self.active_strategies = active_strategies
        self.log_queue = log_queue
        # Using a thread pool to process ticks concurrently
        self.executor = ThreadPoolExecutor(max_workers=10, thread_name_prefix='TickWorker')

    def _log(self, message):
        if self.log_queue:
            self.log_queue.put(f"[{datetime.now().strftime('%H:%M:%S')}] [Data] {message}\n")

    def on_message(self, msg, timestamp=None):
        """Offloads the actual processing to a worker thread to keep the WS receiver responsive."""
        self.executor.submit(self._process_tick, msg, timestamp)

    def _process_tick(self, msg, timestamp=None):
        """The core logic to process a single tick message."""
        try:
            symbol = msg.get('symbol')
            # Check for live price ('ltp') or historical price ('close')
            price = msg.get("ltp") or msg.get("close")
            if symbol and symbol in self.active_strategies and price is not None:
                strategy = self.active_strategies[symbol]
                # Pass the provided timestamp, or the current time for live trading
                tick_timestamp = timestamp or datetime.now()
                strategy.on_tick(tick_timestamp, msg)
        except Exception as e:
            self._log(f"Error processing tick for {symbol}: {e}")

    def shutdown(self):
        """Shuts down the thread pool gracefully."""
        self.executor.shutdown(wait=True)


class BacktestDataHandler:
    """Fetches and provides historical data for backtesting."""

    def __init__(self, fyers_model, log_queue=None):
        self.fyers_model = fyers_model
        self.log_queue = log_queue

    def _log(self, message):
        if self.log_queue:
            self.log_queue.put(f"[{datetime.now().strftime('%H:%M:%S')}] [Data] {message}\n")

    def fetch_data(self, symbol, start_date, end_date, resolution="1"):
        """
        Fetches historical data for a given symbol and date range.
        It iterates day by day to handle API limitations on intraday data ranges.
        """
        all_data = []
        current_date = start_date

        while current_date <= end_date:
            date_str = current_date.strftime('%Y-%m-%d')
            data = {
                "symbol": symbol, "resolution": resolution, "date_format": "1",
                "range_from": date_str,
                "range_to": date_str,
                "cont_flag": "1"
            }
            response = self.fyers_model.history(data=data)

            if response and response.get('candles'):
                df = pd.DataFrame(response['candles'])
                df.columns = ['date', 'open', 'high', 'low', 'close', 'volume']
                df['date'] = pd.to_datetime(df['date'], unit='s')
                df['date'] = df['date'].dt.tz_localize('UTC').dt.tz_convert('Asia/Kolkata')
                df['date'] = df['date'].dt.tz_localize(None)
                df = df.set_index('date')
                all_data.append(df)
            current_date += timedelta(days=1)

        if not all_data:
            self._log(f"Failed to fetch any historical data for {symbol} in the given range.")
            return pd.DataFrame()

        return pd.concat(all_data)