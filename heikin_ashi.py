# forex_backtester_cli/heikin_ashi.py
import pandas as pd

def calculate_heikin_ashi(df: pd.DataFrame) -> pd.DataFrame:
    """
    Calculates Heikin Ashi candles from a DataFrame with 'open', 'high', 'low', 'close'.
    Assumes the input DataFrame index is a DatetimeIndex.
    """
    if not all(col in df.columns for col in ['open', 'high', 'low', 'close']):
        raise ValueError("Input DataFrame must contain 'open', 'high', 'low', 'close' columns.")

    ha_df = pd.DataFrame(index=df.index)

    ha_df['ha_close'] = (df['open'] + df['high'] + df['low'] + df['close']) / 4

    # Calculate initial ha_open (can be same as regular open for the first bar)
    ha_df['ha_open'] = df['open'] # Default for the first bar
    for i in range(1, len(df)):
        ha_df.loc[df.index[i], 'ha_open'] = \
            (ha_df.loc[df.index[i-1], 'ha_open'] + ha_df.loc[df.index[i-1], 'ha_close']) / 2
    
    # For the very first ha_open, if we want to strictly follow the formula,
    # we can set it to (open + close) / 2 of the first regular bar,
    # or simply use the regular open as a common practice.
    # Let's refine the first ha_open to be based on its own bar's open/close if it's the first record.
    if len(df) > 0:
         ha_df.loc[df.index[0], 'ha_open'] = (df.loc[df.index[0],'open'] + df.loc[df.index[0],'close']) / 2


    ha_df['ha_high'] = ha_df[['ha_open', 'ha_close']].join(df['high']).max(axis=1)
    ha_df['ha_low'] = ha_df[['ha_open', 'ha_close']].join(df['low']).min(axis=1)
    
    return ha_df[['ha_open', 'ha_high', 'ha_low', 'ha_close']]

# Example usage (can be removed or put in a test section later)
if __name__ == '__main__':
    # Create a sample DataFrame
    data = {
        'open': [10, 11, 10.5, 11.5, 12],
        'high': [12, 11.5, 11, 12, 12.5],
        'low': [9.5, 10, 10, 11, 11.5],
        'close': [11, 10.5, 11, 12, 11.8]
    }
    sample_df = pd.DataFrame(data, index=pd.to_datetime(['2023-01-01 00:00', 
                                                         '2023-01-01 00:05', 
                                                         '2023-01-01 00:10', 
                                                         '2023-01-01 00:15', 
                                                         '2023-01-01 00:20']))
    print("Original OHLC Data:")
    print(sample_df)
    
    ha_candles = calculate_heikin_ashi(sample_df.copy()) # Pass a copy
    print("\nHeikin Ashi Candles:")
    print(ha_candles)

    # Test with data_handler
    from data_handler import fetch_historical_data, shutdown_mt5_connection
    from config import SYMBOLS, LTF_MT5, START_DATE_STR, END_DATE_STR
    
    if LTF_MT5 is not None:
        print("\nTesting Heikin Ashi with fetched MT5 data...")
        ltf_ohlc_data = fetch_historical_data(SYMBOLS[0], LTF_MT5, START_DATE_STR, "2023-01-03") # Short range
        if ltf_ohlc_data is not None and not ltf_ohlc_data.empty:
            ha_data_mt5 = calculate_heikin_ashi(ltf_ohlc_data.copy())
            print(f"\nHeikin Ashi for {SYMBOLS[0]} (first 5 rows):")
            print(ha_data_mt5.head())
        else:
            print(f"Could not fetch data for {SYMBOLS[0]} to test Heikin Ashi.")
        shutdown_mt5_connection()