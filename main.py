# forex_backtester_cli/main.py
import pandas as pd
import argparse
import os 

import config
from data_handler import fetch_historical_data, shutdown_mt5_connection, initialize_mt5_connection
from heikin_ashi import calculate_heikin_ashi
from utils import identify_swing_points_simple, identify_swing_points_zigzag
from plotting_utils import plot_ohlc_with_swings 
from backtester import run_backtest, get_pip_size 
from reporting import calculate_performance_metrics, calculate_portfolio_performance_metrics
from strategies import get_strategy_class 
from plotly_plotting import plot_trade_chart_plotly 
from datetime import datetime as dt

def debug_strategy_on_segment(symbol: str, start_date: str, end_date: str, 
                              strategy_name_to_debug: str, strategy_params_to_debug: dict,
                              plot_output_dir: str = "plots"):
    print(f"--- Debugging Strategy {strategy_name_to_debug} for {symbol} from {start_date} to {end_date} ---")
    print("NOTE: debug_strategy_on_segment needs refactoring to use the new strategy object model for accurate signal plotting.")
    
    from strategy_logic import detect_choch, detect_ltf_structure_change 
    os.makedirs(plot_output_dir, exist_ok=True) 
    print(f"\nFetching HTF ({config.HTF_TIMEFRAME_STR}) data...")
    htf_data = fetch_historical_data(symbol, config.HTF_MT5, start_date, end_date)
    if htf_data is None or htf_data.empty: return
    
    if config.SWING_IDENTIFICATION_METHOD == "simple": htf_data_with_swings = identify_swing_points_simple(htf_data, config.N_BARS_LEFT_RIGHT_FOR_SWING_HTF, config.N_BARS_LEFT_RIGHT_FOR_SWING_HTF)
    elif config.SWING_IDENTIFICATION_METHOD == "zigzag": htf_data_with_swings = identify_swing_points_zigzag(htf_data, config.ZIGZAG_LEN_HTF)
    else: raise ValueError(f"Unknown method: {config.SWING_IDENTIFICATION_METHOD}")
    
    plot_ohlc_with_swings(htf_data, htf_data_with_swings, symbol, config.HTF_TIMEFRAME_STR, f"HTF Swings - {symbol}", save_path=os.path.join(plot_output_dir, f"{symbol}_HTF_swings.png"))
    
    htf_choch_points_for_plot = []
    start_idx_choch = config.ZIGZAG_LEN_HTF if config.SWING_IDENTIFICATION_METHOD == "zigzag" else config.N_BARS_LEFT_RIGHT_FOR_SWING_HTF
    for i in range(start_idx_choch, len(htf_data_with_swings)):
        choch_type, choch_price_broken, choch_confirmed_time = detect_choch(htf_data_with_swings, i, strategy_params_to_debug.get("BREAK_TYPE", "close"))
        if choch_type: htf_choch_points_for_plot.append((choch_confirmed_time, choch_price_broken, choch_type))
    plot_ohlc_with_swings(htf_data, htf_data_with_swings, symbol, config.HTF_TIMEFRAME_STR, f"HTF CHoCHs - {symbol}", choch_points=htf_choch_points_for_plot, save_path=os.path.join(plot_output_dir, f"{symbol}_HTF_chochs.png"))
    print("\n--- Strategy Debugging with Plotting Finished (using potentially outdated direct logic) ---")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Forex Backtester CLI")
    parser.add_argument("--symbols", nargs='+', default=config.SYMBOLS, help="List of symbols")
    parser.add_argument("--start", type=str, default=config.START_DATE_STR, help="Start date (YYYY-MM-DD)")
    parser.add_argument("--end", type=str, default=config.END_DATE_STR, help="End date (YYYY-MM-DD)")
    parser.add_argument("--mode", type=str, default="backtest", choices=["debug_plot", "backtest"])
    parser.add_argument("--strategy", type=str, default=config.ACTIVE_STRATEGY_NAME, help="Name of the strategy to run")
    
    args = parser.parse_args()

    active_strategy_name = args.strategy
    strategy_custom_params = config.STRATEGY_SPECIFIC_PARAMS.get(active_strategy_name)
    if strategy_custom_params is None:
        print(f"ERROR: Parameters for strategy '{active_strategy_name}' not found in config.py. Exiting.")
        exit()

    timestamp_str = dt.now().strftime("%Y%m%d_%H%M%S")
    symbols_str_for_folder = "_".join(args.symbols) if args.symbols else "_".join(config.SYMBOLS)
    session_folder_name = f"{active_strategy_name}_{symbols_str_for_folder}_{timestamp_str}"
    base_results_path = "Backtesting_Results"
    session_results_path = os.path.join(base_results_path, session_folder_name)
    os.makedirs(session_results_path, exist_ok=True)
    print(f"Results will be saved in: {session_results_path}")

    report_file_path = os.path.join(session_results_path, "ConsolidatedReport.txt")
    all_reports_text = [] 

    if not initialize_mt5_connection(): exit()
    
    all_symbols_trades_dict = {} 
    overall_trade_counter = 0 

    try:
        if args.mode == "debug_plot":
            # This debug_plot mode needs to be updated to use the strategy object model
            # for accurate signal plotting if you rely on it heavily.
            debug_symbol = args.symbols[0] if args.symbols else config.SYMBOLS[0]
            debug_start_date = "2025-02-03" # Example fixed date for focused debug
            debug_end_date = "2025-02-07"   # Example fixed date
            print(f"Running in debug_plot mode for {debug_symbol} from {debug_start_date} to {debug_end_date}")
            debug_strategy_on_segment(debug_symbol, debug_start_date, debug_end_date, 
                                      active_strategy_name, strategy_custom_params, 
                                      session_results_path) # Pass session_results_path

        elif args.mode == "backtest":
            for symbol_to_run in args.symbols:
                print(f"\n===== Running Backtest for {symbol_to_run} with Strategy: {active_strategy_name} =====")
                htf_data = fetch_historical_data(symbol_to_run, config.HTF_MT5, args.start, args.end)
                if htf_data is None or htf_data.empty: all_symbols_trades_dict[symbol_to_run] = []; continue
                if config.SWING_IDENTIFICATION_METHOD == "zigzag": htf_data_swings = identify_swing_points_zigzag(htf_data, config.ZIGZAG_LEN_HTF)
                else: htf_data_swings = identify_swing_points_simple(htf_data, config.N_BARS_LEFT_RIGHT_FOR_SWING_HTF, config.N_BARS_LEFT_RIGHT_FOR_SWING_HTF)
                
                ltf_fetch_start = (pd.to_datetime(args.start) - config.HTF_TIMEDELTA * 10).strftime("%Y-%m-%d")
                ltf_fetch_end = (pd.to_datetime(args.end) + config.HTF_TIMEDELTA * 10).strftime("%Y-%m-%d")
                ltf_ohlc_data = fetch_historical_data(symbol_to_run, config.LTF_MT5, ltf_fetch_start, ltf_fetch_end)
                if ltf_ohlc_data is None or ltf_ohlc_data.empty: all_symbols_trades_dict[symbol_to_run] = []; continue
                ltf_ha_data = calculate_heikin_ashi(ltf_ohlc_data)
                if config.SWING_IDENTIFICATION_METHOD == "zigzag": ltf_ha_data_swings = identify_swing_points_zigzag(ltf_ha_data, config.ZIGZAG_LEN_LTF, col_high='ha_high', col_low='ha_low')
                else: ltf_ha_data_swings = identify_swing_points_simple(ltf_ha_data, config.N_BARS_LEFT_RIGHT_FOR_SWING_LTF, config.N_BARS_LEFT_RIGHT_FOR_SWING_LTF, col_high='ha_high', col_low='ha_low')

                logged_trades_for_symbol, updated_overall_trade_counter = run_backtest(
                    symbol_to_run, htf_data_swings, ltf_ohlc_data, ltf_ha_data_swings,
                    active_strategy_name, strategy_custom_params,
                    session_results_path, 
                    starting_trade_id=overall_trade_counter + 1 
                )
                overall_trade_counter = updated_overall_trade_counter 
                
                all_symbols_trades_dict[symbol_to_run] = logged_trades_for_symbol

                if logged_trades_for_symbol:
                    pip_size_val = get_pip_size(symbol_to_run)
                    print(f"  DEBUG: Calculating PnL R for {len(logged_trades_for_symbol)} trades for {symbol_to_run}") # Moved print
                    for trade_idx, trade in enumerate(logged_trades_for_symbol): 
                        if trade.get('exit_price') is not None and \
                           trade.get('entry_price') is not None and \
                           trade.get('initial_sl_price') is not None: # Check for initial_sl_price
                            
                            initial_sl = trade['initial_sl_price'] # Use the stored initial SL
                            risk_pips = abs(trade['entry_price'] - initial_sl) / pip_size_val
                            
                            pnl_pips_val = 0
                            if trade['direction'] == 'bullish': 
                                pnl_pips_val = (trade['exit_price'] - trade['entry_price']) / pip_size_val
                            elif trade['direction'] == 'bearish': 
                                pnl_pips_val = (trade['entry_price'] - trade['exit_price']) / pip_size_val
                            
                            if risk_pips > 1e-9: 
                                trade['pnl_R'] = round(pnl_pips_val / risk_pips, 2)
                            else: 
                                trade['pnl_R'] = 0 
                            
                            # <<< DEBUG PRINT FOR TP TRADES >>>
                            if trade['status'] == 'closed_tp':
                                print(f"    DEBUG_TRADE_PNL_R (TP): ID {trade['id']}, Entry {trade['entry_price']:.5f}, Exit {trade['exit_price']:.5f}, Initial_SL {initial_sl:.5f}, RiskPips {risk_pips:.2f}, PnLPips {pnl_pips_val:.2f}, PnL_R {trade['pnl_R']:.2f}, Target_RR {strategy_custom_params.get('TP_RR_RATIO', 'N/A')}")
                            elif trade['status'] == 'closed_sl_be':
                                print(f"    DEBUG_TRADE_PNL_R (SL@BE): ID {trade['id']}, Entry {trade['entry_price']:.5f}, Exit {trade['exit_price']:.5f}, Initial_SL {initial_sl:.5f}, RiskPips {risk_pips:.2f}, PnLPips {pnl_pips_val:.2f}, PnL_R {trade['pnl_R']:.2f}")
                            elif trade['status'] == 'closed_sl':
                                print(f"    DEBUG_TRADE_PNL_R (SL): ID {trade['id']}, Entry {trade['entry_price']:.5f}, Exit {trade['exit_price']:.5f}, Initial_SL {initial_sl:.5f}, RiskPips {risk_pips:.2f}, PnLPips {pnl_pips_val:.2f}, PnL_R {trade['pnl_R']:.2f}")


                        else: 
                             trade['pnl_R'] = 0 
                             print(f"    DEBUG_TRADE_PNL_R: ID {trade.get('id','N/A')} missing price data for PnL R calc.")
                    
                    report_text_single = calculate_performance_metrics(
                        logged_trades_for_symbol, config.INITIAL_CAPITAL, symbol_to_run, 
                        pip_size_val, strategy_custom_params, session_results_path
                    ) 
                    if report_text_single: all_reports_text.append(report_text_single)
                else:
                    all_reports_text.append(f"\nNo trades for {symbol_to_run} with {active_strategy_name}.\n")
            
            if any(trade_list for trade_list in all_symbols_trades_dict.values()):
                print(f"\n\n===== Generating Portfolio Performance Report ({active_strategy_name}) =====")
                portfolio_report_text = calculate_portfolio_performance_metrics(
                    all_symbols_trades_dict, config.INITIAL_CAPITAL, 
                    strategy_custom_params, session_results_path
                )
                if portfolio_report_text: all_reports_text.append(portfolio_report_text)
            else:
                all_reports_text.append(f"\nNo trades generated across any symbols for portfolio report ({active_strategy_name}).\n")
            
            with open(report_file_path, "w") as f_report:
                for report_section in all_reports_text:
                    f_report.write(report_section + "\n\n")
            print(f"Consolidated report saved to: {report_file_path}")
            
    finally:
        shutdown_mt5_connection()
        print("Application finished.")