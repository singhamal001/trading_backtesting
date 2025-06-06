# forex_backtester_cli/utils.py
import pandas as pd
import numpy as np

def identify_swing_points_simple(df: pd.DataFrame, n_left: int, n_right: int, 
                                 col_high: str = 'high', col_low: str = 'low') -> pd.DataFrame:
    """
    Identifies swing highs and swing lows using a simple n-bars left/right comparison.
    (This is your original function, renamed for clarity)
    """
    df_out = df.copy()
    df_out['swing_high'] = np.nan
    df_out['swing_low'] = np.nan

    # Ensure columns exist
    if col_high not in df_out.columns or col_low not in df_out.columns:
        raise ValueError(f"Columns '{col_high}' or '{col_low}' not found in DataFrame.")

    for i in range(n_left, len(df_out) - n_right):
        # Check for Swing High
        is_swing_high = True
        current_high = df_out.loc[df_out.index[i], col_high]
        for j in range(1, n_left + 1):
            if df_out.loc[df_out.index[i-j], col_high] >= current_high:
                is_swing_high = False
                break
        if not is_swing_high:
            continue
        for j in range(1, n_right + 1):
            if df_out.loc[df_out.index[i+j], col_high] > current_high: # Strictly higher on the right
                is_swing_high = False
                break
        if is_swing_high:
            df_out.loc[df_out.index[i], 'swing_high'] = current_high

        # Check for Swing Low
        is_swing_low = True
        current_low = df_out.loc[df_out.index[i], col_low]
        for j in range(1, n_left + 1):
            if df_out.loc[df_out.index[i-j], col_low] <= current_low:
                is_swing_low = False
                break
        if not is_swing_low:
            continue
        for j in range(1, n_right + 1):
            if df_out.loc[df_out.index[i+j], col_low] < current_low: # Strictly lower on the right
                is_swing_low = False
                break
        if is_swing_low:
            df_out.loc[df_out.index[i], 'swing_low'] = current_low
            
    return df_out


def identify_swing_points_zigzag(df: pd.DataFrame, zigzag_len: int,
                                 col_high: str = 'high', col_low: str = 'low') -> pd.DataFrame:
    """
    Identifies swing highs and swing lows using a ZigZag-like logic.
    A swing point is confirmed after the trend changes direction.

    Args:
        df (pd.DataFrame): Input DataFrame with high and low columns.
        zigzag_len (int): The number of bars to look back for highest high / lowest low
                           to determine potential trend changes.
        col_high (str): Name of the high column.
        col_low (str): Name of the low column.

    Returns:
        pd.DataFrame: Original DataFrame with 'swing_high' and 'swing_low' columns.
                      These columns will contain the price of the swing point or NaN.
    """
    if not all(c in df.columns for c in [col_high, col_low]):
        raise ValueError(f"DataFrame must contain '{col_high}' and '{col_low}' columns.")
    if zigzag_len < 2:
        raise ValueError("zigzag_len must be at least 2.")

    df_out = df.copy()
    df_out['swing_high'] = np.nan
    df_out['swing_low'] = np.nan

    trend = 0 # 0: undetermined, 1: up, -1: down
    last_pivot_idx = 0 
    last_pivot_price = 0.0
    
    # Temporary lists to store potential pivots before confirmation
    pivots_high_price = []
    pivots_high_idx = []
    pivots_low_price = []
    pivots_low_idx = []

    for i in range(len(df_out)):
        current_high = df_out.loc[df_out.index[i], col_high]
        current_low = df_out.loc[df_out.index[i], col_low]

        # Determine rolling highest high and lowest low
        # Ensure we don't go out of bounds at the start
        lookback_period = df_out.iloc[max(0, i - zigzag_len + 1) : i + 1]
        highest_in_len = lookback_period[col_high].max()
        lowest_in_len = lookback_period[col_low].min()

        new_trend = trend

        if trend == 0: # Initial trend determination
            if current_high == highest_in_len:
                new_trend = 1 # Tentatively up
                last_pivot_idx = i
                last_pivot_price = current_low # If trend starts up, the last pivot was a low
            elif current_low == lowest_in_len:
                new_trend = -1 # Tentatively down
                last_pivot_idx = i
                last_pivot_price = current_high # If trend starts down, the last pivot was a high
        
        elif trend == 1: # Was uptrend
            if current_low == lowest_in_len and i > last_pivot_idx: # Potential reversal down
                # The previous high (highest since last_pivot_idx) is confirmed as a swing high
                confirmed_sh_period = df_out.iloc[last_pivot_idx : i] # Don't include current bar i
                if not confirmed_sh_period.empty:
                    confirmed_sh_price = confirmed_sh_period[col_high].max()
                    confirmed_sh_idx_offset = confirmed_sh_period[col_high].idxmax()
                    # df_out.loc[confirmed_sh_idx_offset, 'swing_high'] = confirmed_sh_price
                    pivots_high_price.append(confirmed_sh_price)
                    pivots_high_idx.append(confirmed_sh_idx_offset)

                new_trend = -1
                last_pivot_idx = i # Current bar's index is start of new potential leg
                last_pivot_price = current_high # The high of this bar is the reference for the new down leg
        
        elif trend == -1: # Was downtrend
            if current_high == highest_in_len and i > last_pivot_idx: # Potential reversal up
                # The previous low (lowest since last_pivot_idx) is confirmed as a swing low
                confirmed_sl_period = df_out.iloc[last_pivot_idx : i] # Don't include current bar i
                if not confirmed_sl_period.empty:
                    confirmed_sl_price = confirmed_sl_period[col_low].min()
                    confirmed_sl_idx_offset = confirmed_sl_period[col_low].idxmin()
                    # df_out.loc[confirmed_sl_idx_offset, 'swing_low'] = confirmed_sl_price
                    pivots_low_price.append(confirmed_sl_price)
                    pivots_low_idx.append(confirmed_sl_idx_offset)
                
                new_trend = 1
                last_pivot_idx = i # Current bar's index is start of new potential leg
                last_pivot_price = current_low # The low of this bar is the reference for the new up leg
        
        trend = new_trend

    # After iterating, populate the swing_high and swing_low columns
    if pivots_high_idx:
        df_out.loc[pivots_high_idx, 'swing_high'] = pivots_high_price
    if pivots_low_idx:
        df_out.loc[pivots_low_idx, 'swing_low'] = pivots_low_price
        
    # Post-processing: Remove consecutive swings of the same type
    # e.g., if two swing highs are identified without an intervening swing low.
    # This requires iterating through the identified pivots.
    # For now, this basic version might produce some redundant swings if zigzag_len is small.
    # A more robust ZigZag would ensure alternating pivots.

    # A simple way to ensure alternating pivots:
    all_pivots = []
    for idx, price in zip(pivots_high_idx, pivots_high_price):
        all_pivots.append({'time': idx, 'price': price, 'type': 'high'})
    for idx, price in zip(pivots_low_idx, pivots_low_price):
        all_pivots.append({'time': idx, 'price': price, 'type': 'low'})
    
    if not all_pivots:
        return df_out

    all_pivots_df = pd.DataFrame(all_pivots).set_index('time').sort_index()
    
    df_out['swing_high'] = np.nan # Reset
    df_out['swing_low'] = np.nan  # Reset

    last_pivot_type = None
    for time_idx, row in all_pivots_df.iterrows():
        current_pivot_type = row['type']
        current_pivot_price = row['price']
        
        if last_pivot_type is None or current_pivot_type != last_pivot_type:
            if current_pivot_type == 'high':
                df_out.loc[time_idx, 'swing_high'] = current_pivot_price
            else: # low
                df_out.loc[time_idx, 'swing_low'] = current_pivot_price
            last_pivot_type = current_pivot_type
        else: # Same type as last, means we need to take the more extreme one
            if current_pivot_type == 'high' and current_pivot_price > df_out.loc[df_out['swing_high'].last_valid_index(), 'swing_high']:
                 df_out.loc[df_out['swing_high'].last_valid_index(), 'swing_high'] = np.nan # Remove previous less extreme
                 df_out.loc[time_idx, 'swing_high'] = current_pivot_price
            elif current_pivot_type == 'low' and current_pivot_price < df_out.loc[df_out['swing_low'].last_valid_index(), 'swing_low']:
                 df_out.loc[df_out['swing_low'].last_valid_index(), 'swing_low'] = np.nan # Remove previous less extreme
                 df_out.loc[time_idx, 'swing_low'] = current_pivot_price


    return df_out


# Example usage
if __name__ == '__main__':
    from data_handler import fetch_historical_data, shutdown_mt5_connection, initialize_mt5_connection
    from config import SYMBOLS, HTF_MT5, START_DATE_STR, END_DATE_STR
    import config # To get N_BARS_LEFT_RIGHT_FOR_SWING_HTF
    import matplotlib.pyplot as plt

    print("Testing utils.py - identify_swing_points...")
    
    # --- Test Simple Swings ---
    # print("\n--- Testing Simple Swing Identification ---")
    # if initialize_mt5_connection():
    #     htf_ohlc_data_simple = fetch_historical_data(SYMBOLS[0], HTF_MT5, START_DATE_STR, "2025-02-10")
    #     if htf_ohlc_data_simple is not None and not htf_ohlc_data_simple.empty:
    #         htf_data_with_simple_swings = identify_swing_points_simple(
    #             htf_ohlc_data_simple.copy(), 
    #             config.N_BARS_LEFT_RIGHT_FOR_SWING_HTF, 
    #             config.N_BARS_LEFT_RIGHT_FOR_SWING_HTF
    #         )
    #         print(htf_data_with_simple_swings[htf_data_with_simple_swings['swing_high'].notna() | htf_data_with_simple_swings['swing_low'].notna()].head(10))
    #     else:
    #         print(f"Could not fetch data for simple swing points test.")
    #     shutdown_mt5_connection()


    # --- Test ZigZag Swings ---
    print("\n--- Testing ZigZag Swing Identification ---")
    zigzag_param = 9 # Corresponds to zigzag_len in PineScript
    if initialize_mt5_connection():
        htf_ohlc_data_zigzag = fetch_historical_data(SYMBOLS[0], HTF_MT5, START_DATE_STR, "2025-02-28") # Longer period for zigzag
        if htf_ohlc_data_zigzag is not None and not htf_ohlc_data_zigzag.empty:
            htf_data_with_zigzag_swings = identify_swing_points_zigzag(
                htf_ohlc_data_zigzag.copy(), 
                zigzag_len=zigzag_param
            )
            print("\nHTF Data with ZigZag Swing Points (showing only rows with swings):")
            print(htf_data_with_zigzag_swings[htf_data_with_zigzag_swings['swing_high'].notna() | htf_data_with_zigzag_swings['swing_low'].notna()].head(20))

            # Optional: Plotting to visualize
            plt.figure(figsize=(15, 7))
            plt.plot(htf_data_with_zigzag_swings.index, htf_data_with_zigzag_swings['close'], label='Close Price', alpha=0.5, zorder=1)
            
            # Plot identified swings
            swing_highs_plot = htf_data_with_zigzag_swings[htf_data_with_zigzag_swings['swing_high'].notna()]
            swing_lows_plot = htf_data_with_zigzag_swings[htf_data_with_zigzag_swings['swing_low'].notna()]
            
            plt.scatter(swing_highs_plot.index, swing_highs_plot['swing_high'], color='red', marker='v', s=100, label='ZigZag High', zorder=5)
            plt.scatter(swing_lows_plot.index, swing_lows_plot['swing_low'], color='lime', marker='^', s=100, label='ZigZag Low', zorder=5)

            # Draw ZigZag lines
            all_pivots_plot = pd.concat([
                swing_highs_plot[['swing_high']].rename(columns={'swing_high': 'price'}),
                swing_lows_plot[['swing_low']].rename(columns={'swing_low': 'price'})
            ]).sort_index().dropna()

            if len(all_pivots_plot) > 1:
                 plt.plot(all_pivots_plot.index, all_pivots_plot['price'], color='blue', linestyle='-', marker='o', markersize=3, linewidth=1.5, label='ZigZag Line', zorder=3)


            plt.title(f"{SYMBOLS[0]} {config.HTF_TIMEFRAME_STR} ZigZag Swings (len={zigzag_param})")
            plt.legend()
            plt.show()
        else:
            print(f"Could not fetch data for ZigZag swing points test.")
        shutdown_mt5_connection()