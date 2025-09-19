import os
import inspect
import importlib.util
from pathlib import Path
from datetime import datetime
import threading
import time
import pandas as pd
from fyers_apiv3 import fyersModel
from fyers_apiv3.FyersWebsocket import data_ws

from .auth import FyersAuthClient
from .execution import OrderManager
from .data_handler import LiveDataHandler, BacktestDataHandler
from trading_core.strategies.base_strategy import Strategy
from fyers_api.client import FyersApiClient


class TradingEngine:
    def __init__(self, live_log_queue=None, backtest_log_queue=None, data_log_queue=None):
        self.live_log_queue = live_log_queue
        self.backtest_log_queue = backtest_log_queue
        self.data_log_queue = data_log_queue
        self.fyers = None
        self.api_client = None
        self.order_manager = None
        self.live_data_handler = None
        self.fyers_socket = None

        self._simulation_running = False
        self._stop_simulation_flag = False

        # Authentication attributes
        self.client_id = os.getenv('APP_ID')
        self.access_token = None

        self._active_log_queue = self.live_log_queue
        self.strategies_map = self._load_strategies()

    @property
    def is_simulation_running(self):
        return self._simulation_running

    def _log(self, message):
        if self._active_log_queue:
            self._active_log_queue.put(f"[{datetime.now().strftime('%H:%M:%S')}] [Engine] {message}\n")

    def _authenticate(self):
        """Handles only the token generation part of authentication."""
        if self.access_token: return True
        try:
            self._log("Authenticating...")
            auth_client = FyersAuthClient(
                fy_id=os.getenv('FY_ID'), app_id=self.client_id,
                app_type="100", app_secret=os.getenv('APP_SECRET'),
                totp_key=os.getenv('TOTP_KEY'), pin=os.getenv('PIN'),
                redirect_uri=os.getenv('REDIRECT_URL')
            )
            self.access_token = auth_client.get_access_token()
            if not self.access_token:
                self._log("Authentication failed.")
                return False
            self._log("Authentication successful.")
            return True
        except Exception as e:
            self._log(f"Authentication error: {e}")
            return False

    def authenticate_and_initialize(self):
        """Authenticates and ensures the FyersModel instance is created."""
        if self.fyers:
            return True

        if self._authenticate():
            self.fyers = fyersModel.FyersModel(
                client_id=self.client_id, token=self.access_token, log_path="logs"
            )
            self.api_client = FyersApiClient(self.fyers)
            self.order_manager = OrderManager(self.fyers, log_callback=self._log)
            return True
        return False

    def get_account_funds(self):
        """Fetches account funds using the API client."""
        if not self.api_client:
            if not self.authenticate_and_initialize():
                return {"status": "error", "error": "Authentication Failed"}
        return self.api_client.get_funds()

    def get_orderbook(self):
        """Fetches the order book from Fyers."""
        if not self.fyers:
            if not self.authenticate_and_initialize():
                return {"status": "error", "error": "Authentication Failed"}
        try:
            response = self.fyers.orderbook()
            if response.get('s') == 'ok':
                return {"status": "success", "data": response.get('orderBook', [])}
            else:
                error_msg = response.get('message', 'Unknown Fyers API error')
                self._log(f"Error fetching order book: {error_msg}")
                return {"status": "error", "error": error_msg}
        except Exception as e:
            self._log(f"Exception fetching order book: {e}")
            return {"status": "error", "error": str(e)}

    def get_tradebook(self):
        """Fetches the trade book from Fyers."""
        if not self.fyers:
            if not self.authenticate_and_initialize():
                return {"status": "error", "error": "Authentication Failed"}
        try:
            response = self.fyers.tradebook()
            if response.get('s') == 'ok':
                return {"status": "success", "data": response.get('tradebook', [])}
            else:
                error_msg = response.get('message', 'Unknown Fyers API error')
                self._log(f"Error fetching trade book: {error_msg}")
                return {"status": "error", "error": error_msg}
        except Exception as e:
            self._log(f"Exception fetching trade book: {e}")
            return {"status": "error", "error": str(e)}

    def start_live_session(self, trackers: list):
        self._active_log_queue = self.live_log_queue
        if not self.authenticate_and_initialize():
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

    def _on_live_data(self, message, timestamp=None):
        log_timestamp = timestamp or datetime.now()
        if self.data_log_queue:
            # Using a more detailed timestamp for data logs
            self.data_log_queue.put(f"{log_timestamp.strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}: {message}\n")
        if self.live_data_handler:
            self.live_data_handler.on_message(message, timestamp=timestamp)

    def _start_websocket(self):
        token = self.fyers.token
        self.fyers_socket = data_ws.FyersDataSocket(
            access_token=token, on_message=self._on_live_data,
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

    def start_live_simulation(self, trackers: list, start_date, end_date, speed=1.0):
        self._active_log_queue = self.live_log_queue
        if not self.authenticate_and_initialize():
            return

        self._log(f"Starting LIVE SIMULATION for {len(trackers)} tracker(s).")
        self._log(f"Date Range: {start_date.strftime('%Y-%m-%d')} to {end_date.strftime('%Y-%m-%d')}")
        self._log(f"Simulation Speed: {speed}x")

        self._simulation_running = True
        self._stop_simulation_flag = False

        active_strategies = {}
        symbols_to_fetch = []
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
                symbols_to_fetch.append(symbol)
            else:
                self._log(f"Warning: Strategy '{strategy_name}' not found.")

        if not active_strategies:
            self._log("No valid strategies to run. Stopping.")
            return

        # Use the LiveDataHandler to process simulated ticks, just like real ones
        self.live_data_handler = LiveDataHandler(active_strategies, self.live_log_queue)

        backtest_handler = BacktestDataHandler(self.fyers, self.live_log_queue)
        all_data = []
        for symbol in set(symbols_to_fetch):
            self._log(f"Fetching historical data for {symbol}...")
            historical_data = backtest_handler.fetch_data(symbol, start_date, end_date)
            if not historical_data.empty:
                historical_data['symbol'] = symbol
                all_data.append(historical_data)

        if not all_data:
            self._log("Live simulation finished: No historical data found.")
        else:
            combined_data = pd.concat(all_data).sort_index()
            self._log(f"Data fetched. Simulating {len(combined_data)} total ticks...")

            previous_sim_timestamp = None
            last_real_timestamp = None

            for sim_timestamp, row in combined_data.iterrows():
                if self._stop_simulation_flag:
                    self._log("Live simulation stopped by user.")
                    break

                # --- Real-time delay simulation ---
                if previous_sim_timestamp:
                    # This is the delay from the historical data
                    sim_delay = (sim_timestamp - previous_sim_timestamp).total_seconds()

                    # If the delay is large (e.g., overnight gap), cap it to a small
                    # value to avoid long waits. A 5-minute threshold should be safe.
                    if sim_delay > 300:  # 5 minutes
                        sim_delay = 1  # Cap to 1 second

                    # Apply speed multiplier. If speed is 0 or less, run as fast as possible.
                    if speed <= 0:
                        sim_delay = 0
                    else:
                        sim_delay /= speed

                    # This is how long processing the last tick actually took in real-world time
                    real_time_elapsed = time.time() - last_real_timestamp
                    # The amount we need to sleep is the simulated delay minus the real time it took to process.
                    sleep_duration = sim_delay - real_time_elapsed

                    if sleep_duration > 0:
                        # Sleep in small chunks to remain responsive to the stop flag
                        sleep_end_time = time.time() + sleep_duration
                        while time.time() < sleep_end_time:
                            if self._stop_simulation_flag:
                                break
                            time.sleep(min(0.1, sleep_end_time - time.time()))

                if self._stop_simulation_flag:  # Check again after sleep
                    self._log("Live simulation stopped by user.")
                    break

                # Record timestamps for next iteration's delay calculation
                previous_sim_timestamp = sim_timestamp
                last_real_timestamp = time.time()
                simulated_message = row.to_dict()
                self._on_live_data(simulated_message, timestamp=sim_timestamp.to_pydatetime())
            self._log("Live simulation finished.")

        if self.live_data_handler:
            # Wait for all pending ticks in the thread pool to be processed
            self.live_data_handler.shutdown()

        self._simulation_running = False
        self._stop_simulation_flag = False

    def stop_session(self):
        self._log("Stopping session...")
        if self.is_simulation_running:
            self._stop_simulation_flag = True
            self._log("Stop signal sent to live simulation.")
            return

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

        if not self.authenticate_and_initialize():
            self.backtest_log_queue.put("Authentication failed. Cannot run backtest.")
            return

        self._log(f"Starting '{trade_type}' backtest for {symbol} with {strategy_name}...")
        backtest_handler = BacktestDataHandler(self.fyers, self.backtest_log_queue)
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
            strategy_instance.on_tick(timestamp.to_pydatetime(), row.to_dict())
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
