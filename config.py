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

BREAK_TYPE = "close" # Default break type, can be overridden by strategy

INITIAL_CAPITAL = 10000
COMMISSION_PER_TRADE = 0 
SLIPPAGE_POINTS = 0    
RISK_PER_TRADE_PERCENT = 1.0 
SL_BUFFER_PIPS = 2 
TP_RR_RATIO = 1.0  # <<< ADD THIS DEFAULT GLOBAL VALUE

PIP_SIZE = {
    "EURUSD": 0.0001, "GBPUSD": 0.0001, "AUDUSD": 0.0001, "NZDUSD": 0.0001,
    "USDCAD": 0.0001, "USDCHF": 0.0001, "USDJPY": 0.01,
    "EURJPY": 0.01, "GBPJPY": 0.01, "AUDJPY": 0.01, "XAUUSD": 0.01
}
LOG_LEVEL = "INFO" 

ACTIVE_STRATEGY_NAME = "ChochHaSma"  

STRATEGY_SPECIFIC_PARAMS = {
    "ChochHa": {
        "BREAK_TYPE": "close", 
        "TP_RR_RATIO": 1.5,
        "R_LEVELS_TO_TRACK": [1.0, 1.5, 2.0, 2.5, 3.0] 
    },
    "ChochHaSma": { # Parameters for the new strategy
        "SMA_PERIOD": 9,
        "SL_FIXED_PIPS": 10,
        "SL_HA_SWING_CANDLES": 5, # Number of HA candles before entry to check for swing high/low
        "TP_RR_RATIO": 2.0,       # Example: default to 1:2 R:R for this strategy
        "HTF_BREAK_TYPE": "close", # CHoCH break type on HTF
        "R_LEVELS_TO_TRACK": [1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0, 4.5, 5.0] # Track more R-levels
    },
}

if HTF_MT5 is None: raise ValueError(f"Invalid HTF_TIMEFRAME_STR: {HTF_TIMEFRAME_STR}")
if LTF_MT5 is None: raise ValueError(f"Invalid LTF_TIMEFRAME_STR: {LTF_TIMEFRAME_STR}")

# --- Trading Session Time Filter ---
ENABLE_TIME_FILTER = True
# Times are in UTC. 1:00 AM IST is 20:30 UTC previous day. 6:00 AM IST is 00:30 UTC current day.
# This means we want to AVOID trading when UTC hour is 20, 21, 22, 23 (of previous day for IST)
# AND 0 (until 00:29 UTC) of the current day.
# Simpler: Define allowed UTC hours.
# Example: If IST trading is 9:00 AM to 11:00 PM IST
# 9:00 AM IST = 03:30 UTC
# 11:00 PM IST = 17:30 UTC
# So, allowed UTC hours might be from 3 to 17.

# Let's define the NO-TRADE PERIOD in UTC
# 1:00 AM IST = 19:30 UTC on the *previous day* if we consider a continuous timeline,
# or more simply, for a given day:
# 1:00 AM IST is the day's 01:00+05:30 = day's (01-05):(00-30) UTC = (day-1) 20:30 UTC
# 6:00 AM IST is the day's 06:00+05:30 = day's (06-05):(00-30) UTC = day's 00:30 UTC

# No trade from 20:30 UTC to 00:30 UTC (which spans across midnight UTC)
# This means:
# - Don't trade if hour is 21, 22, 23
# - Don't trade if hour is 0 and minute < 30
# - Don't trade if hour is 20 and minute >= 30

# More direct: Define the NO TRADE UTC interval.
# For 1:00 AM IST to 6:00 AM IST:
# Start No-Trade (UTC): (1 - 5.5 + 24) % 24 = 19.5  => 19:30 UTC
# End No-Trade (UTC):   (6 - 5.5 + 24) % 24 = 0.5   => 00:30 UTC
# This interval crosses midnight UTC.
# So, no trade if (time.hour > 19 or (time.hour == 19 and time.minute >=30)) OR
#                 (time.hour == 0 and time.minute < 30)

# Let's define it as a list of (start_utc_hour, start_utc_minute, end_utc_hour, end_utc_minute)
# For simplicity, let's use whole hours for now and refine if needed.
# 1:00 AM IST is roughly 19:30 UTC (previous day) to 20:00 UTC
# 6:00 AM IST is roughly 00:00 UTC to 00:30 UTC
# So, avoid UTC hours 20, 21, 22, 23, and hour 0 (until 00:30)
# This is tricky with simple hour checks due to crossing midnight.

# Alternative: Define ALLOWED trading hours in UTC.
# If IST trading is from 6:01 AM to 00:59 AM (next day IST)
# 6:01 AM IST = 00:31 UTC
# 00:59 AM IST (next day) = 19:29 UTC (current day)
# So, allowed UTC hours: 00:31 UTC to 19:29 UTC
ALLOWED_TRADING_UTC_START_HOUR = 0 # Inclusive
ALLOWED_TRADING_UTC_START_MINUTE = 31 # Inclusive
ALLOWED_TRADING_UTC_END_HOUR = 19   # Inclusive
ALLOWED_TRADING_UTC_END_MINUTE = 29 # Inclusive

print("Config loaded.")