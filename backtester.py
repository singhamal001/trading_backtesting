### File: X:\AmalTrading\trading_backtesting\backtester.py

# forex_backtester_cli/backtester.py
import pandas as pd
from datetime import timedelta 
import numpy as np 

import config
from strategies import get_strategy_class 
from plotly_plotting import plot_trade_chart_plotly 

def get_pip_size(symbol: str) -> float:
    for key_part in config.PIP_SIZE:
        if key_part in symbol.upper():
            return config.PIP_SIZE[key_part]
    if "JPY" in symbol.upper(): return 0.01 
    return 0.0001

def is_time_allowed(timestamp_utc: pd.Timestamp) -> bool:
    if not config.ENABLE_TIME_FILTER:
        return True
    time_utc = timestamp_utc.time() 
    start_h, start_m = config.ALLOWED_TRADING_UTC_START_HOUR, config.ALLOWED_TRADING_UTC_START_MINUTE
    end_h, end_m = config.ALLOWED_TRADING_UTC_END_HOUR, config.ALLOWED_TRADING_UTC_END_MINUTE
    current_time_in_minutes = time_utc.hour * 60 + time_utc.minute
    allowed_start_in_minutes = start_h * 60 + start_m
    allowed_end_in_minutes = end_h * 60 + end_m
    return allowed_start_in_minutes <= current_time_in_minutes <= allowed_end_in_minutes

def _calculate_and_set_trade_pnl(trade: dict, pip_size_for_calc: float):
    """Helper to calculate PnL for a closed trade."""
    if trade.get('exit_price') is not None and \
       trade.get('entry_price') is not None and \
       trade.get('initial_sl_price') is not None:
        
        pnl_pips_val = 0
        if trade['direction'] == 'bullish':
            pnl_pips_val = (trade['exit_price'] - trade['entry_price']) / pip_size_for_calc
        elif trade['direction'] == 'bearish':
            pnl_pips_val = (trade['entry_price'] - trade['exit_price']) / pip_size_for_calc
        
        trade['pnl_pips'] = round(pnl_pips_val, 2)
        
        risk_pips = abs(trade['entry_price'] - trade['initial_sl_price']) / pip_size_for_calc
        if risk_pips > 1e-9: 
            trade['pnl_R'] = round(pnl_pips_val / risk_pips, 2)
        else:
            trade['pnl_R'] = 0.0 
            print(f"    Warning: Trade ID {trade.get('id')} had zero or tiny initial risk (Entry: {trade.get('entry_price')}, Initial SL: {trade.get('initial_sl_price')}, RiskPips: {risk_pips:.4f}). PnL R set to 0.")
    else:
        missing_keys = []
        if trade.get('exit_price') is None: missing_keys.append('exit_price')
        if trade.get('entry_price') is None: missing_keys.append('entry_price')
        if trade.get('initial_sl_price') is None: missing_keys.append('initial_sl_price')
        print(f"    DEBUG_TRADE_PNL_R: Trade ID {trade.get('id')} missing price data ({', '.join(missing_keys)}) for PnL R calc during closure.")
        trade['pnl_pips'] = 0.0
        trade['pnl_R'] = 0.0


def run_backtest(
    symbol: str,
    htf_data_with_swings: pd.DataFrame, 
    ltf_data_original_ohlc: pd.DataFrame, 
    ltf_data_ha_with_swings: pd.DataFrame, 
    strategy_name: str, 
    strategy_custom_params: dict,
    session_results_path: str,
    starting_trade_id: int 
    ):
    print(f"\n--- Starting Backtest for {symbol} using Strategy: {strategy_name} (Global Start ID: {starting_trade_id}) ---")
    trades_log = []
    active_trade = None
    pip_size_local = get_pip_size(symbol) 
    sl_buffer_price = config.SL_BUFFER_PIPS * pip_size_local 
    current_overall_trade_id = starting_trade_id -1 

    StrategyClass = get_strategy_class(strategy_name)
    if not StrategyClass:
        print(f"ERROR: Strategy '{strategy_name}' not found.")
        return [], starting_trade_id -1 
    
    common_strategy_params = {
        "symbol": symbol, "pip_size": pip_size_local, "sl_buffer_price": sl_buffer_price,
        "htf_timeframe_str": config.HTF_TIMEFRAME_STR, "ltf_timeframe_str": config.LTF_TIMEFRAME_STR,
    }
    strategy_instance = StrategyClass(strategy_custom_params, common_strategy_params)
    
    htf_arg_for_prepare = htf_data_with_swings.copy()
    
    ltf_arg_for_prepare = None
    if strategy_name in ["ChochHa", "ChochHaSma"]:
        ltf_arg_for_prepare = ltf_data_ha_with_swings.copy()
    elif strategy_name in ["ZLSMAWithFilters", "HAAlligatorMACD", "HAAdaptiveMACD"]: 
        ltf_arg_for_prepare = ltf_data_original_ohlc.copy()
    else: 
        print(f"Warning: LTF data preparation approach not explicitly defined for strategy '{strategy_name}'. Defaulting to original OHLC.")
        ltf_arg_for_prepare = ltf_data_original_ohlc.copy()


    prepared_htf_data, prepared_ltf_data_from_strategy = strategy_instance.prepare_data(
        htf_arg_for_prepare, ltf_arg_for_prepare   
    )
    
    min_htf_len_for_swings = (config.ZIGZAG_LEN_HTF if config.SWING_IDENTIFICATION_METHOD == "zigzag" 
                              else config.N_BARS_LEFT_RIGHT_FOR_SWING_HTF) + 10 # Added buffer
    
    if len(prepared_htf_data) < min_htf_len_for_swings:
        print(f"Warning: Not enough HTF data ({len(prepared_htf_data)} bars) for {symbol} to start backtest with offset {min_htf_len_for_swings}. Skipping symbol.")
        return [], starting_trade_id -1
        
    start_offset_htf = min_htf_len_for_swings


    for i in range(start_offset_htf, len(prepared_htf_data)):
        current_htf_candle_time = prepared_htf_data.index[i]
        manage_trade_until_time = prepared_htf_data.index[i+1] if i + 1 < len(prepared_htf_data) else ltf_data_original_ohlc.index[-1]

        if active_trade:
            ltf_management_slice = ltf_data_original_ohlc[
                (ltf_data_original_ohlc.index > active_trade['last_checked_ltf_time']) &
                (ltf_data_original_ohlc.index <= manage_trade_until_time)
            ]
            for ltf_idx, ltf_candle in ltf_management_slice.iterrows():
                active_trade['last_checked_ltf_time'] = ltf_idx
                current_potential_R = 0.0 

                if active_trade.get('max_R_achieved_for_analysis', 0.0) < 5.0 or active_trade['status'] == 'open':
                    risk_in_price = abs(active_trade['entry_price'] - active_trade['initial_sl_price'])
                    if risk_in_price > 1e-9: 
                        if active_trade['direction'] == 'bullish': current_potential_R = (ltf_candle['high'] - active_trade['entry_price']) / risk_in_price
                        elif active_trade['direction'] == 'bearish': current_potential_R = (active_trade['entry_price'] - ltf_candle['low']) / risk_in_price
                        active_trade['max_R_achieved_for_analysis'] = max(active_trade.get('max_R_achieved_for_analysis', 0.0), min(current_potential_R, 5.0))
                        
                        r_levels_to_check_for_analysis = strategy_instance.get_r_levels_to_track() + [3.5, 4.0, 4.5, 5.0]
                        r_levels_to_check_for_analysis = sorted(list(set(r_levels_to_check_for_analysis)))
                        for r_target in r_levels_to_check_for_analysis:
                            if r_target > 5.0: continue 
                            if not active_trade.get(f'{r_target:.1f}R_achieved', False) and current_potential_R >= r_target:
                                active_trade[f'{r_target:.1f}R_achieved'] = True
                
                if config.ENABLE_BREAKEVEN_SL and \
                   active_trade['status'] == 'open' and \
                   not active_trade.get('sl_moved_to_be', False) and \
                   current_potential_R >= config.BE_SL_TRIGGER_R:
                    
                    entry_price_be = active_trade['entry_price']
                    sl_from_recent_hl = None
                    
                    try:
                        current_ltf_iloc = ltf_data_original_ohlc.index.get_loc(ltf_idx)
                        start_idx_be_lookback = max(0, current_ltf_iloc - config.BE_SL_LOOKBACK_PERIOD)
                        ltf_slice_for_be_sl = ltf_data_original_ohlc.iloc[start_idx_be_lookback : current_ltf_iloc]

                        if not ltf_slice_for_be_sl.empty:
                            if active_trade['direction'] == 'bullish':
                                recent_low = ltf_slice_for_be_sl['low'].min()
                                sl_from_recent_hl = recent_low - sl_buffer_price 
                            elif active_trade['direction'] == 'bearish':
                                recent_high = ltf_slice_for_be_sl['high'].max()
                                sl_from_recent_hl = recent_high + sl_buffer_price
                    except Exception as e_be_slice:
                        print(f"    Warning: Could not get slice for BE SL recent H/L calc for Trade {active_trade['id']}: {e_be_slice}")

                    sl_from_fixed_pips_dist = config.BE_SL_FIXED_PIPS * pip_size_local
                    if active_trade['direction'] == 'bullish':
                        sl_from_fixed_pips_level = entry_price_be - sl_from_fixed_pips_dist
                    else: 
                        sl_from_fixed_pips_level = entry_price_be + sl_from_fixed_pips_dist

                    risk_from_hl = abs(entry_price_be - sl_from_recent_hl) if sl_from_recent_hl is not None else float('inf')
                    risk_from_fixed = sl_from_fixed_pips_dist 

                    chosen_aggressive_sl_level = None
                    if sl_from_recent_hl is not None and risk_from_hl < risk_from_fixed:
                        chosen_aggressive_sl_level = sl_from_recent_hl
                    else:
                        chosen_aggressive_sl_level = sl_from_fixed_pips_level
                    
                    new_be_sl_price = None
                    if active_trade['direction'] == 'bullish':
                        new_be_sl_price = max(entry_price_be, chosen_aggressive_sl_level)
                    elif active_trade['direction'] == 'bearish':
                        new_be_sl_price = min(entry_price_be, chosen_aggressive_sl_level)

                    if new_be_sl_price is not None:
                        active_trade['sl_price'] = new_be_sl_price
                        active_trade['sl_moved_to_be'] = True
                        active_trade['status_info'] = active_trade.get('status_info', "") + f";BE@{config.BE_SL_TRIGGER_R:.1f}R"
                        print(f"    Trade SL to BE: ID {active_trade['id']} new SL {new_be_sl_price:.5f} at {ltf_idx} ({config.BE_SL_TRIGGER_R:.1f}R achieved)")

                if active_trade['status'] == 'open': 
                    if active_trade['direction'] == 'bullish':
                        if ltf_candle['low'] <= active_trade['sl_price']: 
                            active_trade['status'] = 'closed_sl'
                            if active_trade.get('sl_moved_to_be', False): 
                                active_trade['status'] = 'closed_sl_be' 
                            active_trade['exit_time'] = ltf_idx; active_trade['exit_price'] = active_trade['sl_price']
                            _calculate_and_set_trade_pnl(active_trade, pip_size_local) 
                            print(f"    Trade SL: ID {active_trade['id']} at {ltf_idx} Price: {active_trade['sl_price']:.5f} (Status: {active_trade['status']})"); break 
                        elif ltf_candle['high'] >= active_trade['tp_price']: 
                            active_trade['status'] = 'closed_tp'; active_trade['exit_time'] = ltf_idx; active_trade['exit_price'] = active_trade['tp_price']
                            _calculate_and_set_trade_pnl(active_trade, pip_size_local) 
                            for r_target in strategy_instance.get_r_levels_to_track():
                                if r_target <= strategy_instance.tp_rr_ratio: active_trade[f'{r_target:.1f}R_achieved'] = True
                            active_trade['max_R_achieved_for_analysis'] = max(active_trade.get('max_R_achieved_for_analysis', 0.0), min(strategy_instance.tp_rr_ratio, 5.0))
                            print(f"    Trade TP: ID {active_trade['id']} at {ltf_idx} Price: {active_trade['tp_price']:.5f}")
                    elif active_trade['direction'] == 'bearish':
                        if ltf_candle['high'] >= active_trade['sl_price']: 
                            active_trade['status'] = 'closed_sl'
                            if active_trade.get('sl_moved_to_be', False): 
                                active_trade['status'] = 'closed_sl_be' 
                            active_trade['exit_time'] = ltf_idx; active_trade['exit_price'] = active_trade['sl_price']
                            _calculate_and_set_trade_pnl(active_trade, pip_size_local) 
                            print(f"    Trade SL: ID {active_trade['id']} at {ltf_idx} Price: {active_trade['sl_price']:.5f} (Status: {active_trade['status']})"); break
                        elif ltf_candle['low'] <= active_trade['tp_price']: 
                            active_trade['status'] = 'closed_tp'; active_trade['exit_time'] = ltf_idx; active_trade['exit_price'] = active_trade['tp_price']
                            _calculate_and_set_trade_pnl(active_trade, pip_size_local) 
                            for r_target in strategy_instance.get_r_levels_to_track():
                                 if r_target <= strategy_instance.tp_rr_ratio: active_trade[f'{r_target:.1f}R_achieved'] = True
                            active_trade['max_R_achieved_for_analysis'] = max(active_trade.get('max_R_achieved_for_analysis', 0.0), min(strategy_instance.tp_rr_ratio, 5.0))
                            print(f"    Trade TP: ID {active_trade['id']} at {ltf_idx} Price: {active_trade['tp_price']:.5f}")
            
            if active_trade['status'] != 'open': active_trade = None
        
        if not active_trade:
            htf_signal = strategy_instance.check_htf_condition(prepared_htf_data, i)
            
            if htf_signal:
                level_broken_val = htf_signal.get('level_broken') 
                level_broken_str = f"{level_broken_val:.5f}" if isinstance(level_broken_val, (int, float)) else str(level_broken_val if level_broken_val is not None else 'N/A')
                
                # Conditional printing for HTF signal to reduce noise for certain strategies
                print_htf_signal = True
                if strategy_name == "HAAlligatorMACD" and htf_signal.get('type') == "ha_alligator_macd_htf_generic_go":
                    print_htf_signal = False # Example: Suppress generic pass-through for this strategy
                if strategy_name == "HAAdaptiveMACD" and "choch_for_ha_adaptive_macd" in htf_signal.get('type',''): # Print if it's the CHoCH signal
                    print_htf_signal = True 
                
                if print_htf_signal:
                     print(f"\n{current_htf_candle_time}: HTF Signal ({htf_signal.get('type','UnknownType')}) detected for {strategy_name}. Level: {level_broken_str}")

                ltf_search_start_time = current_htf_candle_time 
                ltf_search_window_end_time = prepared_htf_data.index[i+1] if i + 1 < len(prepared_htf_data) else current_htf_candle_time + config.HTF_TIMEDELTA
                
                relevant_ltf_segment_for_signal = prepared_ltf_data_from_strategy[
                    (prepared_ltf_data_from_strategy.index >= ltf_search_start_time) & 
                    (prepared_ltf_data_from_strategy.index < ltf_search_window_end_time) 
                ]
                if relevant_ltf_segment_for_signal.empty: continue

                for j_ltf_search_idx_val, _ in relevant_ltf_segment_for_signal.iterrows():
                    try:
                        original_ltf_iloc = prepared_ltf_data_from_strategy.index.get_loc(j_ltf_search_idx_val)
                    except KeyError:
                        continue 

                    current_ltf_processed_candle_time = prepared_ltf_data_from_strategy.index[original_ltf_iloc]
                    if not is_time_allowed(current_ltf_processed_candle_time): continue

                    ltf_entry_signal = strategy_instance.check_ltf_entry_signal(
                        prepared_ltf_data_from_strategy, original_ltf_iloc, htf_signal
                    )

                    if ltf_entry_signal:
                        entry_candle_iloc = original_ltf_iloc + 1
                        if entry_candle_iloc < len(ltf_data_original_ohlc): 
                            entry_time = ltf_data_original_ohlc.index[entry_candle_iloc]
                            
                            if entry_time >= ltf_search_window_end_time :
                                continue

                            if entry_time not in ltf_data_original_ohlc.index: continue 
                            entry_price = ltf_data_original_ohlc.loc[entry_time]['open']
                            
                            sl_price, tp_price = strategy_instance.calculate_sl_tp(
                                entry_price, entry_time, prepared_ltf_data_from_strategy, 
                                ltf_entry_signal, htf_signal
                            )
                            if sl_price is None or tp_price is None: break 

                            # --- NEW: REVERSAL LOGIC ---
                            final_direction = ltf_entry_signal["direction"]
                            final_sl_price = sl_price_orig
                            final_tp_price = tp_price_orig
                            trade_comment = ""
                    
                            if config.REVERSE_TRADES:
                                print(f"    REVERSING TRADE SIGNAL for {symbol} at {entry_time}")
                                final_direction = "bearish" if ltf_entry_signal["direction"] == "bullish" else "bullish"
                                final_sl_price = tp_price_orig  # Original TP becomes the new SL
                                final_tp_price = sl_price_orig  # Original SL becomes the new TP
                                trade_comment = "REVERSED"
                    
                            # --- END OF REVERSAL LOGIC ---

                            current_overall_trade_id += 1 
                            print(f"    {entry_time}: LTF ENTRY SIGNAL ({strategy_name})! Type: {ltf_entry_signal['type']}, Price: {entry_price:.5f}")
                            active_trade = {
                                "id": current_overall_trade_id, "symbol_specific_id": len(trades_log) + 1, 
                                "symbol": symbol, "strategy": strategy_name,
                                "entry_time": entry_time, "entry_price": entry_price,
                                "direction": ltf_entry_signal["direction"], 
                                "sl_price": sl_price, 
                                "initial_sl_price": sl_price, 
                                "tp_price": tp_price,
                                "htf_signal_details": htf_signal, "ltf_signal_details": ltf_entry_signal,
                                "status": "open", "exit_time": None, "exit_price": None,
                                "pnl_pips": 0.0, "pnl_R": 0.0, 
                                "last_checked_ltf_time": entry_time, 
                                'max_R_achieved_for_analysis': 0.0,
                                'sl_moved_to_be': False 
                            }
                            r_levels_to_init = strategy_instance.get_r_levels_to_track() + [3.5, 4.0, 4.5, 5.0]
                            for r_val in sorted(list(set(r_levels_to_init))):
                                if r_val <= 5.0: 
                                    active_trade[f'{r_val:.1f}R_achieved'] = False 
                            
                            trades_log.append(active_trade)
                            print(f"    Trade Opened: ID {active_trade['id']} ({active_trade['symbol_specific_id']}-{symbol}) {active_trade['direction']} at {active_trade['entry_price']:.5f}, SL: {active_trade['sl_price']:.5f}, TP: {active_trade['tp_price']:.5f}")
                            
                            active_trade['overall_trade_id'] = active_trade['id'] 
                            plot_trade_chart_plotly(active_trade, session_results_path) 
                            break 
                    if active_trade: break 
    
    if active_trade and active_trade['status'] == 'open':
        print(f"    Managing EOD for still open trade ID {active_trade['id']} from {active_trade['last_checked_ltf_time']}")
        ltf_final_slice = ltf_data_original_ohlc[ltf_data_original_ohlc.index > active_trade['last_checked_ltf_time']]
        for ltf_idx, ltf_candle in ltf_final_slice.iterrows(): 
            active_trade['last_checked_ltf_time'] = ltf_idx
            current_potential_R_eod = 0.0
            if active_trade.get('max_R_achieved_for_analysis', 0.0) < 5.0 or active_trade['status'] == 'open':
                risk_in_price = abs(active_trade['entry_price'] - active_trade['initial_sl_price'])
                if risk_in_price > 1e-9:
                    if active_trade['direction'] == 'bullish': current_potential_R_eod = (ltf_candle['high'] - active_trade['entry_price']) / risk_in_price
                    elif active_trade['direction'] == 'bearish': current_potential_R_eod = (active_trade['entry_price'] - ltf_candle['low']) / risk_in_price
                    active_trade['max_R_achieved_for_analysis'] = max(active_trade.get('max_R_achieved_for_analysis', 0.0), min(current_potential_R_eod, 5.0))
                    
                    r_levels_to_check_for_analysis = strategy_instance.get_r_levels_to_track() + [3.5, 4.0, 4.5, 5.0]
                    for r_target in sorted(list(set(r_levels_to_check_for_analysis))):
                        if r_target <= 5.0 and not active_trade.get(f'{r_target:.1f}R_achieved', False) and current_potential_R_eod >= r_target:
                            active_trade[f'{r_target:.1f}R_achieved'] = True
            
            if config.ENABLE_BREAKEVEN_SL and \
               active_trade['status'] == 'open' and \
               not active_trade.get('sl_moved_to_be', False) and \
               current_potential_R_eod >= config.BE_SL_TRIGGER_R:
                
                entry_price_be = active_trade['entry_price']
                sl_from_recent_hl = None
                try:
                    current_ltf_iloc = ltf_data_original_ohlc.index.get_loc(ltf_idx)
                    start_idx_be_lookback = max(0, current_ltf_iloc - config.BE_SL_LOOKBACK_PERIOD)
                    ltf_slice_for_be_sl = ltf_data_original_ohlc.iloc[start_idx_be_lookback : current_ltf_iloc]
                    if not ltf_slice_for_be_sl.empty:
                        if active_trade['direction'] == 'bullish':
                            sl_from_recent_hl = ltf_slice_for_be_sl['low'].min() - sl_buffer_price
                        elif active_trade['direction'] == 'bearish':
                            sl_from_recent_hl = ltf_slice_for_be_sl['high'].max() + sl_buffer_price
                except Exception as e_be_slice_eod:
                     print(f"    Warning: EOD Could not get slice for BE SL recent H/L calc for Trade {active_trade['id']}: {e_be_slice_eod}")

                sl_from_fixed_pips_dist = config.BE_SL_FIXED_PIPS * pip_size_local
                if active_trade['direction'] == 'bullish':
                    sl_from_fixed_pips_level = entry_price_be - sl_from_fixed_pips_dist
                else: 
                    sl_from_fixed_pips_level = entry_price_be + sl_from_fixed_pips_dist

                risk_from_hl = abs(entry_price_be - sl_from_recent_hl) if sl_from_recent_hl is not None else float('inf')
                risk_from_fixed = sl_from_fixed_pips_dist

                chosen_aggressive_sl_level = sl_from_fixed_pips_level
                if sl_from_recent_hl is not None and risk_from_hl < risk_from_fixed:
                    chosen_aggressive_sl_level = sl_from_recent_hl
                
                new_be_sl_price = None
                if active_trade['direction'] == 'bullish':
                    new_be_sl_price = max(entry_price_be, chosen_aggressive_sl_level)
                elif active_trade['direction'] == 'bearish':
                    new_be_sl_price = min(entry_price_be, chosen_aggressive_sl_level)

                if new_be_sl_price is not None:
                    active_trade['sl_price'] = new_be_sl_price
                    active_trade['sl_moved_to_be'] = True
                    active_trade['status_info'] = active_trade.get('status_info', "") + f";BE@{config.BE_SL_TRIGGER_R:.1f}R"
                    print(f"    Trade SL to BE (EOD): ID {active_trade['id']} new SL {new_be_sl_price:.5f} at {ltf_idx} ({config.BE_SL_TRIGGER_R:.1f}R achieved)")

            if active_trade['status'] == 'open': 
                if active_trade['direction'] == 'bullish': 
                    if ltf_candle['low'] <= active_trade['sl_price']: 
                        active_trade['status'] = 'closed_sl'
                        if active_trade.get('sl_moved_to_be', False): active_trade['status'] = 'closed_sl_be'
                        active_trade['exit_time'] = ltf_idx; active_trade['exit_price'] = active_trade['sl_price']
                        _calculate_and_set_trade_pnl(active_trade, pip_size_local)
                        break 
                    elif ltf_candle['high'] >= active_trade['tp_price']: 
                        active_trade['status'] = 'closed_tp'; active_trade['exit_time'] = ltf_idx; active_trade['exit_price'] = active_trade['tp_price']
                        _calculate_and_set_trade_pnl(active_trade, pip_size_local)
                        for r_target in strategy_instance.get_r_levels_to_track():
                            if r_target <= strategy_instance.tp_rr_ratio: active_trade[f'{r_target:.1f}R_achieved'] = True
                        active_trade['max_R_achieved_for_analysis'] = max(active_trade.get('max_R_achieved_for_analysis', 0.0), min(strategy_instance.tp_rr_ratio, 5.0))
                elif active_trade['direction'] == 'bearish': 
                    if ltf_candle['high'] >= active_trade['sl_price']: 
                        active_trade['status'] = 'closed_sl'
                        if active_trade.get('sl_moved_to_be', False): active_trade['status'] = 'closed_sl_be'
                        active_trade['exit_time'] = ltf_idx; active_trade['exit_price'] = active_trade['sl_price']
                        _calculate_and_set_trade_pnl(active_trade, pip_size_local)
                        break
                    elif ltf_candle['low'] <= active_trade['tp_price']: 
                        active_trade['status'] = 'closed_tp'; active_trade['exit_time'] = ltf_idx; active_trade['exit_price'] = active_trade['tp_price']
                        _calculate_and_set_trade_pnl(active_trade, pip_size_local)
                        for r_target in strategy_instance.get_r_levels_to_track():
                            if r_target <= strategy_instance.tp_rr_ratio: active_trade[f'{r_target:.1f}R_achieved'] = True
                        active_trade['max_R_achieved_for_analysis'] = max(active_trade.get('max_R_achieved_for_analysis', 0.0), min(strategy_instance.tp_rr_ratio, 5.0))
        
        if active_trade['status'] == 'open': 
            active_trade['status'] = 'closed_eod'; active_trade['exit_time'] = ltf_data_original_ohlc.index[-1]; active_trade['exit_price'] = ltf_data_original_ohlc.iloc[-1]['close']
            _calculate_and_set_trade_pnl(active_trade, pip_size_local) 
            print(f"    Trade EOD Close: ID {active_trade['id']} at {active_trade['exit_time']} Price: {active_trade['exit_price']:.5f}")

    print(f"--- Backtest for {symbol} ({strategy_name}) Finished. Total trades: {len(trades_log)} ---")
    return trades_log, current_overall_trade_id
