### File: X:\AmalTrading\trading_backtesting\live_engine.py

import time
from datetime import datetime
import pandas as pd
import MetaTrader5 as mt5 

import config # General configurations
from strategies import get_strategy_class # To load the active strategy
from live_data_handler import LiveDataHandler # For fetching live market data
from broker_interface import BrokerInterface # For interacting with MT5 trading functions
from live_portfolio_manager import LivePortfolioManager # For managing live trades and lot sizing
from backtester import get_pip_size # Utility for pip size

# --- Live Engine Configuration ---
LIVE_SYMBOLS = ["GBPJPY", "EURUSD", "USDJPY", "GBPUSD", "AUDUSD", "EURUSD", "CADJPY"] 
MAGIC_NUMBER_LIVE = 10121617
POLL_INTERVAL_SECONDS = 10

# Lookback bars for fetching rolling data needed by indicators/strategies
ROLLING_LTF_BARS = 300
ROLLING_HTF_BARS = 200 

# --- Full Strategy Engine ---
def run_live_engine():
    active_strategy_name = config.ACTIVE_STRATEGY_NAME
    print(f"--- Starting Live Trading Engine ({active_strategy_name}) @ {datetime.now()} ---")
    print(f"--- Trading Symbols: {', '.join(LIVE_SYMBOLS)} ---")
    print(f"--- Magic Number for Trades: {MAGIC_NUMBER_LIVE} ---")
    
    live_data = LiveDataHandler()
    if not live_data.mt5_initialized:
        print("CRITICAL: Failed to initialize LiveDataHandler. Exiting.")
        return

    broker = BrokerInterface(live_data_handler_instance=live_data)
    if not broker.mt5_initialized:
        print("CRITICAL: Failed to initialize BrokerInterface. Exiting.")
        live_data.shutdown()
        return
        
    account_info_val = mt5.account_info()
    if not account_info_val:
        print("CRITICAL: Could not get account info. Exiting.")
        live_data.shutdown()
        return
    portfolio = LivePortfolioManager(broker, account_currency=account_info_val.currency)
    portfolio.load_existing_positions(magic_number_filter=MAGIC_NUMBER_LIVE) 

    strategy_instances = {}
    last_ltf_candle_times = {symbol: None for symbol in LIVE_SYMBOLS}
    
    # Initialize strategy instances for each symbol
    for symbol in LIVE_SYMBOLS:
        strategy_custom_params = config.STRATEGY_SPECIFIC_PARAMS.get(active_strategy_name, {})
        pip_size = get_pip_size(symbol)
        common_params = {
            "symbol": symbol, "pip_size": pip_size, 
            "sl_buffer_price": config.SL_BUFFER_PIPS * pip_size, 
            "htf_timeframe_str": config.HTF_TIMEFRAME_STR,
            "ltf_timeframe_str": config.LTF_TIMEFRAME_STR,
        }
        try:
            StrategyClass = get_strategy_class(active_strategy_name)
            strategy_instances[symbol] = StrategyClass(strategy_custom_params, common_params)
            print(f"Initialized strategy {active_strategy_name} for {symbol}")
        except ValueError as e:
            print(f"CRITICAL: Could not initialize strategy for {symbol}: {e}. Exiting.")
            live_data.shutdown()
            return


    # --- Main Trading Loop ---
    try:
        while True:
            current_loop_time = datetime.now()
            
            for symbol in LIVE_SYMBOLS:
                strategy = strategy_instances[symbol]

                # 1. Get Rolling Historical Data for HTF and LTF
                htf_df_live_rolling = live_data.get_rolling_ohlc_data(symbol, config.HTF_MT5, ROLLING_HTF_BARS)
                ltf_df_live_rolling = live_data.get_rolling_ohlc_data(symbol, config.LTF_MT5, ROLLING_LTF_BARS)

                if ltf_df_live_rolling is None or ltf_df_live_rolling.empty:
                    continue

                if active_strategy_name not in ["HAAlligatorMACD"] and \
                   (htf_df_live_rolling is None or htf_df_live_rolling.empty):
                    pass # Allow strategy to decide if it can proceed

                # 2. Prepare Data: Apply indicators, HA, etc. using the strategy's logic
                # Pass copies to ensure the original rolling data isn't modified by strategy.
                _prepared_htf_df, prepared_ltf_df_strat = strategy.prepare_data(
                    htf_df_live_rolling.copy() if htf_df_live_rolling is not None else pd.DataFrame(), 
                    ltf_df_live_rolling.copy()
                )

                if prepared_ltf_df_strat.empty:
                    continue
                
                decision_candle_idx = len(prepared_ltf_df_strat) - 1
                if decision_candle_idx < 0 : continue
                decision_candle_series = prepared_ltf_df_strat.iloc[decision_candle_idx]
                current_ltf_latest_candle_time = decision_candle_series.name

                # 3. Manage Open Trades (SL, TP, Breakeven) for this symbol FIRST
                # This uses the latest decision_candle_series for R-calculations and ltf_df_live_rolling for BE H/L.
                portfolio.manage_symbol_trades(symbol, decision_candle_series, ltf_df_live_rolling, strategy, MAGIC_NUMBER_LIVE)

                # 4. Check if this is a new candle since last processing for *entry signals*
                if last_ltf_candle_times[symbol] == current_ltf_latest_candle_time:
                    continue 
                
                print(f"  New LTF Candle Detected for {symbol}: {current_ltf_latest_candle_time.strftime('%Y-%m-%d %H:%M:%S')}")
                last_ltf_candle_times[symbol] = current_ltf_latest_candle_time
                
                # 5. Check for New Entry Signals (only if no open trade by this bot for this symbol)
                if not portfolio.has_open_trade(symbol, magic_number=MAGIC_NUMBER_LIVE):
                    htf_signal_live = None
                    if _prepared_htf_df is not None and not _prepared_htf_df.empty:
                        htf_decision_candle_idx = len(_prepared_htf_df) - 1
                        if htf_decision_candle_idx >=0:
                            htf_signal_live = strategy.check_htf_condition(_prepared_htf_df, htf_decision_candle_idx)
                    elif active_strategy_name == "HAAlligatorMACD": 
                         htf_signal_live = { "type": "generic_single_tf_go", 
                                             "time": prepared_ltf_df_strat.index[decision_candle_idx], 
                                             "required_ltf_direction": "any" }
                    # Add other strategy-specific fallbacks if needed

                    if htf_signal_live:
                        # LTF signal on the latest closed prepared LTF candle (decision_candle_idx)
                        ltf_signal_live = strategy.check_ltf_entry_signal(prepared_ltf_df_strat, decision_candle_idx, htf_signal_live)

                        if ltf_signal_live:
                            print(f"  >>> LIVE ENTRY SIGNAL: {symbol} - {ltf_signal_live['type']} at {decision_candle_series.name.strftime('%Y-%m-%d %H:%M:%S')}")
                            
                            entry_ref_price = decision_candle_series.get('close', 0.0) 
                            # For HA strategies, might prefer ha_close if available and appropriate
                            if 'ha_close' in decision_candle_series and active_strategy_name == "HAAlligatorMACD":
                                entry_ref_price = decision_candle_series['ha_close']
                            
                            if entry_ref_price == 0.0:
                                print(f"    Warning: Entry reference price is 0 for {symbol}. Skipping trade.")
                                continue

                            entry_ref_time = decision_candle_series.name

                            sl_price, tp_price = strategy.calculate_sl_tp(
                                entry_ref_price, entry_ref_time, prepared_ltf_df_strat, ltf_signal_live, htf_signal_live
                            )

                            if sl_price and tp_price:
                                # For live lot calculation, use current market price for more accuracy if possible
                                current_tick_for_lot_calc = mt5.symbol_info_tick(symbol)
                                actual_entry_ref_for_lot_calc = entry_ref_price # Default
                                if current_tick_for_lot_calc:
                                    price_for_calc = current_tick_for_lot_calc.ask if ltf_signal_live['direction'] == 'bullish' else current_tick_for_lot_calc.bid
                                    if price_for_calc != 0.0: # Ensure valid tick price
                                        actual_entry_ref_for_lot_calc = price_for_calc
                                
                                volume = portfolio.calculate_lot_size(symbol, sl_price, actual_entry_ref_for_lot_calc)
                                if volume > 0:
                                    print(f"    Attempting to open {ltf_signal_live['direction']} for {symbol} vol:{volume:.2f} SL:{sl_price:.5f} TP:{tp_price:.5f}")
                                    order_mt5_type = mt5.ORDER_TYPE_BUY if ltf_signal_live['direction'] == 'bullish' else mt5.ORDER_TYPE_SELL
                                    
                                    # --- ACTUAL ORDER PLACEMENT ---
                                    deal_info = broker.place_market_order(
                                        symbol=symbol, order_type=order_mt5_type, volume=volume,
                                        sl_price=sl_price, tp_price=tp_price,
                                        magic_number=MAGIC_NUMBER_LIVE, comment=f"{active_strategy_name}"
                                    )
                                    # Check if deal_info is valid and represents a successful trade entry
                                    if deal_info and hasattr(deal_info, 'position_id') and deal_info.position_id > 0 and deal_info.entry == mt5.DEAL_ENTRY_IN:
                                        portfolio.add_trade_from_deal(deal_info, active_strategy_name, sl_price, tp_price, f"{active_strategy_name}")
                                        print(f"    SUCCESS: Order placed for {symbol}. Pos.ID: {deal_info.position_id}")
                                    else:
                                        print(f"    FAILURE: Could not place order for {symbol} or invalid deal_info received.")
                                        if deal_info: print(f"      Deal Info Details: {deal_info}")
                                else:
                                    print(f"    Volume calculation resulted in 0 for {symbol}. No order placed.")
                            else:
                                print(f"    Invalid SL/TP calculated for {symbol} ({sl_price}, {tp_price}). No order placed.")
                # End of new entry check
            # End of symbol processing in loop
            time.sleep(0.05)

            for ticket_id_closed in list(portfolio.open_trades.keys()): # Iterate on copy
                if portfolio.open_trades[ticket_id_closed].symbol == symbol and \
                   portfolio.open_trades[ticket_id_closed].status != "open":
                    portfolio.remove_closed_trade(ticket_id_closed)

        time.sleep(POLL_INTERVAL_SECONDS)

    except KeyboardInterrupt:
        print("Live engine stopping due to user request (KeyboardInterrupt)...")
    except Exception as e:
        print(f"CRITICAL ERROR in live engine: {e}")
        import traceback
        traceback.print_exc()
    finally:
        print("Shutting down live engine components...")
        if 'live_data' in locals() and live_data.mt5_initialized: # Check if live_data was initialized
            live_data.shutdown()
        print("Live engine shut down complete.")

if __name__ == '__main__':    
    # --- Run Full Live Engine ---
    print("\n--- LAUNCHING FULL LIVE TRADING ENGINE ---")
    print("--- Ensure MT5 is running, logged into DEMO, and config is set for live testing. ---")
    print("--- Press CTRL+C in the console to stop the engine. ---")
    time.sleep(3)
    
    run_live_engine()