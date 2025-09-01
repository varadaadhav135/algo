# trading_bot/main.py
import os
from dotenv import load_dotenv
from ttkthemes import ThemedTk
from gui_app.main import TradingApp

if __name__ == "__main__":
    # Load environment variables from a .env file
    # Create a file named '.env' in the trading_bot directory
    # and add your credentials there, e.g.,
    # FY_ID="your_fyers_id"
    # APP_ID="your_app_id"
    # ... etc.
    load_dotenv()

    # Initialize and run the GUI application
    root = ThemedTk(theme="vista")
    app = TradingApp(root)
    root.mainloop()