# forex_backtester_cli/backtester.py
import pandas as pd
from datetime import timedelta 

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
    pip_size = get_pip_size(symbol)
    sl_buffer_price = config.SL_BUFFER_PIPS * pip_size
    current_overall_trade_id = starting_trade_id -1 

    StrategyClass = get_strategy_class(strategy_name)
    if not StrategyClass:
        print(f"ERROR: Strategy '{strategy_name}' not found.")
        return [], starting_trade_id -1 
    
    common_strategy_params = {
        "symbol": symbol, "pip_size": pip_size, "sl_buffer_price": sl_buffer_price,
        "htf_timeframe_str": config.HTF_TIMEFRAME_STR, "ltf_timeframe_str": config.LTF_TIMEFRAME_STR,
    }
    strategy_instance = StrategyClass(strategy_custom_params, common_strategy_params)
    prepared_htf_data, prepared_ltf_data = strategy_instance.prepare_data(
        htf_data_with_swings.copy(), ltf_data_ha_with_swings.copy()
    )
    
    start_offset_htf = (config.ZIGZAG_LEN_HTF if config.SWING_IDENTIFICATION_METHOD == "zigzag" 
                        else config.N_BARS_LEFT_RIGHT_FOR_SWING_HTF) + 10

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
                
                if active_trade.get('max_R_achieved_for_analysis', 0.0) < 5.0 or active_trade['status'] == 'open': # Continue R analysis if not capped or trade still open
                    risk_in_price = abs(active_trade['entry_price'] - active_trade['sl_price'])
                    if risk_in_price > 1e-9:
                        current_potential_R = 0.0
                        if active_trade['direction'] == 'bullish': 
                            current_potential_R = (ltf_candle['high'] - active_trade['entry_price']) / risk_in_price
                        elif active_trade['direction'] == 'bearish': 
                            current_potential_R = (active_trade['entry_price'] - ltf_candle['low']) / risk_in_price
                        
                        active_trade['max_R_achieved_for_analysis'] = max(
                            active_trade.get('max_R_achieved_for_analysis', 0.0), 
                            min(current_potential_R, 5.0) 
                        )
                        
                        r_levels_to_check_for_analysis = strategy_instance.get_r_levels_to_track() + [3.5, 4.0, 4.5, 5.0]
                        r_levels_to_check_for_analysis = sorted(list(set(r_levels_to_check_for_analysis)))

                        for r_target in r_levels_to_check_for_analysis:
                            if r_target > 5.0: continue 
                            if not active_trade.get(f'{r_target}R_achieved', False) and current_potential_R >= r_target:
                                active_trade[f'{r_target}R_achieved'] = True
                
                if active_trade['status'] == 'open': # Only check SL/TP if trade is actually open
                    if active_trade['direction'] == 'bullish':
                        if ltf_candle['low'] <= active_trade['sl_price']: 
                            active_trade['status'] = 'closed_sl'; active_trade['exit_time'] = ltf_idx; active_trade['exit_price'] = active_trade['sl_price']
                            print(f"    Trade SL: ID {active_trade['id']} at {ltf_idx} Price: {active_trade['sl_price']:.5f}")
                            break 
                        elif ltf_candle['high'] >= active_trade['tp_price']: 
                            active_trade['status'] = 'closed_tp'; active_trade['exit_time'] = ltf_idx; active_trade['exit_price'] = active_trade['tp_price']
                            for r_target in strategy_instance.get_r_levels_to_track():
                                if r_target <= strategy_instance.tp_rr_ratio: active_trade[f'{r_target}R_achieved'] = True
                            # Ensure max_R_achieved_for_analysis reflects at least TP if TP is hit
                            active_trade['max_R_achieved_for_analysis'] = max(active_trade.get('max_R_achieved_for_analysis', 0.0), min(strategy_instance.tp_rr_ratio, 5.0))
                            print(f"    Trade TP: ID {active_trade['id']} at {ltf_idx} Price: {active_trade['tp_price']:.5f}")
                            # No break here for TP, R-analysis continues on this candle, but status is now closed_tp
                    elif active_trade['direction'] == 'bearish':
                        if ltf_candle['high'] >= active_trade['sl_price']: 
                            active_trade['status'] = 'closed_sl'; active_trade['exit_time'] = ltf_idx; active_trade['exit_price'] = active_trade['sl_price']
                            print(f"    Trade SL: ID {active_trade['id']} at {ltf_idx} Price: {active_trade['sl_price']:.5f}")
                            break
                        elif ltf_candle['low'] <= active_trade['tp_price']: 
                            active_trade['status'] = 'closed_tp'; active_trade['exit_time'] = ltf_idx; active_trade['exit_price'] = active_trade['tp_price']
                            for r_target in strategy_instance.get_r_levels_to_track():
                                 if r_target <= strategy_instance.tp_rr_ratio: active_trade[f'{r_target}R_achieved'] = True
                            active_trade['max_R_achieved_for_analysis'] = max(active_trade.get('max_R_achieved_for_analysis', 0.0), min(strategy_instance.tp_rr_ratio, 5.0))
                            print(f"    Trade TP: ID {active_trade['id']} at {ltf_idx} Price: {active_trade['tp_price']:.5f}")
            
            if active_trade['status'] != 'open': # If SL was hit (TP status allows R-analysis to continue for current candle)
                active_trade = None 
        
        if not active_trade:
            htf_signal = strategy_instance.check_htf_condition(prepared_htf_data, i)
            if htf_signal:
                print(f"\n{current_htf_candle_time}: HTF Signal ({htf_signal['type']}) detected for {strategy_name}. Level: {htf_signal.get('level_broken', 'N/A'):.5f}")
                ltf_search_start_time = current_htf_candle_time 
                ltf_search_window_end_time = current_htf_candle_time + (config.HTF_TIMEDELTA * 3) 
                relevant_ltf_data_ha_swings = prepared_ltf_data[
                    (prepared_ltf_data.index > ltf_search_start_time) & 
                    (prepared_ltf_data.index <= ltf_search_window_end_time)
                ]
                if relevant_ltf_data_ha_swings.empty: continue

                for j_ltf_search in range(len(relevant_ltf_data_ha_swings)):
                    current_ltf_ha_candle_time = relevant_ltf_data_ha_swings.index[j_ltf_search]
                    if not is_time_allowed(current_ltf_ha_candle_time): continue

                    original_ltf_iloc = prepared_ltf_data.index.get_loc(current_ltf_ha_candle_time)
                    ltf_entry_signal = strategy_instance.check_ltf_entry_signal(prepared_ltf_data, original_ltf_iloc, htf_signal)

                    if ltf_entry_signal:
                        entry_candle_iloc_in_subset = j_ltf_search + 1 
                        if entry_candle_iloc_in_subset < len(relevant_ltf_data_ha_swings):
                            entry_time = relevant_ltf_data_ha_swings.index[entry_candle_iloc_in_subset]
                            if entry_time not in ltf_data_original_ohlc.index: continue
                            entry_price = ltf_data_original_ohlc.loc[entry_time]['open']
                            
                            sl_price, tp_price = strategy_instance.calculate_sl_tp(
                                entry_price, entry_time, prepared_ltf_data, ltf_entry_signal, htf_signal
                            )
                            if sl_price is None or tp_price is None: break 

                            current_overall_trade_id += 1 
                            print(f"    {entry_time}: LTF ENTRY SIGNAL ({strategy_name})! Type: {ltf_entry_signal['type']}, Price: {entry_price:.5f}")
                            active_trade = {
                                "id": current_overall_trade_id, 
                                "symbol_specific_id": len(trades_log) + 1, 
                                "symbol": symbol, "strategy": strategy_name,
                                "entry_time": entry_time, "entry_price": entry_price,
                                "direction": htf_signal["required_ltf_direction"],
                                "sl_price": sl_price, "tp_price": tp_price,
                                "htf_signal_details": htf_signal, "ltf_signal_details": ltf_entry_signal,
                                "status": "open", "exit_time": None, "exit_price": None,
                                "pnl_pips": None, "pnl_R": None,
                                "last_checked_ltf_time": entry_time, 
                                'max_R_achieved_for_analysis': 0.0 # Use this name
                            }
                            r_levels_to_init = strategy_instance.get_r_levels_to_track() + [3.5, 4.0, 4.5, 5.0]
                            for r_val in sorted(list(set(r_levels_to_init))):
                                if r_val <= 5.0: active_trade[f'{r_val}R_achieved'] = False
                            
                            trades_log.append(active_trade)
                            print(f"    Trade Opened: ID {active_trade['id']} ({active_trade['symbol_specific_id']}-{symbol}) {active_trade['direction']} at {active_trade['entry_price']:.5f}, SL: {active_trade['sl_price']:.5f}, TP: {active_trade['tp_price']:.5f}")
                            
                            active_trade['overall_trade_id'] = active_trade['id'] 
                            plot_trade_chart_plotly(active_trade, session_results_path) 
                            break 
    
    if active_trade and active_trade['status'] == 'open':
        print(f"    Managing EOD for still open trade ID {active_trade['id']} from {active_trade['last_checked_ltf_time']}")
        ltf_final_slice = ltf_data_original_ohlc[ltf_data_original_ohlc.index > active_trade['last_checked_ltf_time']]
        for ltf_idx, ltf_candle in ltf_final_slice.iterrows(): 
            active_trade['last_checked_ltf_time'] = ltf_idx
            if active_trade.get('max_R_achieved_for_analysis', 0.0) < 5.0 or active_trade['status'] == 'open':
                risk_in_price = abs(active_trade['entry_price'] - active_trade['sl_price'])
                if risk_in_price > 1e-9:
                    current_potential_R = 0.0
                    if active_trade['direction'] == 'bullish': current_potential_R = (ltf_candle['high'] - active_trade['entry_price']) / risk_in_price
                    elif active_trade['direction'] == 'bearish': current_potential_R = (active_trade['entry_price'] - ltf_candle['low']) / risk_in_price
                    active_trade['max_R_achieved_for_analysis'] = max(active_trade.get('max_R_achieved_for_analysis', 0.0), min(current_potential_R, 5.0))
                    r_levels_to_check_for_analysis = strategy_instance.get_r_levels_to_track() + [3.5, 4.0, 4.5, 5.0]
                    for r_target in sorted(list(set(r_levels_to_check_for_analysis))):
                        if r_target <= 5.0 and not active_trade.get(f'{r_target}R_achieved', False) and current_potential_R >= r_target:
                            active_trade[f'{r_target}R_achieved'] = True
            
            if active_trade['status'] == 'open': 
                if active_trade['direction'] == 'bullish': 
                    if ltf_candle['low'] <= active_trade['sl_price']: active_trade['status'] = 'closed_sl'; active_trade['exit_time'] = ltf_idx; active_trade['exit_price'] = active_trade['sl_price']; break 
                    elif ltf_candle['high'] >= active_trade['tp_price']: active_trade['status'] = 'closed_tp'; active_trade['exit_time'] = ltf_idx; active_trade['exit_price'] = active_trade['tp_price']
                elif active_trade['direction'] == 'bearish': 
                    if ltf_candle['high'] >= active_trade['sl_price']: active_trade['status'] = 'closed_sl'; active_trade['exit_time'] = ltf_idx; active_trade['exit_price'] = active_trade['sl_price']; break
                    elif ltf_candle['low'] <= active_trade['tp_price']: active_trade['status'] = 'closed_tp'; active_trade['exit_time'] = ltf_idx; active_trade['exit_price'] = active_trade['tp_price']
        
        if active_trade['status'] == 'open': 
            active_trade['status'] = 'closed_eod'; active_trade['exit_time'] = ltf_data_original_ohlc.index[-1]; active_trade['exit_price'] = ltf_data_original_ohlc.iloc[-1]['close']
            print(f"    Trade EOD Close: ID {active_trade['id']} at {active_trade['exit_time']} Price: {active_trade['exit_price']:.5f}")

    print(f"--- Backtest for {symbol} ({strategy_name}) Finished. Total trades: {len(trades_log)} ---")
    return trades_log, current_overall_trade_id