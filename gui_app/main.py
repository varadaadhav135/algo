import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, colorchooser
import threading
import queue
from datetime import datetime
import pandas as pd
from ttkthemes import ThemedTk
from tkcalendar import DateEntry

from trading_core.engine import TradingEngine


class SymbolSearchWindow(tk.Toplevel):
    def __init__(self, parent, callback, search_query=""):
        super().__init__(parent.root)
        self.parent = parent
        self.callback = callback
        self.title("Search Symbols")
        self.geometry("600x400")
        self.df = self.parent.equity_df
        search_frame = ttk.Frame(self, padding="10")
        search_frame.pack(fill=tk.X)
        ttk.Label(search_frame, text="Search:").pack(side=tk.LEFT, padx=(0, 5))
        self.search_entry = ttk.Entry(search_frame)
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True)
        self.search_entry.insert(0, search_query)
        self.search_entry.bind("<KeyRelease>", self.on_search)
        self.search_entry.focus_set()
        listbox_mode = tk.EXTENDED if self.callback == self.parent.add_symbols_to_tracker_tree else tk.SINGLE
        self.results_listbox = tk.Listbox(self, selectmode=listbox_mode)
        self.results_listbox.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        self.results_listbox.bind("<Double-1>", self.on_double_click)
        button_frame = ttk.Frame(self, padding="10")
        button_frame.pack(fill=tk.X)
        ttk.Button(button_frame, text="Add Selected", command=self.add_selected).pack(side=tk.LEFT)
        ttk.Button(button_frame, text="Close", command=self.destroy).pack(side=tk.RIGHT)
        if self.df is not None:
            self.on_search()
        else:
            self.results_listbox.insert(tk.END, "CSV file not loaded.")

    def populate_listbox(self, df):
        self.results_listbox.delete(0, tk.END)
        for _, row in df.iterrows():
            self.results_listbox.insert(tk.END, f"{row['SYMBOL']} | {row['NAME OF COMPANY']}")

    def on_search(self, event=None):
        query = self.search_entry.get().strip().lower()
        if self.df is None: return
        if not query:
            return self.populate_listbox(self.df)
        mask = self.df['SYMBOL'].str.lower().str.contains(query) | self.df['NAME OF COMPANY'].str.lower().str.contains(
            query)
        self.populate_listbox(self.df[mask])

    def add_selected(self):
        selected_indices = self.results_listbox.curselection()
        if not selected_indices: return
        selected_symbols = [self.results_listbox.get(i).split('|')[0].strip() for i in selected_indices]
        self.callback(selected_symbols)
        self.destroy()

    def on_double_click(self, event):
        self.add_selected()


class BacktestOrderManager:
    def __init__(self, log_callback):
        self.log_callback = log_callback
        self.log_callback("Initialized Mock Order Manager for Backtesting.")

    def place_order(self, symbol, qty, side, order_type, timestamp,
                    strategy_name=None, entry_price=None, exit_reason=None, price=None, **kwargs):
        trade_type = "BUY" if side == 1 else "SELL"
        title = "--- TRADE EXIT ---" if exit_reason is not None else "--- TRADE ENTRY ---"
        log_message = f"{title}\n"
        log_message += f"  Timestamp: {timestamp.strftime('%Y-%m-%d %H:%M:%S')}\n"
        log_message += f"  Symbol:    {symbol}\n"
        log_message += f"  Strategy:  {strategy_name or 'N/A'}\n"
        log_message += f"  Action:    {trade_type} @ {price}\n"
        log_message += f"  Quantity:  {qty}\n"
        if exit_reason and entry_price and price:
            pnl = ((price - entry_price) * qty) if side == -1 else ((entry_price - price) * qty)
            log_message += f"  P&L:     {pnl:.2f}\n"
            log_message += f"  Reason:  {exit_reason}\n"
        elif exit_reason:
            log_message += f"  Reason:  {exit_reason}\n"
        log_message += "--------------------"
        self.log_callback(log_message)


class SettingsWindow(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent.root)
        self.parent = parent
        self.title("Settings")
        self.geometry("350x200")
        frame = ttk.Frame(self, padding="10")
        frame.pack(fill=tk.BOTH, expand=True)
        ttk.Label(frame, text="Theme:").grid(row=0, column=0, padx=5, pady=10, sticky="w")
        self.theme_combobox = ttk.Combobox(frame, values=self.parent.style.theme_names(), state="readonly")
        self.theme_combobox.grid(row=0, column=1, padx=5, pady=10)
        self.theme_combobox.set(self.parent.style.theme_use())
        button_frame = ttk.Frame(frame)
        button_frame.grid(row=2, column=0, columnspan=2, pady=20)
        ttk.Button(button_frame, text="Apply", command=self.apply_settings).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Close", command=self.destroy).pack(side=tk.LEFT, padx=5)

    def apply_settings(self):
        selected_theme = self.theme_combobox.get()
        self.parent.root.set_theme(selected_theme)
        messagebox.showinfo("Settings Applied", "Theme has been updated!", parent=self)
        self.destroy()


class TradingApp:
    def __init__(self, root):
        self.root = root
        self.root.title("Trading Bot Controller")
        self.root.geometry("900x700")
        self.style = ttk.Style(self.root)
        self.selected_backtest_symbol_var = tk.StringVar(value="No symbol selected")
        self.live_log_queue = queue.Queue()
        self.backtest_log_queue = queue.Queue()
        self.engine = TradingEngine(
            live_log_queue=self.live_log_queue,
            backtest_log_queue=self.backtest_log_queue
        )
        self.equity_df = self._load_equity_data()
        self._create_widgets()
        self._create_menu()
        self.root.after(100, self._process_live_log_queue)
        self.root.after(100, self._process_backtest_log_queue)

    def _create_menu(self):
        menu_bar = tk.Menu(self.root)
        self.root.config(menu=menu_bar)
        file_menu = tk.Menu(menu_bar, tearoff=0)
        menu_bar.add_cascade(label="File", menu=file_menu)
        file_menu.add_command(label="Settings", command=self.open_settings)
        file_menu.add_separator()
        file_menu.add_command(label="Exit", command=self.root.quit)

    def _create_widgets(self):
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        self.live_trade_tab = ttk.Frame(self.notebook)
        self.backtest_tab = ttk.Frame(self.notebook)
        self.notebook.add(self.live_trade_tab, text='Live Trading')
        self.notebook.add(self.backtest_tab, text='Backtesting')
        self._create_live_trade_widgets()
        self._create_backtest_widgets()

    def _create_live_trade_widgets(self):
        main_frame = ttk.Frame(self.live_trade_tab, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        input_frame = ttk.LabelFrame(main_frame, text="Configure Stock Tracker", padding="10")
        input_frame.pack(fill=tk.X, pady=5)
        input_frame.columnconfigure(1, weight=1)

        ttk.Label(input_frame, text="Symbol:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        self.select_symbols_button = ttk.Button(input_frame, text="Select Symbols...",
                                                command=self.open_live_search_window)
        self.select_symbols_button.grid(row=0, column=1, sticky="w", padx=5, pady=5)

        ttk.Label(input_frame, text="Strategy:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        strategy_names = list(self.engine.strategies_map.keys())
        self.live_strategy_combobox = ttk.Combobox(input_frame, values=strategy_names, state="readonly", width=35)
        self.live_strategy_combobox.grid(row=1, column=1, padx=5, pady=5, sticky="ew")
        if strategy_names:
            self.live_strategy_combobox.current(0)

        ttk.Label(input_frame, text="Trade Type:").grid(row=2, column=0, sticky="w", padx=5, pady=5)
        self.live_trade_type_combobox = ttk.Combobox(input_frame, values=["Intraday", "Positional"], state="readonly",
                                                     width=35)
        self.live_trade_type_combobox.grid(row=2, column=1, padx=5, pady=5, sticky="ew")
        self.live_trade_type_combobox.current(0)

        ttk.Label(input_frame, text="Sizing:").grid(row=3, column=0, sticky="w", padx=5, pady=5)
        sizing_frame = ttk.Frame(input_frame)
        sizing_frame.grid(row=3, column=1, sticky="ew", padx=5, pady=5)
        self.live_sizing_type_combobox = ttk.Combobox(sizing_frame, values=["Quantity", "Amount"], state="readonly",
                                                      width=10)
        self.live_sizing_type_combobox.pack(side="left")
        self.live_sizing_type_combobox.current(0)
        self.live_sizing_value_entry = ttk.Entry(sizing_frame, width=15)
        self.live_sizing_value_entry.pack(side="left", padx=5, fill="x", expand=True)
        self.live_sizing_value_entry.insert(0, "1")

        display_frame = ttk.LabelFrame(main_frame, text="Active Trackers", padding="10")
        display_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        self.tree = ttk.Treeview(display_frame, columns=("Symbol", "Strategy", "Type", "Sizing", "Value"),
                                 show="headings")
        self.tree.heading("Symbol", text="Symbol")
        self.tree.heading("Strategy", text="Strategy")
        self.tree.heading("Type", text="Trade Type")
        self.tree.heading("Sizing", text="Sizing Type")
        self.tree.heading("Value", text="Value")
        self.tree.column("Symbol", width=150)
        self.tree.column("Strategy", width=180)
        self.tree.column("Type", width=100)
        self.tree.column("Sizing", width=80)
        self.tree.column("Value", width=80)
        self.tree.pack(fill=tk.BOTH, expand=True)

        control_frame = ttk.Frame(main_frame, padding="10")
        control_frame.pack(fill=tk.X)
        self.start_button = ttk.Button(control_frame, text="Start Trading", command=self.start_trading)
        self.start_button.pack(side=tk.LEFT, padx=5)
        self.stop_button = ttk.Button(control_frame, text="Stop Trading", command=self.stop_trading, state="disabled")
        self.stop_button.pack(side=tk.LEFT, padx=5)

        log_frame = ttk.LabelFrame(main_frame, text="Live Logs", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=5)
        self.log_area = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, state='disabled', height=10)
        self.log_area.pack(fill=tk.BOTH, expand=True)

    def _create_backtest_widgets(self):
        main_frame = ttk.Frame(self.backtest_tab, padding="10")
        main_frame.pack(fill=tk.BOTH, expand=True)
        input_frame = ttk.LabelFrame(main_frame, text="Backtest Configuration", padding="10")
        input_frame.pack(fill=tk.X, pady=5)
        input_frame.columnconfigure(1, weight=1)

        ttk.Label(input_frame, text="Symbol:").grid(row=0, column=0, sticky="w", padx=5, pady=5)
        symbol_frame = ttk.Frame(input_frame)
        symbol_frame.grid(row=0, column=1, sticky="ew", columnspan=2, padx=5, pady=5)
        self.select_backtest_symbol_button = ttk.Button(symbol_frame, text="Select Symbol...",
                                                        command=self.open_backtest_search_window)
        self.select_backtest_symbol_button.pack(side="left")
        self.selected_symbol_label = ttk.Label(symbol_frame, textvariable=self.selected_backtest_symbol_var,
                                               relief="sunken", padding=(5, 2))
        self.selected_symbol_label.pack(side="left", padx=10, fill="x", expand=True)

        ttk.Label(input_frame, text="Strategy:").grid(row=1, column=0, sticky="w", padx=5, pady=5)
        strategy_names = list(self.engine.strategies_map.keys())
        self.backtest_strategy_combobox = ttk.Combobox(input_frame, values=strategy_names, state="readonly")
        self.backtest_strategy_combobox.grid(row=1, column=1, sticky="ew", columnspan=2, padx=5, pady=5)
        if strategy_names:
            self.backtest_strategy_combobox.current(0)

        ttk.Label(input_frame, text="Trade Type:").grid(row=2, column=0, sticky="w", padx=5, pady=5)
        self.backtest_trade_type_combobox = ttk.Combobox(input_frame, values=["Intraday", "Positional"],
                                                         state="readonly")
        self.backtest_trade_type_combobox.grid(row=2, column=1, sticky="ew", columnspan=2, padx=5, pady=5)
        self.backtest_trade_type_combobox.current(0)

        ttk.Label(input_frame, text="Sizing:").grid(row=3, column=0, sticky="w", padx=5, pady=5)
        sizing_frame = ttk.Frame(input_frame)
        sizing_frame.grid(row=3, column=1, sticky="ew", padx=5, pady=5, columnspan=2)
        self.backtest_sizing_type_combobox = ttk.Combobox(sizing_frame, values=["Quantity", "Amount"], state="readonly",
                                                          width=10)
        self.backtest_sizing_type_combobox.pack(side="left")
        self.backtest_sizing_type_combobox.current(0)
        self.backtest_sizing_value_entry = ttk.Entry(sizing_frame, width=15)
        self.backtest_sizing_value_entry.pack(side="left", padx=5, fill="x", expand=True)
        self.backtest_sizing_value_entry.insert(0, "1")

        ttk.Label(input_frame, text="From Date:").grid(row=4, column=0, sticky="w", padx=5, pady=5)
        self.start_date_entry = DateEntry(input_frame, date_pattern='yyyy-mm-dd', width=12)
        self.start_date_entry.grid(row=4, column=1, sticky="ew", columnspan=2, padx=5, pady=5)
        self.start_date_entry.bind("<Button-1>", lambda e: self.start_date_entry.drop_down())

        ttk.Label(input_frame, text="To Date:").grid(row=5, column=0, sticky="w", padx=5, pady=5)
        self.end_date_entry = DateEntry(input_frame, date_pattern='yyyy-mm-dd', width=12)
        self.end_date_entry.grid(row=5, column=1, sticky="ew", columnspan=2, padx=5, pady=5)
        self.end_date_entry.bind("<Button-1>", lambda e: self.end_date_entry.drop_down())

        button_frame = ttk.Frame(input_frame)
        button_frame.grid(row=6, column=0, columnspan=3, pady=10)
        self.run_backtest_button = ttk.Button(button_frame, text="Run Backtest", command=self.start_backtest)
        self.run_backtest_button.pack()

        log_frame = ttk.LabelFrame(main_frame, text="Backtest Results", padding="10")
        log_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        self.backtest_log_area = scrolledtext.ScrolledText(log_frame, wrap=tk.WORD, state='disabled', height=10)
        self.backtest_log_area.pack(fill=tk.BOTH, expand=True)

    def open_settings(self):
        SettingsWindow(self)

    def open_live_search_window(self):
        if self.equity_df is None: return messagebox.showerror("Error", "Symbol data file is missing.")
        SymbolSearchWindow(self, callback=self.add_symbols_to_tracker_tree)

    def open_backtest_search_window(self):
        if self.equity_df is None: return messagebox.showerror("Error", "Symbol data file is missing.")
        SymbolSearchWindow(self, callback=self.set_backtest_symbol)

    def add_symbols_to_tracker_tree(self, symbols):
        strategy_name = self.live_strategy_combobox.get()
        trade_type = self.live_trade_type_combobox.get()
        sizing_type = self.live_sizing_type_combobox.get()
        sizing_value = self.live_sizing_value_entry.get()
        if not strategy_name: return messagebox.showwarning("Strategy Not Selected", "Please select a strategy.")
        if not sizing_value.isdigit() or int(sizing_value) <= 0: return messagebox.showwarning("Input Error",
                                                                                               "Sizing value must be a positive number.")
        for symbol in symbols:
            is_duplicate = any(self.tree.item(i)['values'][0] == symbol for i in self.tree.get_children())
            if not is_duplicate:
                self.tree.insert("", "end", values=(symbol, strategy_name, trade_type, sizing_type, sizing_value))

    def set_backtest_symbol(self, symbols):
        if symbols:
            self.selected_backtest_symbol_var.set(symbols[0])

    def _load_equity_data(self, filename='EQUITY_L_modified.csv'):
        try:
            df = pd.read_csv(filename, skipinitialspace=True)
            df.columns = df.columns.str.strip()
            df['SYMBOL'] = df['SYMBOL'].astype(str)
            df['NAME OF COMPANY'] = df['NAME OF COMPANY'].astype(str)
            self.live_log_queue.put(
                f"[{datetime.now().strftime('%H:%M:%S')}] [GUI] Equity symbol data loaded successfully.\n")
            return df
        except FileNotFoundError:
            messagebox.showerror("Error", f"Could not find '{filename}'. Symbol search will be disabled.")
            return None
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load symbol data: {e}")
            return None

    def start_trading(self):
        active_trackers = [
            {
                'symbol': self.tree.item(i)['values'][0],
                'strategy_name': self.tree.item(i)['values'][1],
                'trade_type': self.tree.item(i)['values'][2],
                'sizing_type': self.tree.item(i)['values'][3],
                'sizing_value': self.tree.item(i)['values'][4]
            }
            for i in self.tree.get_children()
        ]
        if not active_trackers:
            return messagebox.showerror("Error", "No trackers configured.")
        self.live_log_queue.put("GUI: Sending command to start live session...\n")
        self.start_button.config(state="disabled")
        self.stop_button.config(state="normal")
        threading.Thread(
            target=self.engine.start_live_session,
            args=(active_trackers,),
            daemon=True
        ).start()

    def stop_trading(self):
        self.live_log_queue.put("GUI: Sending command to stop session...\n")
        self.engine.stop_session()
        self.start_button.config(state="normal")
        self.stop_button.config(state="disabled")

    def start_backtest(self):
        symbol = self.selected_backtest_symbol_var.get()
        if symbol == "No symbol selected" or not symbol:
            return messagebox.showerror("Input Error", "Please select a symbol for the backtest.")

        strategy_name = self.backtest_strategy_combobox.get()
        start_date = self.start_date_entry.get_date()
        end_date = self.end_date_entry.get_date()
        trade_type = self.backtest_trade_type_combobox.get()
        sizing_type = self.backtest_sizing_type_combobox.get()
        sizing_value = self.backtest_sizing_value_entry.get()

        if not sizing_value.isdigit() or int(sizing_value) <= 0:
            return messagebox.showerror("Input Error", "Sizing value must be a positive number.")

        if not all([strategy_name, start_date, end_date, trade_type]):
            return messagebox.showerror("Input Error", "All fields are required.")

        self.backtest_log_area.config(state='normal')
        self.backtest_log_area.delete(1.0, tk.END)
        self.backtest_log_area.config(state='disabled')
        self.run_backtest_button.config(state="disabled")
        threading.Thread(
            target=self._run_backtest_thread,
            args=(symbol, strategy_name, start_date, end_date, trade_type, sizing_type, sizing_value),
            daemon=True
        ).start()

    def _run_backtest_thread(self, symbol, strategy_name, start_date, end_date, trade_type, sizing_type, sizing_value):
        is_authenticated = self.engine._authenticate()
        if not is_authenticated:
            self.backtest_log_queue.put("Authentication failed. Cannot run backtest.\n")
            self.root.after(0, lambda: self.run_backtest_button.config(state="normal"))
            return

        mock_om = BacktestOrderManager(lambda msg: self.backtest_log_queue.put(msg + "\n"))
        original_om = self.engine.order_manager
        self.engine.order_manager = mock_om

        self.engine.run_backtest(symbol, strategy_name, start_date, end_date, trade_type, sizing_type, sizing_value)

        self.engine.order_manager = original_om
        self.root.after(0, lambda: self.run_backtest_button.config(state="normal"))

    def _process_live_log_queue(self):
        while not self.live_log_queue.empty():
            message = self.live_log_queue.get_nowait()
            self._update_live_log(message)
        self.root.after(100, self._process_live_log_queue)

    def _process_backtest_log_queue(self):
        while not self.backtest_log_queue.empty():
            message = self.backtest_log_queue.get_nowait()
            self._update_backtest_log(message)
        self.root.after(100, self._process_backtest_log_queue)

    def _update_live_log(self, message):
        self.log_area.config(state='normal')
        self.log_area.insert(tk.END, message)
        self.log_area.config(state='disabled')
        self.log_area.see(tk.END)

    def _update_backtest_log(self, message):
        self.backtest_log_area.config(state='normal')
        self.backtest_log_area.insert(tk.END, message)
        self.backtest_log_area.config(state='disabled')
        self.backtest_log_area.see(tk.END)