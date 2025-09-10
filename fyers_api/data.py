# fyers_api/data.py

import pandas as pd
import requests
from io import StringIO
import os
from datetime import date

# URLs for different exchange segments from Fyers
FYERS_MASTER_URLS = {
    "NSE_CM": "https://public.fyers.in/sym_details/NSE_CM.csv",
    "NSE_FO": "https://public.fyers.in/sym_details/NSE_FO.csv",
    "NSE_CD": "https://public.fyers.in/sym_details/NSE_CD.csv",
    # Add other segments like BSE, MCX if needed
}

# Define column names for header-less files like NSE_FO and NSE_CD
DERIVATIVE_COLUMNS = [
    "Fyers Token", "Symbol Details", "Exchange Instrument Type", "Minimum Lot Size",
    "Tick Size", "ISIN", "Trading Session", "Last Update Date", "Expiry Date",
    "Symbol Ticker", "Exchange", "Segment", "Scrip Code", "Underlying Scrip",
    "Underlying Fytoken", "Strike Price", "Option Type", "Underlying ISIN",
    "Permitted To Trade", "Qty Freeze", "Credit Var"
]


def get_symbols(segment, data_dir="data"):
    """
    Downloads and caches the Fyers symbol master file for a specific segment.

    Checks if a fresh (today's) version of the symbol file exists locally.
    If not, it downloads it from the Fyers public URL.

    Args:
        segment (str): The exchange segment (e.g., "NSE_CM", "NSE_FO").
        data_dir (str): The directory to store/cache the symbol files.

    Returns:
        pandas.DataFrame: A DataFrame containing all symbols for the segment,
                          or an empty DataFrame if the download fails.
    """
    if segment not in FYERS_MASTER_URLS:
        print(f"Error: Invalid segment '{segment}'. Available segments are: {list(FYERS_MASTER_URLS.keys())}")
        return pd.DataFrame()

    os.makedirs(data_dir, exist_ok=True)
    
    today_str = date.today().strftime('%Y-%m-%d')
    file_path = os.path.join(data_dir, f"{segment}_{today_str}.csv")

    if os.path.exists(file_path):
        print(f"Loading cached symbols for {segment} from {file_path}")
        return pd.read_csv(file_path)

    # File doesn't exist, so download it
    print(f"Downloading latest symbols for {segment}...")
    url = FYERS_MASTER_URLS[segment]
    try:
        response = requests.get(url, timeout=15)
        response.raise_for_status()

        csv_data = StringIO(response.text)

        # Different segments have different CSV formats.
        if segment in ["NSE_FO", "NSE_CD"]:
            # Derivatives files (FO, CD) from Fyers do not contain a header row.
            df = pd.read_csv(csv_data, header=None, names=DERIVATIVE_COLUMNS)
        else:
            # Equity files (CM) have a header row on the first line.
            df = pd.read_csv(csv_data)

        # Clean up column names by stripping leading/trailing whitespace
        df.columns = df.columns.str.strip()
        
        df.to_csv(file_path, index=False)
        print(f"Successfully downloaded and cached symbols to {file_path}")

        # Clean up old files for the same segment
        for item in os.listdir(data_dir):
            if item.startswith(segment) and item != os.path.basename(file_path):
                os.remove(os.path.join(data_dir, item))
        
        return df
    except requests.RequestException as e:
        print(f"Error downloading {segment} symbols: {e}")
        return pd.DataFrame()