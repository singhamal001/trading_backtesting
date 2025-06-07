### File: X:\AmalTrading\trading_backtesting\indicators.py

# forex_backtester_cli/indicators.py
import pandas as pd
import numpy as np
from scipy.stats import linregress # For linear regression

def calculate_sma(series: pd.Series, length: int) -> pd.Series:
    return series.rolling(window=length).mean()

def calculate_smma(series: pd.Series, length: int) -> pd.Series:
    """Calculates Smoothed Moving Average (SMMA) / Wilder's Smoothing."""
    # SMMA(i) = (SMMA(i-1) * (length - 1) + series(i)) / length
    # First value is a simple moving average.
    smma = pd.Series(np.nan, index=series.index, dtype=float)
    if len(series) == 0 or length <= 0:
        return smma
    if length > len(series): # Not enough data for even one SMA
        return smma

    # Calculate initial SMA for the first value
    # Ensure we only calculate if we have enough data points for the first SMA
    if len(series) >= length:
        smma.iloc[length-1] = series.iloc[:length].mean()
    else: # Should not happen if length > len(series) check is done, but defensive
        return smma

    # Apply recursive formula for subsequent values
    for i in range(length, len(series)):
        if pd.isna(smma.iloc[i-1]): # Should not happen after first SMA if data is continuous
             # Fallback: recalculate SMA for current window if prev SMMA is NaN
             # This might happen if series has internal NaNs not handled before this function
            current_window = series.iloc[i-length+1:i+1]
            if not current_window.isna().any():
                smma.iloc[i] = current_window.mean()
            # else smma.iloc[i] remains NaN
        else:
            smma.iloc[i] = (smma.iloc[i-1] * (length - 1) + series.iloc[i]) / length
    return smma


def calculate_atr(high: pd.Series, low: pd.Series, close: pd.Series, length: int) -> pd.Series:
    if not (isinstance(high, pd.Series) and isinstance(low, pd.Series) and isinstance(close, pd.Series)):
        raise TypeError("Inputs high, low, close must be pandas Series.")
    if not (len(high) == len(low) == len(close)):
        raise ValueError("Inputs high, low, close must have the same length.")

    prev_close = close.shift(1)
    tr1 = pd.Series(high - low)
    tr2 = pd.Series(abs(high - prev_close))
    tr3 = pd.Series(abs(low - prev_close))
    
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    # Using EWM for ATR (Wilder's smoothing)
    atr = tr.ewm(alpha=1/length, adjust=False, min_periods=length).mean() 
    return atr

def calculate_linreg_value(series: pd.Series, length: int) -> pd.Series:
    """Calculates the endpoint of a linear regression line over a rolling window."""
    if len(series) < length:
        return pd.Series(np.nan, index=series.index)
    
    linreg_values = pd.Series(np.nan, index=series.index)
    x = np.arange(length)
    for i in range(length - 1, len(series)):
        y_window = series.iloc[i - length + 1 : i + 1].values
        if np.isnan(y_window).any() or len(y_window) < length: 
            continue
        slope, intercept, r_value, p_value, std_err = linregress(x, y_window)
        linreg_values.iloc[i] = slope * (length - 1) + intercept 
    return linreg_values

def calculate_zlsma(series: pd.Series, length: int) -> pd.Series:
    lsma = calculate_linreg_value(series, length)
    lsma_filled = lsma.copy()
    if pd.isna(lsma_filled.iloc[length-1]) and length*2-1 < len(lsma_filled) : 
        first_valid_lsma_idx = lsma_filled.first_valid_index()
        if first_valid_lsma_idx is not None:
            lsma_filled.fillna(method='bfill', limit=length*2, inplace=True) 
            lsma_filled.fillna(method='ffill', inplace=True) 

    lsma2 = calculate_linreg_value(lsma_filled, length)
    
    eq = lsma - lsma2 
    zlsma = lsma + eq
    return zlsma

def calculate_range_filter_bands(close: pd.Series, length: int, atr_length: int, atr_mult: float, high: pd.Series, low: pd.Series):
    ma = calculate_sma(close, length)
    atr_values = calculate_atr(high, low, close, atr_length) * atr_mult
    
    is_in_range = pd.Series(False, index=close.index)
    range_top = pd.Series(np.nan, index=close.index)
    range_bottom = pd.Series(np.nan, index=close.index)

    for i in range(length -1, len(close)):
        if pd.isna(ma.iloc[i]) or pd.isna(atr_values.iloc[i]):
            continue
            
        count = 0
        for k in range(length): 
            if i-k < 0: break
            if abs(close.iloc[i-k] - ma.iloc[i]) > atr_values.iloc[i]:
                count += 1
        
        if count == 0: 
            is_in_range.iloc[i] = True
            range_top.iloc[i] = ma.iloc[i] + atr_values.iloc[i]
            range_bottom.iloc[i] = ma.iloc[i] - atr_values.iloc[i]
            
    return is_in_range, range_top, range_bottom


def calculate_adaptive_macd(close: pd.Series, r2_period: int, fast_len: int, slow_len: int, signal_len: int):
    time_idx = pd.Series(np.arange(len(close)), index=close.index)
    
    def rolling_corr_with_time(window_series):
        if len(window_series) < r2_period : return np.nan # Ensure enough points for rolling window
        if window_series.isna().any(): return np.nan # Skip if NaNs in window
        if len(window_series) < 2: return np.nan 
        
        # Ensure the x-axis for linregress matches the window length
        window_time_idx = np.arange(len(window_series))
        try:
            slope, intercept, r_value, p_value, std_err = linregress(window_time_idx, window_series.values)
            return r_value**2
        except ValueError: # Handle cases where linregress might fail (e.g. all y values are same)
            return 0.0 # Or np.nan, depending on desired behavior

    r_squared_series = close.rolling(window=r2_period).apply(rolling_corr_with_time, raw=False)
    r2_factor = 0.5 * (r_squared_series) + 0.5 
    r2_factor.fillna(0.5, inplace=True) 

    a1 = 2 / (fast_len + 1)
    a2 = 2 / (slow_len + 1)

    term1_k = (1 - a1) * (1 - a2)
    term2_k = 1e9 # Default large value
    if (1 - a2) != 0 : # Avoid division by zero
        term2_k = (1 - a1) / (1 - a2) 
    
    K_series = r2_factor * term1_k + (1 - r2_factor) * term2_k
    
    macd_line = pd.Series(np.nan, index=close.index)
    close_diff = close.diff()
    
    if len(close) > 2:
        macd_line.iloc[0] = 0.0 
        cd1 = close_diff.iloc[1] if not pd.isna(close_diff.iloc[1]) else 0
        m0 = macd_line.iloc[0] if not pd.isna(macd_line.iloc[0]) else 0
        macd_line.iloc[1] = cd1 * (a1 - a2) + (-a2 - a1 + 2) * m0
        
        initial_K = K_series.bfill().iloc[0] if not K_series.empty and not K_series.bfill().empty else 0.5 

        for i in range(2, len(close)):
            cd = close_diff.iloc[i] if not pd.isna(close_diff.iloc[i]) else 0
            m1 = macd_line.iloc[i-1] if not pd.isna(macd_line.iloc[i-1]) else 0
            m2 = macd_line.iloc[i-2] if not pd.isna(macd_line.iloc[i-2]) else 0
            k_val = K_series.iloc[i] if not pd.isna(K_series.iloc[i]) else initial_K
            
            macd_line.iloc[i] = cd * (a1 - a2) + (-a2 - a1 + 2) * m1 - k_val * m2
    
    signal_line = macd_line.ewm(span=signal_len, adjust=False, min_periods=signal_len).mean()
    histogram = macd_line - signal_line
    
    return macd_line, signal_line, histogram

def calculate_alligator(
    source_series: pd.Series, 
    jaw_period: int, jaw_shift: int,
    teeth_period: int, teeth_shift: int,
    lips_period: int, lips_shift: int
) -> tuple[pd.Series, pd.Series, pd.Series]:
    """
    Calculates Williams Alligator lines (Jaw, Teeth, Lips).
    The returned series are the SMMA values *without* the plotting shift applied.
    The shift should be handled by the strategy logic when accessing these values.
    """
    jaw = calculate_smma(source_series, jaw_period)
    teeth = calculate_smma(source_series, teeth_period)
    lips = calculate_smma(source_series, lips_period)
    return jaw, teeth, lips