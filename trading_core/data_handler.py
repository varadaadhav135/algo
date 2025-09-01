# trading_bot/trading_core/data_handler.py
import pandas as pd
from datetime import datetime
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

    def on_message(self, msg):
        """Offloads the actual processing to a worker thread to keep the WS receiver responsive."""
        self.executor.submit(self._process_tick, msg)

    def _process_tick(self, msg):
        """The core logic to process a single tick message."""
        try:
            symbol = msg.get('symbol')
            if symbol and symbol in self.active_strategies and msg.get("ltp"):
                price = float(msg.get("ltp"))
                strategy = self.active_strategies[symbol]
                # Pass the current time as the tick timestamp for live trading
                strategy.on_tick(datetime.now(), price)
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
        data = {
            "symbol": symbol, "resolution": resolution, "date_format": "1",
            "range_from": start_date.strftime('%Y-%m-%d'),
            "range_to": end_date.strftime('%Y-%m-%d'),
            "cont_flag": "1"
        }
        response = self.fyers_model.history(data=data)
        if response and response.get('candles'):
            df = pd.DataFrame(response['candles'])
            df.columns = ['date', 'open', 'high', 'low', 'close', 'volume']
            df['date'] = pd.to_datetime(df['date'], unit='s')
            df['date'] = df['date'].dt.tz_localize('UTC').dt.tz_convert('Asia/Kolkata')
            df['date'] = df['date'].dt.tz_localize(None)  # Remove timezone for simplicity
            df = df.set_index('date')
            return df
        self._log(f"Failed to fetch historical data: {response.get('message', 'No data')}")
        return pd.DataFrame()