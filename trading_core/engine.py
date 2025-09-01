import os
import inspect
import importlib.util
from pathlib import Path
from datetime import datetime
import threading
from fyers_apiv3 import fyersModel
from fyers_apiv3.FyersWebsocket import data_ws

from .auth import FyersAuthClient
from .execution import OrderManager
from .data_handler import LiveDataHandler, BacktestDataHandler
from trading_core.strategies.base_strategy import Strategy


class TradingEngine:
    def __init__(self, live_log_queue=None, backtest_log_queue=None):
        self.live_log_queue = live_log_queue
        self.backtest_log_queue = backtest_log_queue
        self.fyers_model = None
        self.order_manager = None
        self.live_data_handler = None
        self.fyers_socket = None

        self._active_log_queue = self.live_log_queue
        self.strategies_map = self._load_strategies()

    def _log(self, message):
        if self._active_log_queue:
            log_entry = f"[{datetime.now().strftime('%H:%M:%S')}] [Engine] {message}"
            self._active_log_queue.put(log_entry + "\n")

    def _authenticate(self):
        if self.fyers_model: return True
        try:
            self._log("Authenticating...")
            auth_client = FyersAuthClient(
                fy_id=os.getenv('FY_ID'), app_id=os.getenv('APP_ID'),
                app_type="100", app_secret=os.getenv('APP_SECRET'),
                totp_key=os.getenv('TOTP_KEY'), pin=os.getenv('PIN'),
                redirect_uri=os.getenv('REDIRECT_URL')
            )
            access_token = auth_client.get_access_token()
            if not access_token:
                self._log("Authentication failed.")
                return False
            self.fyers_model = fyersModel.FyersModel(
                client_id=os.getenv('APP_ID'), token=access_token, is_async=False
            )
            self.order_manager = OrderManager(self.fyers_model, log_callback=self._log)
            self._log("Authentication successful.")
            return True
        except Exception as e:
            self._log(f"Authentication error: {e}")
            return False

    def start_live_session(self, trackers: list):
        self._active_log_queue = self.live_log_queue
        if not self._authenticate():
            return
        self._log(f"Starting live session for {len(trackers)} tracker(s).")

        active_strategies = {}
        for tracker in trackers:
            symbol = tracker['symbol']
            strategy_name = tracker['strategy_name']
            trade_type = tracker['trade_type']
            sizing_type = tracker['sizing_type']
            sizing_value = tracker['sizing_value']

            if strategy_name in self.strategies_map:
                strategy_class = self.strategies_map[strategy_name]
                active_strategies[symbol] = strategy_class(
                    symbol, self.order_manager,
                    trade_type=trade_type,
                    sizing_type=sizing_type,
                    sizing_value=sizing_value
                )
            else:
                self._log(f"Warning: Strategy '{strategy_name}' not found.")

        if not active_strategies:
            self._log("No valid strategies to run. Stopping.")
            return

        self.live_data_handler = LiveDataHandler(active_strategies, self.live_log_queue)
        self._start_websocket()

    def _start_websocket(self):
        token = self.fyers_model.token
        self.fyers_socket = data_ws.FyersDataSocket(
            access_token=token, on_message=self.live_data_handler.on_message,
            on_error=lambda e: self._log(f"WebSocket Error: {e}"),
            on_close=lambda e: self._log(f"WebSocket Closed: {e}"),
            on_connect=lambda: self._on_ws_connect(self.live_data_handler.active_strategies)
        )
        threading.Thread(target=self.fyers_socket.connect, daemon=True).start()

    def _on_ws_connect(self, active_strategies):
        symbols = list(active_strategies.keys())
        self._log(f"WebSocket connected. Subscribing to: {', '.join(symbols)}")
        self.fyers_socket.subscribe(symbols=symbols, data_type="SymbolUpdate")
        self.fyers_socket.keep_running()

    def stop_session(self):
        self._log("Stopping session...")
        if self.live_data_handler:
            self.live_data_handler.shutdown()
        if self.fyers_socket:
            self.fyers_socket.close_connection()
        self._log("Session stopped.")

    def run_backtest(self, symbol, strategy_name, start_date, end_date,
                     trade_type="Intraday", sizing_type="Quantity", sizing_value=1):
        self._active_log_queue = self.backtest_log_queue
        if strategy_name not in self.strategies_map:
            self._log(f"Backtest failed: Strategy '{strategy_name}' not found.")
            return

        self._log(f"Starting '{trade_type}' backtest for {symbol} with {strategy_name}...")
        backtest_handler = BacktestDataHandler(self.fyers_model, self.backtest_log_queue)
        historical_data = backtest_handler.fetch_data(symbol, start_date, end_date)

        if historical_data.empty:
            self._log("Backtest finished: No historical data found.")
            return

        self._log(f"Data fetched. Simulating {len(historical_data)} candles...")
        strategy_class = self.strategies_map[strategy_name]
        strategy_instance = strategy_class(
            symbol, self.order_manager,
            trade_type=trade_type,
            sizing_type=sizing_type,
            sizing_value=sizing_value
        )

        for timestamp, row in historical_data.iterrows():
            strategy_instance.on_tick(timestamp.to_pydatetime(), row['close'])
        self._log("Backtest finished.")

    def _load_strategies(self):
        strategy_map = {}
        current_file_path = Path(__file__).parent
        strategies_dir = current_file_path / "strategies"
        self._log(f"Searching for strategies in: {strategies_dir}")

        for file_path in strategies_dir.glob("*.py"):
            if file_path.name.startswith('__') or "base" in file_path.name:
                continue
            try:
                module_name = file_path.stem
                spec = importlib.util.spec_from_file_location(module_name, file_path)
                module = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(module)

                for name, obj in inspect.getmembers(module, inspect.isclass):
                    if issubclass(obj, Strategy) and obj is not Strategy:
                        strategy_map[obj.STRATEGY_NAME] = obj
                        self._log(f"Successfully loaded strategy: {obj.STRATEGY_NAME}")
            except Exception as e:
                self._log(f"Error loading strategy from {file_path.name}: {e}")

        if not strategy_map:
            self._log("CRITICAL: No strategies were found or loaded. The dropdown will be empty.")
        return strategy_map