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
        self._initialize_state()

    def _initialize_state(self):
        """
        Checks if there is an open position for this strategy and symbol,
        and restores the strategy's state if so.
        """
        position = self.order_manager.get_open_position(self.symbol)
        if position and position.get('strategy') == self.STRATEGY_NAME:
            # This strategy has an open position, restore state.
            self._restore_state_from_position(position)

    def _restore_state_from_position(self, position: dict):
        """
        Restores strategy-specific state from a persisted position.
        This method should be overridden by concrete strategies that need
        to maintain state across restarts.
        """
        pass  # Default implementation does nothing.

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
    def on_tick(self, timestamp: datetime, data: dict):
        """This method will be called for every new tick data."""
        pass