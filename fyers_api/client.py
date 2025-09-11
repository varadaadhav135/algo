# fyers_api/client.py

class FyersApiClient:
    """
    A wrapper class for the Fyers API model to encapsulate API calls.
    """
    def __init__(self, fyers_model):
        """
        Initializes the API client with a FyersModel instance.

        Args:
            fyers_model: An authenticated fyersModel.FyersModel instance.
        """
        self.fyers_model = fyers_model

    def get_funds(self):
        """
        Fetches account funds and returns the available balance.

        Returns:
            A dictionary with 'status' and 'data' or 'error' keys.
        """
        try:
            funds_response = self.fyers_model.funds()
            if funds_response.get('s') == 'ok':
                # Find the fund limit with id 10 (equity amount)
                equity_limit = next((limit for limit in funds_response.get('fund_limit', []) if limit.get('id') == 10), None)
                if equity_limit:
                    balance = equity_limit.get('equityAmount', 0)
                    return {"status": "success", "data": f"₹{balance:,.2f}"}
                return {"status": "error", "error": "Equity fund limit not found."}
            return {"status": "error", "error": funds_response.get('message', 'Unknown API error')}
        except Exception as e:
            return {"status": "error", "error": str(e)}
