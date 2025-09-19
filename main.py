import os
import sys
from dotenv import load_dotenv
from ttkthemes import ThemedTk

# Add project root to the Python path to ensure modules are discoverable
project_root = os.path.dirname(os.path.abspath(__file__))
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from gui_app.main import TradingApp

def main():
    """
    Main function to initialize and run the trading application.
    """
    # Load environment variables from .env file
    load_dotenv()

    # Initialize and run the GUI application
    root = ThemedTk(theme="black")
    app = TradingApp(root)
    root.mainloop()

if __name__ == "__main__":
    main()
