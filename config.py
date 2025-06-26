### File: X:\AmalTrading\trading_backtesting\config.py

# forex_backtester_cli/config.py
import MetaTrader5 as mt5
import pandas as pd

# --- MT5 Connection Configuration ---
MT5_PATH = r"C:\Program Files\MetaTrader 5\terminal64.exe" 
ACCOUNT_LOGIN = 686105
ACCOUNT_PASSWORD = "5rG@EpLd"
ACCOUNT_SERVER = "TenTrade-Server"

# --- Timezone Configuration ---
INTERNAL_TIMEZONE = 'UTC'

# --- Live Trading / Backtesting Behavior ---
REVERSE_TRADES = True # Set to True to reverse all trade signals

# --- Default Backtest Parameters ---
SYMBOLS = ["EURUSD", "USDJPY", "USDCHF", "USDCAD"] 

HTF_TIMEFRAME_STR = "M15" 
LTF_TIMEFRAME_STR = "M5" 

TIMEFRAME_MAP = {
    "M1": mt5.TIMEFRAME_M1, "M5": mt5.TIMEFRAME_M5, "M15": mt5.TIMEFRAME_M15,
    "M30": mt5.TIMEFRAME_M30, "H1": mt5.TIMEFRAME_H1, "H4": mt5.TIMEFRAME_H4,
    "D1": mt5.TIMEFRAME_D1, "W1": mt5.TIMEFRAME_W1, "MN1": mt5.TIMEFRAME_MN1,
}
HTF_MT5 = TIMEFRAME_MAP.get(HTF_TIMEFRAME_STR)
LTF_MT5 = TIMEFRAME_MAP.get(LTF_TIMEFRAME_STR)

TIMEDELTA_MAP = {
    "M1": pd.Timedelta(minutes=1), "M5": pd.Timedelta(minutes=5), 
    "M15": pd.Timedelta(minutes=15), "M30": pd.Timedelta(minutes=30),
    "H1": pd.Timedelta(hours=1), "H4": pd.Timedelta(hours=4),
    "D1": pd.Timedelta(days=1)
}
HTF_TIMEDELTA = TIMEDELTA_MAP.get(HTF_TIMEFRAME_STR)
if HTF_TIMEDELTA is None:
    print(f"Warning: Could not determine timedelta for HTF: {HTF_TIMEFRAME_STR}. Defaulting.")
    if HTF_TIMEFRAME_STR == "H4": HTF_TIMEDELTA = pd.Timedelta(hours=4)
    elif HTF_TIMEFRAME_STR == "M30": HTF_TIMEDELTA = pd.Timedelta(minutes=30)
    elif HTF_TIMEFRAME_STR == "H1": HTF_TIMEDELTA = pd.Timedelta(hours=1)
    else: HTF_TIMEDELTA = pd.Timedelta(days=1) 

START_DATE_STR = "2024-08-01" 
END_DATE_STR = "2025-03-31"   

SWING_IDENTIFICATION_METHOD = "zigzag" 
N_BARS_LEFT_RIGHT_FOR_SWING_HTF = 5 
N_BARS_LEFT_RIGHT_FOR_SWING_LTF = 3 
ZIGZAG_LEN_HTF = 9 
ZIGZAG_LEN_LTF = 5 

BREAK_TYPE = "close" 

INITIAL_CAPITAL = 10000
COMMISSION_PER_TRADE = 0 
SLIPPAGE_POINTS = 0    
RISK_PER_TRADE_PERCENT = 1.0 
SL_BUFFER_PIPS = 1 
TP_RR_RATIO = 2.0  

ENABLE_BREAKEVEN_SL = True 
BE_SL_TRIGGER_R = 1.0      
BE_SL_LOOKBACK_PERIOD = 5  
BE_SL_FIXED_PIPS = 15      

PIP_SIZE = {
    "EURUSD": 0.0001, "GBPUSD": 0.0001, "AUDUSD": 0.0001, "NZDUSD": 0.0001,
    "USDCAD": 0.0001, "USDCHF": 0.0001, "CADCHF": 0.0001, "EURCHF": 0.0001, "USDJPY": 0.01, # Corrected JPY pip size
    "EURJPY": 0.01, "GBPJPY": 0.01, "AUDJPY": 0.01, "CADJPY": 0.01, "CHFJPY": 0.01, "XAUUSD": 0.1
}
LOG_LEVEL = "INFO" 

ALLIGATOR_JAW_PERIOD = 13
ALLIGATOR_JAW_SHIFT = 8
ALLIGATOR_TEETH_PERIOD = 8
ALLIGATOR_TEETH_SHIFT = 5
ALLIGATOR_LIPS_PERIOD = 5
ALLIGATOR_LIPS_SHIFT = 3
ALLIGATOR_SMMA_SOURCE = 'ha_median' 

# ACTIVE_STRATEGY_NAME = "ZLSMAWithFilters"  
# ACTIVE_STRATEGY_NAME = "HAAlligatorMACD" 
ACTIVE_STRATEGY_NAME = "HAAdaptiveMACD" # Set new strategy as active

STRATEGY_SPECIFIC_PARAMS = {
    "ChochHa": {
        "BREAK_TYPE": "close", 
        "TP_RR_RATIO": 1.5,
        "R_LEVELS_TO_TRACK": [1.0, 1.5, 2.0, 2.5, 3.0] 
    },
    "ChochHaSma": { 
        "SMA_PERIOD": 9,
        "SL_FIXED_PIPS": 10,
        "SL_HA_SWING_CANDLES": 5, 
        "TP_RR_RATIO": 2.0,       
        "HTF_BREAK_TYPE": "close", 
        "R_LEVELS_TO_TRACK": [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0] 
    },
    "ZLSMAWithFilters": {
        "ZLSMA_LENGTH": 32,
        "ZLSMA_SOURCE": "close",
        "TP_RR_RATIO": 2.0,
        "SL_ATR_PERIOD": 14, 
        "SL_ATR_MULTIPLIER": 1.5,
        "R_LEVELS_TO_TRACK": [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0],
        "USE_RANGE_FILTER_HTF": True, 
        "RANGE_FILTER_LENGTH": 20,    
        "RANGE_FILTER_MULT": 1.0,     
        "RANGE_FILTER_ATR_LEN": 100,  
        "USE_ADAPTIVE_MACD_FILTER": True, 
        "ADAPTIVE_MACD_R2_PERIOD": 20, 
        "ADAPTIVE_MACD_FAST": 10,
        "ADAPTIVE_MACD_SLOW": 12, 
        "ADAPTIVE_MACD_SIGNAL": 9,
        "HTF_BREAK_TYPE_ZLSMA": "close" # Example if you want strategy specific break type
    },
    "HAAlligatorMACD": {
        "TP_RR_RATIO": 2.0,
        "R_LEVELS_TO_TRACK": [1.0, 1.5, 2.0], 
        "ALLIGATOR_JAW_PERIOD": 13, "ALLIGATOR_JAW_SHIFT": 8,
        "ALLIGATOR_TEETH_PERIOD": 8, "ALLIGATOR_TEETH_SHIFT": 5,
        "ALLIGATOR_LIPS_PERIOD": 5, "ALLIGATOR_LIPS_SHIFT": 3,
        "ALLIGATOR_SMMA_SOURCE": 'ha_median', 
        "ADAPTIVE_MACD_R2_PERIOD": 20, "ADAPTIVE_MACD_FAST": 10,      
        "ADAPTIVE_MACD_SLOW": 20, "ADAPTIVE_MACD_SIGNAL": 9,
        "HA_STRUCTURAL_LOOKBACK": 50, 
        "ALLIGATOR_TREND_CONFIRM_BARS": 3,
        "HTF_BREAK_TYPE_HA_ALLIGATOR": "close"
    },
    "HAAdaptiveMACD": {
        "TP_RR_RATIO": 2.0,
        "R_LEVELS_TO_TRACK": [1.0, 1.5, 2.0, 2.5, 3.0],
        # Adaptive MACD params (can reuse from ZLSMA or define specific ones)
        "ADAPTIVE_MACD_R2_PERIOD": 20, 
        "ADAPTIVE_MACD_FAST": 12,
        "ADAPTIVE_MACD_SLOW": 26,
        "ADAPTIVE_MACD_SIGNAL": 9,
        "SL_HA_SIGNAL_CANDLE_BUFFER_PIPS": 2,
        "HTF_BREAK_TYPE": "close"
    }
}

if HTF_MT5 is None: raise ValueError(f"Invalid HTF_TIMEFRAME_STR: {HTF_TIMEFRAME_STR}")
if LTF_MT5 is None: raise ValueError(f"Invalid LTF_TIMEFRAME_STR: {LTF_TIMEFRAME_STR}")

ENABLE_TIME_FILTER = True
ALLOWED_TRADING_UTC_START_HOUR = 0 
ALLOWED_TRADING_UTC_START_MINUTE = 31 
ALLOWED_TRADING_UTC_END_HOUR = 19   
ALLOWED_TRADING_UTC_END_MINUTE = 29 

print("Config loaded.")
