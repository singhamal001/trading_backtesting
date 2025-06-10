### File: X:\AmalTrading\trading_backtesting\broker_interface.py

import MetaTrader5 as mt5
import time
from typing import List, Dict, Any, Optional, Tuple 
import pandas as pd

# Define which symbols require FOK based on your screenshots
SYMBOLS_REQUIRING_FOK_ONLY = {"AUDUSD", "GBPJPY", "CADJPY"}

class BrokerInterface:
    def __init__(self, live_data_handler_instance=None):
        self.mt5_initialized = False
        if live_data_handler_instance and live_data_handler_instance.mt5_initialized:
            self.mt5_initialized = True
        else:
            self._ensure_mt5_connection(attempt_init=True)

    def _ensure_mt5_connection(self, attempt_init=False):
        if mt5.terminal_info() is None: 
            self.mt5_initialized = False
            if attempt_init:
                print("BrokerInterface: MT5 connection lost or not initialized. Attempting to initialize.")
                from config import MT5_PATH, ACCOUNT_LOGIN, ACCOUNT_PASSWORD, ACCOUNT_SERVER 
                init_args = []
                init_kwargs = {}
                if MT5_PATH: init_args.append(MT5_PATH)
                if ACCOUNT_LOGIN:
                    init_kwargs['login'] = ACCOUNT_LOGIN
                    if ACCOUNT_PASSWORD: init_kwargs['password'] = ACCOUNT_PASSWORD
                    if ACCOUNT_SERVER: init_kwargs['server'] = ACCOUNT_SERVER
                
                if not mt5.initialize(*init_args, **init_kwargs):
                    print(f"BrokerInterface: MT5 initialize() failed, error code = {mt5.last_error()}")
                    self.mt5_initialized = False
                else:
                    self.mt5_initialized = True
                    print("BrokerInterface: MT5 re-initialized successfully.")
            else:
                print("BrokerInterface: MT5 connection not active and re-initialization not attempted.")
        else:
            self.mt5_initialized = True

    def get_symbol_info(self, symbol: str) -> Optional[Any]: 
        self._ensure_mt5_connection()
        if not self.mt5_initialized: return None
        
        info = mt5.symbol_info(symbol)
        if info is None:
            print(f"BrokerInterface: Failed to get info for {symbol}, error {mt5.last_error()}")
        return info

    def place_market_order(self, symbol: str, order_type: int, volume: float, 
                           sl_price: float, tp_price: float, 
                           magic_number: int = 0, comment: str = "") -> Optional[Any]:
        self._ensure_mt5_connection()
        if not self.mt5_initialized: return None

        symbol_info = self.get_symbol_info(symbol)
        if not symbol_info:
            return None 

        if order_type not in [mt5.ORDER_TYPE_BUY, mt5.ORDER_TYPE_SELL]:
            print(f"BrokerInterface: Invalid order type {order_type}")
            return None

        tick = mt5.symbol_info_tick(symbol)
        if not tick:
            print(f"BrokerInterface: Could not get tick for {symbol}. Cannot place order.")
            return None
            
        price = tick.ask if order_type == mt5.ORDER_TYPE_BUY else tick.bid
        if price == 0: 
            print(f"BrokerInterface: Invalid market price (0) for {symbol}. Cannot place order.")
            return None

        # Determine the correct filling mode for this symbol
        filling_mode = mt5.ORDER_FILLING_IOC # Default to IOC
        if symbol.upper() in SYMBOLS_REQUIRING_FOK_ONLY:
            filling_mode = mt5.ORDER_FILLING_FOK
            print(f"BrokerInterface: Using FOK filling mode for {symbol}")
        else:
            # For symbols like EURUSD, GBPUSD, USDJPY, BTCUSD, XAUUSD that show "Fill or Kill, Immediate or Cancel"
            # IOC is generally preferred if available as it allows partial fills if the full volume isn't there
            # at one price point, whereas FOK would reject the entire order.
            # However, if your broker's "Fill or Kill, Immediate or Cancel" means *either* is supported,
            # and IOC was failing for some reason (though less likely if listed), FOK is safer.
            # Let's stick to IOC for those that explicitly list both, assuming IOC is acceptable.
            # If you still get issues, you might default all to FOK or make this more configurable.
            pass # Defaulting to IOC is already set

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": symbol,
            "volume": volume,
            "type": order_type,
            "price": price, 
            "sl": round(sl_price, symbol_info.digits), 
            "tp": round(tp_price, symbol_info.digits),
            "deviation": 10, 
            "magic": magic_number,
            "comment": comment,
            "type_time": mt5.ORDER_TIME_GTC, 
            "type_filling": filling_mode, # Use the determined filling_mode
        }

        result = mt5.order_send(request)
        if result is None:
            print(f"BrokerInterface: order_send failed for {symbol} (result is None), error code={mt5.last_error()}")
            return None
        
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            print(f"BrokerInterface: order_send failed for {symbol}, retcode={result.retcode}, comment={result.comment}")
            return None
        
        print(f"BrokerInterface: Order request sent successfully for {symbol}. Order ID: {result.order}, Deal ID: {result.deal}, Retcode: {result.retcode}, Filling: {filling_mode}")
        
        time.sleep(0.5) 
        deal_info_list = mt5.history_deals_get(ticket=result.deal) 

        if deal_info_list and len(deal_info_list) > 0:
            # print(f"BrokerInterface: Successfully retrieved deal info for deal {result.deal}")
            return deal_info_list[0]
        else:
            # print(f"BrokerInterface: Could not retrieve deal by deal ticket {result.deal}. Trying by order ticket {result.order}.")
            deal_info_list_by_order = mt5.history_deals_get(ticket=result.order)
            if deal_info_list_by_order and len(deal_info_list_by_order) > 0:
                for deal_item in deal_info_list_by_order:
                    if deal_item.volume == result.volume and deal_item.entry == mt5.DEAL_ENTRY_IN: 
                        #  print(f"BrokerInterface: Successfully retrieved deal info by order ticket {result.order}, found matching deal {deal_item.deal}")
                         return deal_item
                # print(f"BrokerInterface: No matching entry deal found for order ticket {result.order} in history.")
            # else:
                #  print(f"BrokerInterface: Still could not retrieve deal info for order {result.order}. Last error: {mt5.last_error()}")

            # print(f"BrokerInterface: Constructing mock deal from order_send result for order {result.order}.")
            class MockDeal: 
                def __init__(self, res, sym_info):
                    self.ticket = res.deal 
                    self.order = res.order
                    self.position_id = res.order 
                    self.price = res.price 
                    self.volume = res.volume
                    self.type = res.request.type 
                    self.symbol = res.request.symbol
                    self.magic = res.request.magic
                    self.time_msc = int(time.time() * 1000) 
                    self.profit = 0.0
                    self.sl = res.request.sl
                    self.tp = res.request.tp
                    self.entry = mt5.DEAL_ENTRY_IN 
                    self.comment = res.comment
            return MockDeal(result, symbol_info)

    def get_open_positions(self, symbol: Optional[str] = None, magic_number: Optional[int] = None, ticket: Optional[int] = None) -> List[Any]: 
        self._ensure_mt5_connection()
        if not self.mt5_initialized: return []
        positions_result = []
        pos_list = None
        if ticket is not None: pos_list = mt5.positions_get(ticket=ticket)
        elif symbol: pos_list = mt5.positions_get(symbol=symbol)
        else: pos_list = mt5.positions_get()
        if pos_list is None: return []
        for p in pos_list:
            if magic_number is None or p.magic == magic_number:
                positions_result.append(p)
        return positions_result

    def close_position(self, position_ticket: int, volume: float, symbol: str, position_type: int, comment: str = "") -> Optional[Any]: 
        self._ensure_mt5_connection()
        if not self.mt5_initialized: return None
        symbol_info = self.get_symbol_info(symbol)
        if not symbol_info: return None
        close_order_type = mt5.ORDER_TYPE_SELL if position_type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        tick = mt5.symbol_info_tick(symbol)
        if not tick:
            print(f"BrokerInterface: Could not get tick for closing {symbol}. Cannot close.")
            return None
        price = tick.bid if close_order_type == mt5.ORDER_TYPE_SELL else tick.ask 
        if price == 0:
            print(f"BrokerInterface: Invalid market price (0) for closing {symbol}. Cannot close.")
            return None
        
        # Determine filling mode for closure (usually FOK or IOC is fine for market close)
        filling_mode_close = mt5.ORDER_FILLING_IOC # Default for closure
        if symbol.upper() in SYMBOLS_REQUIRING_FOK_ONLY:
            filling_mode_close = mt5.ORDER_FILLING_FOK

        request = {
            "action": mt5.TRADE_ACTION_DEAL, "symbol": symbol, "volume": volume,
            "type": close_order_type, "position": position_ticket, "price": price,
            "deviation": 20, "comment": comment, "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling_mode_close, 
        }
        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            print(f"BrokerInterface: Failed to close position {position_ticket}, retcode={result.retcode if result else 'None'}, comment={result.comment if result else ''}, error={mt5.last_error()}")
            return None
        print(f"BrokerInterface: Position {position_ticket} close request sent. Deal ID: {result.deal}")
        time.sleep(0.5)
        history_deals = mt5.history_deals_get(ticket=result.deal) 
        return history_deals[0] if history_deals and len(history_deals) > 0 else None

    def modify_position_sl_tp(self, position_ticket: int, symbol: str, new_sl: float, new_tp: float) -> bool:
        self._ensure_mt5_connection()
        if not self.mt5_initialized: return False
        symbol_info = self.get_symbol_info(symbol)
        if not symbol_info: return False
        request = {
            "action": mt5.TRADE_ACTION_SLTP, "position": position_ticket,
            "symbol": symbol, 
            "sl": round(new_sl, symbol_info.digits), "tp": round(new_tp, symbol_info.digits),
        }
        result = mt5.order_send(request)
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            print(f"BrokerInterface: Failed to modify SL/TP for position {position_ticket}, retcode={result.retcode if result else 'None'}, comment={result.comment if result else ''}, error={mt5.last_error()}")
            return False
        print(f"BrokerInterface: Position {position_ticket} SL/TP modified successfully.")
        return True

# ... (if __name__ == '__main__': test block remains the same) ...
if __name__ == '__main__':
    print("Testing BrokerInterface...")
    broker = BrokerInterface()
    if broker.mt5_initialized:
        print("BrokerInterface initialized MT5.")
        
        info = broker.get_symbol_info("EURUSD")
        if info:
            print(f"EURUSD Info: Spread={info.spread}, Digits={info.digits}, Point={info.point}, Type: {type(info)}")

        open_trades = broker.get_open_positions(magic_number=12345) 
        print(f"Open positions with magic 12345: {len(open_trades)}")
        for trade in open_trades:
            print(f"  Ticket: {trade.ticket}, Symbol: {trade.symbol}, Type: {type(trade)}")
        
        # Test with a symbol requiring FOK
        print("\nTesting order placement for CADJPY (should use FOK):")
        cadjpy_info = broker.get_symbol_info("CADJPY")
        if cadjpy_info:
            tick_cadjpy = mt5.symbol_info_tick("CADJPY")
            if tick_cadjpy and tick_cadjpy.ask > 0:
                sl_test = round(tick_cadjpy.ask - 50 * cadjpy_info.point, cadjpy_info.digits)
                tp_test = round(tick_cadjpy.ask + 100 * cadjpy_info.point, cadjpy_info.digits)
                # broker.place_market_order("CADJPY", mt5.ORDER_TYPE_BUY, 0.01, sl_test, tp_test, 111222, "Test FOK CADJPY")
            else:
                print("Could not get tick for CADJPY to test order.")
        else:
            print("Could not get info for CADJPY.")

    else:
        print("Could not initialize BrokerInterface.")