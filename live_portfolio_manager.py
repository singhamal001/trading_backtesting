### File: X:\AmalTrading\trading_backtesting\live_portfolio_manager.py

from typing import List, Dict, Optional, Any
from dataclasses import dataclass, field
import MetaTrader5 as mt5 
import pandas as pd 
from broker_interface import BrokerInterface 
from backtester import get_pip_size 
import config 
import time 

@dataclass
class LiveTrade:
    symbol: str
    ticket_id: int 
    order_id: int  
    entry_price: float
    initial_sl_price: float
    current_sl_price: float
    tp_price: float
    direction: str 
    mt5_direction: int 
    volume: float
    entry_time: Any 
    strategy_name: str
    magic_number: int
    comment: Optional[str] = ""
    sl_moved_to_be: bool = False
    status: str = "open" 
    exit_price: Optional[float] = None
    exit_time: Optional[Any] = None
    pnl_currency: Optional[float] = None 
    max_R_achieved_for_analysis: float = 0.0 
    r_achievements: Dict[str, bool] = field(default_factory=dict)


class LivePortfolioManager:
    def __init__(self, broker: BrokerInterface, account_currency: str = "USD"):
        self.broker = broker
        self.open_trades: Dict[int, LiveTrade] = {} 
        self.account_currency = account_currency 
        self.risk_per_trade_percent = config.RISK_PER_TRADE_PERCENT 

    def load_existing_positions(self, magic_number_filter: Optional[int] = None):
        print("LivePortfolioManager: Attempting to load existing positions...")
        broker_positions: List[Any] = self.broker.get_open_positions(magic_number=magic_number_filter)
        if not broker_positions:
            print("LivePortfolioManager: No existing positions found to load matching filter.")
            return

        for pos_info in broker_positions:
            if pos_info.ticket not in self.open_trades: 
                direction_str = "bullish" if pos_info.type == mt5.ORDER_TYPE_BUY else "bearish"
                # Check if SL/TP are valid (not 0.0) before assigning
                initial_sl = pos_info.sl if pos_info.sl != 0.0 else (pos_info.price_open - 100 * get_pip_size(pos_info.symbol) * (1 if pos_info.type == mt5.ORDER_TYPE_BUY else -1)) # Fallback SL
                initial_tp = pos_info.tp if pos_info.tp != 0.0 else (pos_info.price_open + 200 * get_pip_size(pos_info.symbol) * (1 if pos_info.type == mt5.ORDER_TYPE_BUY else -1)) # Fallback TP
                
                trade = LiveTrade(
                    symbol=pos_info.symbol,
                    ticket_id=pos_info.ticket,
                    order_id=pos_info.order, 
                    entry_price=pos_info.price_open,
                    initial_sl_price=initial_sl, 
                    current_sl_price=initial_sl,
                    tp_price=initial_tp,
                    direction=direction_str,
                    mt5_direction=pos_info.type,
                    volume=pos_info.volume,
                    entry_time=pd.to_datetime(pos_info.time, unit='s', utc=True), 
                    strategy_name="loaded_manual", 
                    magic_number=pos_info.magic,
                    comment=pos_info.comment,
                    sl_moved_to_be=False # Cannot reliably infer if SL was already moved to BE when loading
                )
                self.open_trades[pos_info.ticket] = trade
                print(f"  Loaded existing position: Ticket {pos_info.ticket} for {pos_info.symbol} SL:{initial_sl} TP:{initial_tp}")
        print(f"LivePortfolioManager: Finished loading. Total managed positions: {len(self.open_trades)}")


    def calculate_lot_size(self, symbol: str, sl_price_calc: float, entry_price_calc: float) -> float:
        account_info = mt5.account_info()
        if not account_info:
            print("LivePortfolioManager: Could not get account info for lot size calculation.")
            return 0.0
        
        account_equity = account_info.equity
        risk_amount_currency = (self.risk_per_trade_percent / 100) * account_equity
        
        pip_size_val = get_pip_size(symbol) 
        sl_distance_pips = abs(entry_price_calc - sl_price_calc) / pip_size_val
        if sl_distance_pips < 1: 
            print(f"LivePortfolioManager: SL distance ({sl_distance_pips:.2f} pips) is too small for {symbol}. Cannot calculate lot size.")
            return 0.0

        symbol_info = self.broker.get_symbol_info(symbol)
        if not symbol_info:
            return 0.0
        
        value_per_pip_per_lot = 0.0
        ref_price_for_calc = entry_price_calc 
        
        profit_for_1_pip_buy = mt5.order_calc_profit(mt5.ORDER_TYPE_BUY, symbol, 1.0, ref_price_for_calc, ref_price_for_calc + pip_size_val)
        
        if profit_for_1_pip_buy is not None and profit_for_1_pip_buy > 1e-9 : # Check for > 0 (small positive)
            value_per_pip_per_lot = profit_for_1_pip_buy
        else:
            profit_for_1_pip_sell = mt5.order_calc_profit(mt5.ORDER_TYPE_SELL, symbol, 1.0, ref_price_for_calc, ref_price_for_calc - pip_size_val)
            if profit_for_1_pip_sell is not None and profit_for_1_pip_sell > 1e-9:
                 value_per_pip_per_lot = profit_for_1_pip_sell
            else:
                print(f"LivePortfolioManager: order_calc_profit failed for {symbol} (BuyProfit: {profit_for_1_pip_buy}, SellProfit: {profit_for_1_pip_sell}). LastError: {mt5.last_error()}. Using fallback pip value logic.")
                tick_value = symbol_info.trade_tick_value
                tick_size = symbol_info.trade_tick_size
                if tick_value != 0 and tick_size != 0:
                    value_per_pip_per_lot = (pip_size_val / tick_size) * tick_value
                else: 
                    print(f"CRITICAL: Pip value determination failed for {symbol}. Defaulting to a generic $10/pip/lot (HIGHLY APPROXIMATE).")
                    value_per_pip_per_lot = 10.0 

        if value_per_pip_per_lot <= 1e-9: 
            print(f"LivePortfolioManager: Calculated value_per_pip_per_lot is {value_per_pip_per_lot:.4f} for {symbol}. Cannot calculate lot size.")
            return 0.0
            
        volume = risk_amount_currency / (sl_distance_pips * value_per_pip_per_lot)
        
        volume = max(symbol_info.volume_min, volume)
        volume = min(symbol_info.volume_max, volume)
        if symbol_info.volume_step != 0:
            volume = round(volume / symbol_info.volume_step) * symbol_info.volume_step
        else: 
            volume = round(volume, 2) 
        
        volume_digits = getattr(symbol_info, 'volume_digits', 2) 
        volume = round(volume, volume_digits)

        print(f"  Lot Size Calc: Equity={account_equity:.2f}, RiskAmt={risk_amount_currency:.2f}, SLPips={sl_distance_pips:.1f}, ValPerPipLot={value_per_pip_per_lot:.4f}, Volume={volume:.{volume_digits}f}")
        return volume if volume >= symbol_info.volume_min else 0.0

    def add_trade_from_deal(self, deal_info: Any, strategy_name: str, initial_sl: float, initial_tp: float, comment: str = ""):
        if not deal_info or not hasattr(deal_info, 'entry') or deal_info.entry != mt5.DEAL_ENTRY_IN:
            return

        direction_str = "bullish" if deal_info.type == mt5.ORDER_TYPE_BUY else "bearish"
        trade = LiveTrade(
            symbol=deal_info.symbol,
            ticket_id=deal_info.position_id, 
            order_id=deal_info.order,
            entry_price=deal_info.price,
            initial_sl_price=initial_sl, 
            current_sl_price=initial_sl,
            tp_price=initial_tp,
            direction=direction_str,
            mt5_direction=deal_info.type,
            volume=deal_info.volume,
            entry_time=pd.to_datetime(deal_info.time_msc, unit='ms', utc=True), 
            strategy_name=strategy_name,
            magic_number=deal_info.magic,
            comment=getattr(deal_info, 'comment', comment) # Prefer deal comment, fallback to passed comment
        )
        self.open_trades[trade.ticket_id] = trade
        print(f"LivePortfolioManager: Added new live trade. Pos.Ticket: {trade.ticket_id}, Symbol: {trade.symbol}, Entry: {trade.entry_price:.5f}, SL: {initial_sl:.5f}, TP: {initial_tp:.5f}")

    def update_trade_sl(self, ticket_id: int, new_sl_price: float, is_be: bool = False):
        if ticket_id in self.open_trades:
            self.open_trades[ticket_id].current_sl_price = new_sl_price
            if is_be:
                self.open_trades[ticket_id].sl_moved_to_be = True
        else:
            print(f"LivePortfolioManager: Attempted to update SL for unknown trade {ticket_id}")

    def mark_trade_closed_by_logic(self, ticket_id: int, exit_price: float, exit_time: Any, reason: str, pnl_calc: Optional[float] = None):
        if ticket_id in self.open_trades:
            trade = self.open_trades[ticket_id]
            trade.status = reason
            trade.exit_price = exit_price
            trade.exit_time = pd.to_datetime(exit_time, unit='s', utc=True) if isinstance(exit_time, (int, float)) else pd.to_datetime(exit_time)
            trade.pnl_currency = pnl_calc 
            print(f"LivePortfolioManager: Marked trade {ticket_id} ({trade.symbol}) as {reason} by logic at {exit_price:.5f}. PnL: {pnl_calc if pnl_calc is not None else 'N/A'}")
        else:
            print(f"LivePortfolioManager: Attempted to close unknown trade {ticket_id} by logic.")
            
    def remove_closed_trade(self, ticket_id: int):
        if ticket_id in self.open_trades and self.open_trades[ticket_id].status != "open":
            del self.open_trades[ticket_id]

    def get_trade(self, ticket_id: int) -> Optional[LiveTrade]:
        return self.open_trades.get(ticket_id)

    def has_open_trade(self, symbol: str, magic_number: Optional[int] = None) -> bool:
        for trade in self.open_trades.values():
            if trade.symbol == symbol and trade.status == "open":
                if magic_number is None or trade.magic_number == magic_number:
                    return True
        return False

    def manage_symbol_trades(self, symbol: str, current_ltf_candle_prepared: pd.Series, 
                             ltf_ohlc_data_rolling: pd.DataFrame, # Original OHLC for BE recent H/L
                             strategy_instance: Any, 
                             magic_number_filter: Optional[int] = None):
        trades_processed_this_cycle = [] 

        # Sync with broker: identify trades closed by SL/TP at broker or manually
        current_broker_positions_tickets = {
            pos.ticket for pos in self.broker.get_open_positions(symbol=symbol, magic_number=magic_number_filter)
        }

        for ticket_id, trade in list(self.open_trades.items()): # Iterate on a copy
            if trade.symbol != symbol or trade.status != "open":
                continue
            if magic_number_filter is not None and trade.magic_number != magic_number_filter:
                continue
            
            if ticket_id not in current_broker_positions_tickets:
                print(f"  Trade {ticket_id} ({symbol}) detected as closed (not in current broker positions).")
                closing_deal = None
                # Query history for the closing deal to get accurate exit price/time/pnl
                deals = mt5.history_deals_get(position=ticket_id) 
                if deals:
                    for deal_item in sorted(deals, key=lambda d: d.time_msc, reverse=True): 
                        if deal_item.entry == mt5.DEAL_ENTRY_OUT or deal_item.entry == mt5.DEAL_ENTRY_INOUT: 
                            closing_deal = deal_item
                            break
                if closing_deal:
                    reason = "closed_by_broker_deal"
                    # Basic check if it was SL or TP based on price vs stored SL/TP
                    # This is an approximation as broker SL/TP might have been hit with slippage
                    if abs(closing_deal.price - trade.current_sl_price) < (2 * get_pip_size(symbol)):
                        reason = "closed_sl_be_broker_deal" if trade.sl_moved_to_be else "closed_sl_broker_deal"
                    elif abs(closing_deal.price - trade.tp_price) < (2 * get_pip_size(symbol)):
                        reason = "closed_tp_broker_deal"
                    self.mark_trade_closed_by_logic(ticket_id, closing_deal.price, closing_deal.time_msc / 1000.0, reason, closing_deal.profit)
                else: 
                    self.mark_trade_closed_by_logic(ticket_id, 0, time.time(), "closed_broker_sync_no_deal") # Fallback
                trades_processed_this_cycle.append(ticket_id)
                continue 

        # Manage trades that are confirmed to be still open
        for ticket_id, trade in list(self.open_trades.items()):
            if ticket_id in trades_processed_this_cycle or trade.symbol != symbol or trade.status != "open":
                continue
            if magic_number_filter is not None and trade.magic_number != magic_number_filter:
                continue

            position_details_list = self.broker.get_open_positions(ticket=ticket_id)
            if not position_details_list:
                if ticket_id not in trades_processed_this_cycle: 
                     print(f"  Trade {ticket_id} ({symbol}) disappeared between checks. Marking as closed.")
                     self.mark_trade_closed_by_logic(ticket_id, 0, time.time(), "closed_broker_sync_late_no_deal")
                     trades_processed_this_cycle.append(ticket_id)
                continue
            
            position_details = position_details_list[0]
            # Update our records with potentially modified SL/TP from broker
            if position_details.sl != 0.0 : trade.current_sl_price = position_details.sl
            if position_details.tp != 0.0 : trade.tp_price = position_details.tp 

            current_potential_R = 0.0
            risk_in_price = abs(trade.entry_price - trade.initial_sl_price)
            pip_size = get_pip_size(symbol)

            if risk_in_price > 1e-9: 
                # Use the H/L of the latest *prepared* candle for R calculation
                # current_ltf_candle_prepared is pd.Series
                candle_high = current_ltf_candle_prepared.get('high', current_ltf_candle_prepared.get('ha_high'))
                candle_low = current_ltf_candle_prepared.get('low', current_ltf_candle_prepared.get('ha_low'))

                if candle_high is None or candle_low is None: # Should not happen if data is prepared
                    print(f"Warning: Missing high/low in prepared candle for R-calc on trade {ticket_id}")
                    continue


                if trade.direction == "bullish":
                    current_potential_R = (candle_high - trade.entry_price) / risk_in_price
                elif trade.direction == "bearish":
                    current_potential_R = (trade.entry_price - candle_low) / risk_in_price
                
                trade.max_R_achieved_for_analysis = max(trade.max_R_achieved_for_analysis, min(current_potential_R, 5.0))
                
                r_levels_to_check = strategy_instance.get_r_levels_to_track() + [config.BE_SL_TRIGGER_R, 3.5, 4.0, 4.5, 5.0] # Ensure BE_SL_TRIGGER_R is checked
                for r_target in sorted(list(set(r_levels_to_check))):
                    if r_target > 5.0: continue
                    key = f'{r_target:.1f}R_achieved'
                    if not trade.r_achievements.get(key, False) and current_potential_R >= r_target:
                        trade.r_achievements[key] = True
                        if r_target == config.BE_SL_TRIGGER_R:
                             print(f"  Trade {ticket_id} ({symbol}) achieved Breakeven Trigger {r_target:.1f}R.")
                        # else:
                        #      print(f"  Trade {ticket_id} ({symbol}) achieved {r_target:.1f}R.")


            # --- Breakeven SL Logic ---
            if config.ENABLE_BREAKEVEN_SL and \
               not trade.sl_moved_to_be and \
               trade.r_achievements.get(f'{config.BE_SL_TRIGGER_R:.1f}R_achieved', False): # Check if BE R-level was hit
                
                sl_buffer_price_be = config.SL_BUFFER_PIPS * pip_size 
                entry_price_be = trade.entry_price
                sl_from_recent_hl = None
                
                try: 
                    # Use ltf_ohlc_data_rolling (original OHLC) for BE recent H/L
                    current_candle_time_in_ohlc = current_ltf_candle_prepared.name 
                    ohlc_candle_idx = ltf_ohlc_data_rolling.index.get_loc(current_candle_time_in_ohlc)
                    start_idx_be_lookback = max(0, ohlc_candle_idx - config.BE_SL_LOOKBACK_PERIOD)
                    # Slice up to, but not including, the current signal candle for lookback
                    ltf_slice_for_be_sl = ltf_ohlc_data_rolling.iloc[start_idx_be_lookback : ohlc_candle_idx]

                    if not ltf_slice_for_be_sl.empty:
                        if trade.direction == 'bullish':
                            sl_from_recent_hl = ltf_slice_for_be_sl['low'].min() - sl_buffer_price_be
                        elif trade.direction == 'bearish':
                            sl_from_recent_hl = ltf_slice_for_be_sl['high'].max() + sl_buffer_price_be
                except Exception as e_be_slice_live:
                    print(f"    Warning (Live BE): Could not get slice for BE SL H/L for Trade {trade.ticket_id}: {e_be_slice_live}")

                sl_from_fixed_pips_dist = config.BE_SL_FIXED_PIPS * pip_size
                sl_from_fixed_pips_level = (entry_price_be - sl_from_fixed_pips_dist) if trade.direction == 'bullish' else (entry_price_be + sl_from_fixed_pips_dist)

                risk_from_hl = abs(entry_price_be - sl_from_recent_hl) if sl_from_recent_hl is not None else float('inf')
                risk_from_fixed = sl_from_fixed_pips_dist

                chosen_aggressive_sl_level = sl_from_fixed_pips_level
                if sl_from_recent_hl is not None and risk_from_hl < risk_from_fixed:
                    chosen_aggressive_sl_level = sl_from_recent_hl
                
                new_be_sl_price = max(entry_price_be, chosen_aggressive_sl_level) if trade.direction == 'bullish' else min(entry_price_be, chosen_aggressive_sl_level)

                # Only modify if the new SL is different and valid
                if new_be_sl_price is not None and abs(new_be_sl_price - trade.current_sl_price) > (pip_size / 2): 
                    print(f"  Attempting to move SL to BE for trade {ticket_id} ({symbol}). New SL: {new_be_sl_price:.5f} (Current SL: {trade.current_sl_price:.5f})")
                    if self.broker.modify_position_sl_tp(trade.ticket_id, trade.symbol, new_be_sl_price, trade.tp_price):
                        self.update_trade_sl(trade.ticket_id, new_be_sl_price, is_be=True) # Mark as BE
                        print(f"    SUCCESS: Trade SL to BE (Live): ID {trade.ticket_id} new SL {new_be_sl_price:.5f}")
                    else:
                        print(f"    FAILURE: Could not modify SL to BE for trade {ticket_id} via broker.")
            
            trades_processed_this_cycle.append(ticket_id)
        
        for tid in list(set(trades_processed_this_cycle)): 
            if tid in self.open_trades and self.open_trades[tid].status != "open":
                self.remove_closed_trade(tid)

# Test section remains the same
if __name__ == '__main__':
    print("Testing LivePortfolioManager...") # ... (rest of your test code) ...
    class MockBroker:
        def get_symbol_info(self, symbol):
            class Info: pass
            i = Info()
            i.digits = 5; i.point = 0.00001; i.trade_tick_value = 1.0; i.trade_tick_size = 0.00001
            i.volume_min = 0.01; i.volume_max = 100; i.volume_step = 0.01; i.currency_profit = "USD"
            i.volume_digits = 2
            if "JPY" in symbol:
                i.digits = 3; i.point = 0.001; i.trade_tick_value = 1.0 # Simplified for JPY, assuming 1 tick = 1 USD for 1 lot
                i.trade_tick_size = 0.001
            return i
        def get_open_positions(self, symbol=None, magic_number=None, ticket=None): return []
        def modify_position_sl_tp(self, ticket,symbol,sl,tp): return True

    mock_broker = MockBroker()
    original_account_info = mt5.account_info
    mt5.account_info = lambda: type('AccountInfo', (), {'equity': 10000, 'currency': 'USD'})()
    original_order_calc_profit = mt5.order_calc_profit
    # Mock order_calc_profit to return a positive value for testing
    mt5.order_calc_profit = lambda action, sym, vol, p_open, p_close: abs(p_close - p_open) / (0.00001 if "JPY" not in sym else 0.001) * (1.0 if "JPY" not in sym else 0.0066) if vol == 1.0 else 0.01 # Approx $ per point

    portfolio = LivePortfolioManager(broker=mock_broker, account_currency="USD") # type: ignore
    config.RISK_PER_TRADE_PERCENT = 1.0

    print("\nTesting Lot Size Calculation (EURUSD):")
    vol_eurusd = portfolio.calculate_lot_size("EURUSD", sl_price_calc=1.08000, entry_price_calc=1.08200) 
    print(f"Calculated EURUSD Volume: {vol_eurusd}")

    print("\nTesting Lot Size Calculation (USDJPY):")
    vol_usdjpy = portfolio.calculate_lot_size("USDJPY", sl_price_calc=150.000, entry_price_calc=150.500) 
    print(f"Calculated USDJPY Volume: {vol_usdjpy}")

    mt5.account_info = original_account_info
    mt5.order_calc_profit = original_order_calc_profit