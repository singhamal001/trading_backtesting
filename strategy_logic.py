# forex_backtester_cli/strategy_logic.py
import pandas as pd
import numpy as np

DEBUG_STRATEGY_LOGIC = True 

def get_market_structure_and_recent_swings(df_with_swings: pd.DataFrame, current_eval_time: pd.Timestamp):
    """
    Analyzes swings confirmed *before or at current_eval_time* to determine market structure.
    """
    if DEBUG_STRATEGY_LOGIC: print(f"  DEBUG: get_market_structure called for time <= {current_eval_time} with full df shape {df_with_swings.shape}")
    
    # Filter swings that occurred at or before the current evaluation time
    confirmed_swings = df_with_swings[df_with_swings.index <= current_eval_time]
    swing_highs = confirmed_swings[confirmed_swings['swing_high'].notna()]
    swing_lows = confirmed_swings[confirmed_swings['swing_low'].notna()]

    if DEBUG_STRATEGY_LOGIC:
        print(f"    Considering swings up to {current_eval_time}: Found {len(swing_highs)} swing highs, {len(swing_lows)} swing lows.")
        if not swing_highs.empty: print(f"    Latest considered SH: {swing_highs.iloc[-1]['swing_high']:.5f} at {swing_highs.index[-1]}")
        if not swing_lows.empty: print(f"    Latest considered SL: {swing_lows.iloc[-1]['swing_low']:.5f} at {swing_lows.index[-1]}")

    if swing_highs.empty or swing_lows.empty or len(swing_highs) < 2 or len(swing_lows) < 2:
        if DEBUG_STRATEGY_LOGIC: print("    Not enough confirmed swings (need >=2 of each type) up to this point for structure determination.")
        return "undetermined", None, None, None, None

    last_sh = swing_highs.iloc[-1]
    second_last_sh = swing_highs.iloc[-2]
    last_sl = swing_lows.iloc[-1]
    second_last_sl = swing_lows.iloc[-2]

    market_structure = "ranging" 

    if last_sh['swing_high'] > second_last_sh['swing_high'] and \
       last_sl['swing_low'] > second_last_sl['swing_low']:
        if last_sh.name > last_sl.name and last_sl.name > second_last_sh.name:
             market_structure = "uptrend"
    elif last_sh['swing_high'] < second_last_sh['swing_high'] and \
         last_sl['swing_low'] < second_last_sl['swing_low']:
        if last_sl.name > last_sh.name and last_sh.name > second_last_sl.name:
            market_structure = "downtrend"
    
    if DEBUG_STRATEGY_LOGIC: print(f"    Determined structure based on swings up to {current_eval_time}: {market_structure}")
    
    # For CHoCH, we need the last structural point of the identified trend.
    # If uptrend, it's the last HL (which would be `last_sl` if structure is correctly identified).
    # If downtrend, it's the last LH (which would be `last_sh`).
    # This part is crucial and might need more advanced logic to pick the *correct* structural HL/LH.
    # For now, we return the latest identified swings from the filtered set.
    
    return market_structure, \
           last_sh['swing_high'], last_sh.name, \
           last_sl['swing_low'], last_sl.name


def detect_choch(df_ohlc_with_swings: pd.DataFrame, current_candle_index: int, break_type: str = "close"):
    current_candle = df_ohlc_with_swings.iloc[current_candle_index]
    current_time = current_candle.name 
    
    # The structure (HL or LH to be broken) must be established *before* the current candle's time.
    # So, we evaluate structure based on swings confirmed up to the *previous* candle's time.
    time_for_structure_eval = df_ohlc_with_swings.index[current_candle_index - 1] if current_candle_index > 0 else df_ohlc_with_swings.index[0]

    if DEBUG_STRATEGY_LOGIC: print(f"\nDEBUG: detect_choch for current candle at {current_time} (index {current_candle_index}). Evaluating structure up to {time_for_structure_eval}.")

    if current_candle_index < 1: return None, None, None # Should be handled by backtester loop start
    
    # Get structure based on swings confirmed up to the *previous* candle's time.
    structure, struct_sh_price, struct_sh_time, struct_sl_price, struct_sl_time = \
        get_market_structure_and_recent_swings(df_ohlc_with_swings, time_for_structure_eval)

    if DEBUG_STRATEGY_LOGIC:
        print(f"  CHoCH Check: Current Candle Time: {current_time}")
        print(f"  Evaluated Structure (up to {time_for_structure_eval}): {structure}")
        if struct_sh_time: print(f"  Relevant Structural SH for break check: {struct_sh_price:.5f} at {struct_sh_time}")
        if struct_sl_time: print(f"  Relevant Structural SL for break check: {struct_sl_price:.5f} at {struct_sl_time}")

    # Bearish CHoCH: Was in uptrend, current candle breaks the last significant Higher Low (struct_sl_price)
    if structure == "uptrend" and struct_sl_price is not None: # struct_sl_time will be <= time_for_structure_eval
        point_to_break = struct_sl_price
        if DEBUG_STRATEGY_LOGIC: print(f"    Potential Bearish CHoCH: Uptrend context. Watching HL at {point_to_break:.5f} (time {struct_sl_time}). Current close: {current_candle['close']:.5f}, low: {current_candle['low']:.5f}")
        if break_type == "close":
            if current_candle['close'] < point_to_break:
                if DEBUG_STRATEGY_LOGIC: print(f"      >>> BEARISH CHOCH by CLOSE confirmed!")
                return "bearish_choch", point_to_break, current_time
        elif break_type == "wick":
            if current_candle['low'] < point_to_break:
                if DEBUG_STRATEGY_LOGIC: print(f"      >>> BEARISH CHOCH by WICK confirmed!")
                return "bearish_choch", point_to_break, current_time

    # Bullish CHoCH: Was in downtrend, current candle breaks the last significant Lower High (struct_sh_price)
    elif structure == "downtrend" and struct_sh_price is not None:
        point_to_break = struct_sh_price
        if DEBUG_STRATEGY_LOGIC: print(f"    Potential Bullish CHoCH: Downtrend context. Watching LH at {point_to_break:.5f} (time {struct_sh_time}). Current close: {current_candle['close']:.5f}, high: {current_candle['high']:.5f}")
        if break_type == "close":
            if current_candle['close'] > point_to_break:
                if DEBUG_STRATEGY_LOGIC: print(f"      >>> BULLISH CHOCH by CLOSE confirmed!")
                return "bullish_choch", point_to_break, current_time
        elif break_type == "wick":
            if current_candle['high'] > point_to_break:
                if DEBUG_STRATEGY_LOGIC: print(f"      >>> BULLISH CHOCH by WICK confirmed!")
                return "bullish_choch", point_to_break, current_time
                
    return None, None, None

# LTF function also needs to be adjusted similarly if it uses get_market_structure_and_recent_swings
def detect_ltf_structure_change(df_ltf_ha_with_swings: pd.DataFrame, 
                                current_ltf_candle_index: int, 
                                required_direction: str, 
                                break_type: str = "close"):
    current_ltf_candle = df_ltf_ha_with_swings.iloc[current_ltf_candle_index]
    current_ltf_time = current_ltf_candle.name
    
    time_for_ltf_structure_eval = df_ltf_ha_with_swings.index[current_ltf_candle_index - 1] if current_ltf_candle_index > 0 else df_ltf_ha_with_swings.index[0]

    if DEBUG_STRATEGY_LOGIC: print(f"  DEBUG: detect_ltf_structure_change for HA candle at {current_ltf_time} (index {current_ltf_candle_index}), required: {required_direction}. Evaluating structure up to {time_for_ltf_structure_eval}")

    if current_ltf_candle_index < 1: return None, None, None

    ltf_structure, last_ltf_sh_price, last_ltf_sh_time, last_ltf_sl_price, last_ltf_sl_time = \
        get_market_structure_and_recent_swings(df_ltf_ha_with_swings, time_for_ltf_structure_eval) # Pass full df and eval time

    # ... (rest of LTF logic remains similar, checking against the returned structural points) ...
    if DEBUG_STRATEGY_LOGIC:
        print(f"    LTF Structure (up to {time_for_ltf_structure_eval}): {ltf_structure}")
        if last_ltf_sh_time: print(f"    LTF Relevant Structural SH: {last_ltf_sh_price:.5f} at {last_ltf_sh_time}")
        if last_ltf_sl_time: print(f"    LTF Relevant Structural SL: {last_ltf_sl_price:.5f} at {last_ltf_sl_time}")

    if required_direction == "bullish":
        # For bullish confirmation, we could be breaking a previous LH (CHoCH) or a previous SH (BOS)
        # The `last_ltf_sh_price` from `get_market_structure_and_recent_swings` is the latest SH.
        # If ltf_structure was 'downtrend', this `last_ltf_sh_price` is the LH to break for a CHoCH.
        # If ltf_structure was 'uptrend', this `last_ltf_sh_price` is the SH to break for a BOS.
        point_to_break = last_ltf_sh_price 
        if point_to_break is not None: # last_ltf_sh_time will be <= time_for_ltf_structure_eval
            if DEBUG_STRATEGY_LOGIC: print(f"      LTF Bullish Check: Watching level {point_to_break:.5f}. Current HA_close: {current_ltf_candle['ha_close']:.5f}, HA_high: {current_ltf_candle['ha_high']:.5f}")
            if break_type == "close" and current_ltf_candle['ha_close'] > point_to_break:
                signal = "ltf_bullish_confirm_choch" if ltf_structure == "downtrend" or ltf_structure == "ranging" else "ltf_bullish_confirm_bos"
                if DEBUG_STRATEGY_LOGIC: print(f"        >>> LTF BULLISH CONFIRM by CLOSE ({signal})!")
                return signal, point_to_break, current_ltf_time
            elif break_type == "wick" and current_ltf_candle['ha_high'] > point_to_break:
                signal = "ltf_bullish_confirm_choch" if ltf_structure == "downtrend" or ltf_structure == "ranging" else "ltf_bullish_confirm_bos"
                if DEBUG_STRATEGY_LOGIC: print(f"        >>> LTF BULLISH CONFIRM by WICK ({signal})!")
                return signal, point_to_break, current_ltf_time

    elif required_direction == "bearish":
        point_to_break = last_ltf_sl_price
        if point_to_break is not None:
            if DEBUG_STRATEGY_LOGIC: print(f"      LTF Bearish Check: Watching level {point_to_break:.5f}. Current HA_close: {current_ltf_candle['ha_close']:.5f}, HA_low: {current_ltf_candle['ha_low']:.5f}")
            if break_type == "close" and current_ltf_candle['ha_close'] < point_to_break:
                signal = "ltf_bearish_confirm_choch" if ltf_structure == "uptrend" or ltf_structure == "ranging" else "ltf_bearish_confirm_bos"
                if DEBUG_STRATEGY_LOGIC: print(f"        >>> LTF BEARISH CONFIRM by CLOSE ({signal})!")
                return signal, point_to_break, current_ltf_time
            elif break_type == "wick" and current_ltf_candle['ha_low'] < point_to_break:
                signal = "ltf_bearish_confirm_choch" if ltf_structure == "uptrend" or ltf_structure == "ranging" else "ltf_bearish_confirm_bos"
                if DEBUG_STRATEGY_LOGIC: print(f"        >>> LTF BEARISH CONFIRM by WICK ({signal})!")
                return signal, point_to_break, current_ltf_time
                
    return None, None, None


def detect_ltf_structure_change(df_ltf_ha_with_swings: pd.DataFrame, 
                                current_ltf_candle_index: int, 
                                required_direction: str, 
                                break_type: str = "close"):
    current_ltf_candle = df_ltf_ha_with_swings.iloc[current_ltf_candle_index]
    current_ltf_time = current_ltf_candle.name
    
    # Determine the time up to which structure should be evaluated (previous candle's time)
    time_for_ltf_structure_eval = df_ltf_ha_with_swings.index[current_ltf_candle_index - 1] if current_ltf_candle_index > 0 else df_ltf_ha_with_swings.index[0]

    if DEBUG_STRATEGY_LOGIC: print(f"  DEBUG: detect_ltf_structure_change for HA candle at {current_ltf_time} (index {current_ltf_candle_index}), required: {required_direction}. Evaluating structure up to {time_for_ltf_structure_eval}")

    if current_ltf_candle_index < 1: return None, None, None

    # Call get_market_structure_and_recent_swings with the current_eval_time argument
    ltf_structure, last_ltf_sh_price, last_ltf_sh_time, last_ltf_sl_price, last_ltf_sl_time = \
        get_market_structure_and_recent_swings(df_ltf_ha_with_swings, time_for_ltf_structure_eval) # <<< CORRECTED CALL

    if DEBUG_STRATEGY_LOGIC:
        print(f"    LTF Structure (up to {time_for_ltf_structure_eval}): {ltf_structure}")
        if last_ltf_sh_time: print(f"    LTF Relevant Structural SH: {last_ltf_sh_price:.5f} at {last_ltf_sh_time}")
        if last_ltf_sl_time: print(f"    LTF Relevant Structural SL: {last_ltf_sl_price:.5f} at {last_ltf_sl_time}")

    if required_direction == "bullish":
        point_to_break = last_ltf_sh_price 
        if point_to_break is not None: 
            if DEBUG_STRATEGY_LOGIC: print(f"      LTF Bullish Check: Watching level {point_to_break:.5f}. Current HA_close: {current_ltf_candle['ha_close']:.5f}, HA_high: {current_ltf_candle['ha_high']:.5f}")
            if break_type == "close" and current_ltf_candle['ha_close'] > point_to_break:
                signal = "ltf_bullish_confirm_choch" if ltf_structure == "downtrend" or ltf_structure == "ranging" else "ltf_bullish_confirm_bos"
                if DEBUG_STRATEGY_LOGIC: print(f"        >>> LTF BULLISH CONFIRM by CLOSE ({signal})!")
                return signal, point_to_break, current_ltf_time
            elif break_type == "wick" and current_ltf_candle['ha_high'] > point_to_break:
                signal = "ltf_bullish_confirm_choch" if ltf_structure == "downtrend" or ltf_structure == "ranging" else "ltf_bullish_confirm_bos"
                if DEBUG_STRATEGY_LOGIC: print(f"        >>> LTF BULLISH CONFIRM by WICK ({signal})!")
                return signal, point_to_break, current_ltf_time

    elif required_direction == "bearish":
        point_to_break = last_ltf_sl_price
        if point_to_break is not None:
            if DEBUG_STRATEGY_LOGIC: print(f"      LTF Bearish Check: Watching level {point_to_break:.5f}. Current HA_close: {current_ltf_candle['ha_close']:.5f}, HA_low: {current_ltf_candle['ha_low']:.5f}")
            if break_type == "close" and current_ltf_candle['ha_close'] < point_to_break:
                signal = "ltf_bearish_confirm_choch" if ltf_structure == "uptrend" or ltf_structure == "ranging" else "ltf_bearish_confirm_bos"
                if DEBUG_STRATEGY_LOGIC: print(f"        >>> LTF BEARISH CONFIRM by CLOSE ({signal})!")
                return signal, point_to_break, current_ltf_time
            elif break_type == "wick" and current_ltf_candle['ha_low'] < point_to_break:
                signal = "ltf_bearish_confirm_choch" if ltf_structure == "uptrend" or ltf_structure == "ranging" else "ltf_bearish_confirm_bos"
                if DEBUG_STRATEGY_LOGIC: print(f"        >>> LTF BEARISH CONFIRM by WICK ({signal})!")
                return signal, point_to_break, current_ltf_time
                
    return None, None, None


# --- Example Usage / Test Section ---
if __name__ == '__main__':
    print("Testing strategy_logic.py...")
    # We need sample data with swings to test this properly.
    # Let's use the data fetching from previous steps.
    from data_handler import fetch_historical_data, shutdown_mt5_connection
    from utils import identify_swing_points
    from heikin_ashi import calculate_heikin_ashi
    import config # To get timeframe constants and other params

    symbol_to_test = config.SYMBOLS[0]
    # Use a slightly longer range to ensure enough swings for structure
    start_date_test = "2025-02-01" 
    end_date_test = "2025-02-28" # One month

    print(f"\nFetching HTF data for {symbol_to_test} for structure analysis...")
    htf_data = fetch_historical_data(symbol_to_test, config.HTF_MT5, start_date_test, end_date_test)
    
    if htf_data is not None and not htf_data.empty:
        htf_data_with_swings = identify_swing_points(
            htf_data, 
            config.N_BARS_LEFT_RIGHT_FOR_SWING_HTF, 
            config.N_BARS_LEFT_RIGHT_FOR_SWING_HTF
        )
        print(f"HTF data with swings (shape): {htf_data_with_swings.shape}")

        # Test get_market_structure_and_recent_swings
        # Test on a few points in the data
        if len(htf_data_with_swings) > config.N_BARS_LEFT_RIGHT_FOR_SWING_HTF * 2 + 10: # Ensure enough data
            test_indices = [
                len(htf_data_with_swings) // 2, # Middle
                len(htf_data_with_swings) - config.N_BARS_LEFT_RIGHT_FOR_SWING_HTF - 2 # Near end
            ]
            for idx_loc in test_indices:
                print(f"\n--- Testing structure at HTF index (iloc): {idx_loc} (Time: {htf_data_with_swings.index[idx_loc]}) ---")
                structure, sh_p, sh_t, sl_p, sl_t = get_market_structure_and_recent_swings(
                    htf_data_with_swings.iloc[:idx_loc+1] # Pass data up to that point
                )
                print(f"Market Structure: {structure}")
                print(f"Last SH: {sh_p} at {sh_t}, Last SL: {sl_p} at {sl_t}")

                # Test CHoCH detection (this is a conceptual test, real CHoCH needs prior trend)
                choch_type, choch_price, choch_time = detect_choch(
                    htf_data_with_swings, # Pass full df with pre-calculated swings
                    idx_loc,              # Current candle to check if it *causes* a CHoCH
                    config.BREAK_TYPE
                )
                if choch_type:
                    print(f"CHoCH Detected at current candle: {choch_type} breaking level {choch_price} at {choch_time}")
                else:
                    print("No CHoCH detected by current candle.")
        else:
            print("Not enough HTF data to run detailed structure tests.")
            
        # --- Test LTF Logic (conceptual, as we don't have a live HTF CHoCH signal here) ---
        print(f"\nFetching LTF data for {symbol_to_test} for LTF structure analysis...")
        ltf_data = fetch_historical_data(symbol_to_test, config.LTF_MT5, start_date_test, end_date_test)
        if ltf_data is not None and not ltf_data.empty:
            ltf_ha_data = calculate_heikin_ashi(ltf_data)
            ltf_ha_with_swings = identify_swing_points(
                ltf_ha_data,
                config.N_BARS_LEFT_RIGHT_FOR_SWING_LTF,
                config.N_BARS_LEFT_RIGHT_FOR_SWING_LTF,
                col_high='ha_high', col_low='ha_low'
            )
            print(f"LTF HA data with swings (shape): {ltf_ha_with_swings.shape}")

            if len(ltf_ha_with_swings) > config.N_BARS_LEFT_RIGHT_FOR_SWING_LTF * 2 + 20:
                ltf_test_idx = len(ltf_ha_with_swings) // 2
                print(f"\n--- Testing LTF structure at LTF HA index (iloc): {ltf_test_idx} (Time: {ltf_ha_with_swings.index[ltf_test_idx]}) ---")
                
                # Simulate a required bullish direction
                ltf_signal, ltf_price, ltf_time = detect_ltf_structure_change(
                    ltf_ha_with_swings, ltf_test_idx, "bullish", config.BREAK_TYPE
                )
                if ltf_signal:
                    print(f"LTF Bullish Confirm: {ltf_signal} at level {ltf_price} at {ltf_time}")
                else:
                    print("No LTF Bullish Confirm at current LTF candle.")

                # Simulate a required bearish direction
                ltf_signal_b, ltf_price_b, ltf_time_b = detect_ltf_structure_change(
                    ltf_ha_with_swings, ltf_test_idx, "bearish", config.BREAK_TYPE
                )
                if ltf_signal_b:
                    print(f"LTF Bearish Confirm: {ltf_signal_b} at level {ltf_price_b} at {ltf_time_b}")
                else:
                    print("No LTF Bearish Confirm at current LTF candle.")
            else:
                print("Not enough LTF HA data for detailed tests.")
        else:
            print("Failed to fetch LTF data for testing.")
    else:
        print("Failed to fetch HTF data for testing.")

    shutdown_mt5_connection()
    print("\nstrategy_logic.py test finished.")