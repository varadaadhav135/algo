from abc import ABC, abstractmethod
from datetime import datetime
import math


class Strategy(ABC):
    """Abstract base class for all trading strategies."""

    @classmethod
    @property
    @abstractmethod
    def STRATEGY_NAME(cls) -> str:
        pass

    def __init__(self, symbol, order_manager, trade_type="Intraday",
                 sizing_type="Quantity", sizing_value=1):
        self.symbol = symbol
        self.order_manager = order_manager
        self.trade_type = trade_type
        self.product_type = "CNC" if self.trade_type == "Positional" else "INTRADAY"

        # --- NEW: Store sizing parameters ---
        self.sizing_type = sizing_type
        self.sizing_value = int(sizing_value)  # Ensure value is an integer

    def _calculate_quantity(self, price: float) -> int:
        """Calculates the trade quantity based on the selected sizing method."""
        if price <= 0:
            return 0

        if self.sizing_type == "Quantity":
            return self.sizing_value

        elif self.sizing_type == "Amount":
            if self.sizing_value < price:
                # Not enough capital to buy even one share
                return 0
            return math.floor(self.sizing_value / price)

        return 0  # Default to 0 if sizing type is unknown

    @abstractmethod
    def on_tick(self, timestamp: datetime, price: float):
        """This method will be called for every new price tick."""
        pass