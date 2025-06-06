# forex_backtester_cli/data_handler.py

import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime
import pytz # For timezone handling if needed, though MT5 gives UTC

# Import MT5 connection details from config
from config import MT5_PATH, ACCOUNT_LOGIN, ACCOUNT_PASSWORD, ACCOUNT_SERVER, INTERNAL_TIMEZONE

# Global variable to track MT5 initialization
mt5_initialized = False

def initialize_mt5_connection():
    """Initializes connection to MetaTrader 5 if not already initialized."""
    global mt5_initialized
    if mt5_initialized:
        return True

    print("Initializing MetaTrader 5 connection for data handler...")
    init_args = []
    init_kwargs = {}

    if MT5_PATH:
        init_args.append(MT5_PATH)
    if ACCOUNT_LOGIN:
        init_kwargs['login'] = ACCOUNT_LOGIN
        if ACCOUNT_PASSWORD:
            init_kwargs['password'] = ACCOUNT_PASSWORD
        if ACCOUNT_SERVER:
            init_kwargs['server'] = ACCOUNT_SERVER
    
    if not mt5.initialize(*init_args, **init_kwargs):
        print(f"MT5 initialize() failed, error code = {mt5.last_error()}")
        # Consider raising an exception or returning False to halt execution
        return False
    
    print("MT5 connection successful.")
    mt5_initialized = True
    return True

def shutdown_mt5_connection():
    """Shuts down the MetaTrader 5 connection if initialized."""
    global mt5_initialized
    if mt5_initialized:
        print("Shutting down MetaTrader 5 connection.")
        mt5.shutdown()
        mt5_initialized = False

def fetch_historical_data(symbol: str, timeframe_mt5: int, start_date_str: str, end_date_str: str) -> pd.DataFrame | None:
    """
    Fetches historical OHLCV data from MetaTrader 5.
    Timestamps in the returned DataFrame are UTC.
    """
    if not initialize_mt5_connection():
        return None

    try:
        # Convert string dates to datetime objects
        # MT5 expects naive datetime objects, assuming they are UTC for the query
        utc_tz = pytz.timezone('UTC')
        start_datetime_utc = utc_tz.localize(datetime.strptime(start_date_str, "%Y-%m-%d"))
        end_datetime_utc = utc_tz.localize(datetime.strptime(end_date_str, "%Y-%m-%d"))
        # Add one day to end_datetime_utc to include the full end_date_str
        end_datetime_utc = end_datetime_utc + pd.Timedelta(days=1)


    except ValueError as e:
        print(f"Error parsing date strings: {e}")
        return None

    print(f"Fetching data for {symbol} on timeframe {timeframe_mt5} from {start_datetime_utc} to {end_datetime_utc} (UTC)...")
    
    rates = mt5.copy_rates_range(symbol, timeframe_mt5, start_datetime_utc, end_datetime_utc)

    if rates is None:
        print(f"mt5.copy_rates_range() for {symbol} returned None. Error: {mt5.last_error()}")
        return None
    
    if len(rates) == 0:
        print(f"No data returned for {symbol} in the specified range and timeframe.")
        return pd.DataFrame() # Return empty DataFrame

    df = pd.DataFrame(rates)
    # Convert 'time' (seconds since epoch, UTC) to datetime objects and set as index
    df['time'] = pd.to_datetime(df['time'], unit='s', utc=True) # Ensure it's UTC aware
    df.set_index('time', inplace=True)
    
    # Ensure columns are lowercase for consistency
    df.columns = [x.lower() for x in df.columns]
    
    # Select standard OHLCV columns if others exist (like 'spread', 'real_volume')
    standard_cols = ['open', 'high', 'low', 'close', 'tick_volume']
    df = df[[col for col in standard_cols if col in df.columns]]
    df.rename(columns={'tick_volume': 'volume'}, inplace=True, errors='ignore')


    print(f"Successfully fetched {len(df)} bars for {symbol}.")
    return df

# Example usage (can be removed or put in a test section later)
if __name__ == '__main__':
    from config import SYMBOLS, HTF_MT5, LTF_MT5, START_DATE_STR, END_DATE_STR

    print("Testing data_handler.py...")
    
    if HTF_MT5 is not None:
        htf_data = fetch_historical_data(SYMBOLS[0], HTF_MT5, START_DATE_STR, END_DATE_STR)
        if htf_data is not None and not htf_data.empty:
            print(f"\nHTF Data for {SYMBOLS[0]} ({HTF_MT5}):")
            print(htf_data.head())
            print(htf_data.tail())
            print(f"Index Dtype: {htf_data.index.dtype}")
        else:
            print(f"Failed to fetch HTF data or data is empty for {SYMBOLS[0]}.")
    else:
        print("HTF_MT5 is not defined in config.")

    if LTF_MT5 is not None:
        ltf_data = fetch_historical_data(SYMBOLS[0], LTF_MT5, START_DATE_STR, END_DATE_STR)
        if ltf_data is not None and not ltf_data.empty:
            print(f"\nLTF Data for {SYMBOLS[0]} ({LTF_MT5}):")
            print(ltf_data.head())
            print(ltf_data.tail())
            print(f"Index Dtype: {ltf_data.index.dtype}")

        else:
            print(f"Failed to fetch LTF data or data is empty for {SYMBOLS[0]}.")
    else:
        print("LTF_MT5 is not defined in config.")

    shutdown_mt5_connection()
    print("data_handler.py test finished.")