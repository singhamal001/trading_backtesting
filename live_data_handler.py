### File: X:\AmalTrading\trading_backtesting\live_data_handler.py

import MetaTrader5 as mt5
import pandas as pd
from datetime import datetime, timedelta
import pytz
import time

# Import MT5 connection details from config (can be overridden or managed separately for live)
from config import MT5_PATH, ACCOUNT_LOGIN, ACCOUNT_PASSWORD, ACCOUNT_SERVER, INTERNAL_TIMEZONE, TIMEFRAME_MAP

class LiveDataHandler:
    def __init__(self):
        self.mt5_initialized = False
        self.utc_tz = pytz.timezone(INTERNAL_TIMEZONE) # Should be 'UTC'
        if not self.initialize_mt5():
            raise ConnectionError("Failed to initialize MetaTrader 5 for LiveDataHandler.")

    def initialize_mt5(self):
        if self.mt5_initialized:
            return True
        
        init_args = []
        init_kwargs = {}
        if MT5_PATH: init_args.append(MT5_PATH)
        if ACCOUNT_LOGIN:
            init_kwargs['login'] = ACCOUNT_LOGIN
            if ACCOUNT_PASSWORD: init_kwargs['password'] = ACCOUNT_PASSWORD
            if ACCOUNT_SERVER: init_kwargs['server'] = ACCOUNT_SERVER
        
        if not mt5.initialize(*init_args, **init_kwargs):
            print(f"LiveDataHandler: MT5 initialize() failed, error code = {mt5.last_error()}")
            self.mt5_initialized = False
            return False
        
        print("LiveDataHandler: MT5 connection successful.")
        self.mt5_initialized = True
        return True

    def get_rolling_ohlc_data(self, symbol: str, timeframe_mt5: int, lookback_bars: int) -> pd.DataFrame | None:
        if not self.mt5_initialized:
            print("LiveDataHandler: MT5 not initialized.")
            if not self.initialize_mt5(): # Try to re-initialize
                return None

        try:
            # Fetch slightly more bars to ensure enough for indicators after potential gaps
            rates = mt5.copy_rates_from_pos(symbol, timeframe_mt5, 0, lookback_bars + 50) 
        except Exception as e:
            print(f"LiveDataHandler: Error fetching rates for {symbol} TF {timeframe_mt5}: {e}")
            # Attempt to re-initialize connection on error
            self.mt5_initialized = False # Force re-init on next call
            if self.initialize_mt5():
                try: # Retry fetching after re-initialization
                    rates = mt5.copy_rates_from_pos(symbol, timeframe_mt5, 0, lookback_bars + 50)
                except Exception as e_retry:
                    print(f"LiveDataHandler: Retry error fetching rates for {symbol} TF {timeframe_mt5}: {e_retry}")
                    return None
            else:
                return None


        if rates is None:
            print(f"LiveDataHandler: mt5.copy_rates_from_pos() for {symbol} TF {timeframe_mt5} returned None. Error: {mt5.last_error()}")
            return None
        
        if len(rates) == 0:
            print(f"LiveDataHandler: No data returned for {symbol} TF {timeframe_mt5}.")
            return pd.DataFrame()

        df = pd.DataFrame(rates)
        df['time'] = pd.to_datetime(df['time'], unit='s', utc=True)
        df.set_index('time', inplace=True)
        df.columns = [x.lower() for x in df.columns]
        
        standard_cols = ['open', 'high', 'low', 'close', 'tick_volume']
        df = df[[col for col in standard_cols if col in df.columns]]
        df.rename(columns={'tick_volume': 'volume'}, inplace=True, errors='ignore')

        # Return only the required number of bars from the end
        return df.iloc[-lookback_bars:] if len(df) >= lookback_bars else df

    def shutdown(self):
        if self.mt5_initialized:
            print("LiveDataHandler: Shutting down MetaTrader 5 connection.")
            mt5.shutdown()
            self.mt5_initialized = False

if __name__ == '__main__':
    print("Testing LiveDataHandler...")
    live_data = LiveDataHandler()
    if live_data.mt5_initialized:
        eurusd_m5_data = live_data.get_rolling_ohlc_data("EURUSD", TIMEFRAME_MAP["M5"], 200)
        if eurusd_m5_data is not None and not eurusd_m5_data.empty:
            print("\nEURUSD M5 Data (last 5 rows):")
            print(eurusd_m5_data.tail())
            print(f"Shape: {eurusd_m5_data.shape}")
            print(f"Latest candle time: {eurusd_m5_data.index[-1]}")
        else:
            print("Failed to fetch EURUSD M5 data.")

        usdjpy_m15_data = live_data.get_rolling_ohlc_data("USDJPY", TIMEFRAME_MAP["M15"], 100)
        if usdjpy_m15_data is not None and not usdjpy_m15_data.empty:
            print("\nUSDJPY M15 Data (last 5 rows):")
            print(usdjpy_m15_data.tail())
        else:
            print("Failed to fetch USDJPY M15 data.")
        
        live_data.shutdown()
    else:
        print("Could not initialize LiveDataHandler.")