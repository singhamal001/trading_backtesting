# forex_backtester_cli/plotly_plotting.py
import plotly.graph_objects as go
import plotly.offline as offline # For saving HTML
import pandas as pd
import os
import MetaTrader5 as mt5 
from data_handler import fetch_historical_data 

def tf_mt5_to_minutes(tf_mt5_val: int) -> int:
    if tf_mt5_val == mt5.TIMEFRAME_M1: return 1
    if tf_mt5_val == mt5.TIMEFRAME_M5: return 5
    if tf_mt5_val == mt5.TIMEFRAME_M15: return 15
    if tf_mt5_val == mt5.TIMEFRAME_M30: return 30
    if tf_mt5_val == mt5.TIMEFRAME_H1: return 60
    if tf_mt5_val == mt5.TIMEFRAME_H4: return 240
    if tf_mt5_val == mt5.TIMEFRAME_D1: return 1440
    print(f"Warning: Unknown MT5 timeframe constant {tf_mt5_val} in tf_mt5_to_minutes. Defaulting to 60.")
    return 60 

def plot_trade_chart_plotly(trade_info: dict, 
                            session_results_path: str,
                            htf_plot_candles_lookback: int = 50,
                            ltf_plot_candles_lookback: int = 200,
                            ltf_plot_candles_forward: int = 100
                            ):
    overall_trade_id = trade_info.get('overall_trade_id', trade_info.get('id', 'UnknownID')) 
    # print(f"  DEBUG_PLOT: Entered plot_trade_chart_plotly for Trade ID {overall_trade_id}") # Keep if needed
    
    symbol = trade_info['symbol']
    entry_time = pd.to_datetime(trade_info['entry_time'])
    entry_price = trade_info['entry_price']
    sl_price = trade_info['sl_price']
    tp_price = trade_info['tp_price']
    direction = trade_info['direction']
    status = trade_info['status']
    exit_time = pd.to_datetime(trade_info.get('exit_time')) if trade_info.get('exit_time') else None
    exit_price = trade_info.get('exit_price')

    outcome_folder = "Win" if "tp" in status else "Loss" if "sl" in status else "Other"
    direction_folder = "Longs" if direction == "bullish" else "Shorts"
    trade_plot_dir = os.path.join(session_results_path, outcome_folder, direction_folder, f"Trade_{overall_trade_id}_{symbol}")
    os.makedirs(trade_plot_dir, exist_ok=True)

    plot_timeframes = {
        "H4": (mt5.TIMEFRAME_H4, htf_plot_candles_lookback, "HTF_Context"), 
        "H1": (mt5.TIMEFRAME_H1, 100, "H1_Context"),
        "M30": (mt5.TIMEFRAME_M30, 150, "M30_Context"),
        "M15": (mt5.TIMEFRAME_M15, ltf_plot_candles_lookback, "M15_Context"),
        "M5": (mt5.TIMEFRAME_M5, ltf_plot_candles_lookback, "M5_EntryDetail") 
    }

    for tf_str, (tf_mt5, lookback_cfg, suffix) in plot_timeframes.items():
        # print(f"    DEBUG_PLOT: Plotting {tf_str} for trade {overall_trade_id}...") 
        minutes_for_lookback = tf_mt5_to_minutes(tf_mt5) * (lookback_cfg + 20) 
        minutes_for_forward = tf_mt5_to_minutes(tf_mt5) * (ltf_plot_candles_forward if tf_str == "M5" else 30) 
        fetch_start_dt = entry_time - pd.Timedelta(minutes=minutes_for_lookback)
        fetch_end_dt = entry_time + pd.Timedelta(minutes=minutes_for_forward)

        # print(f"      DEBUG_PLOT: Fetching data for {tf_str} from {fetch_start_dt.strftime('%Y-%m-%d %H:%M:%S')} to {fetch_end_dt.strftime('%Y-%m-%d %H:%M:%S')}")
        current_tf_data = fetch_historical_data(symbol, tf_mt5, 
                                                fetch_start_dt.strftime("%Y-%m-%d"), 
                                                fetch_end_dt.strftime("%Y-%m-%d"))   
            
        if current_tf_data is None or current_tf_data.empty:
            print(f"  Warning: Could not fetch data for {tf_str} plot for trade {overall_trade_id}.")
            continue
        
        # print(f"      DEBUG_PLOT: Slicing data for {tf_str} plot...")
        indexer_pos = current_tf_data.index.get_indexer([entry_time], method='ffill')[0]
        if indexer_pos == -1: indexer_pos = current_tf_data.index.get_indexer([entry_time], method='bfill')[0]
        if indexer_pos == -1: 
            print(f"  Warning: Entry time {entry_time} could not be located in fetched {tf_str} data for trade {overall_trade_id}. Plotting approximate window.")
            plot_slice = current_tf_data[
                (current_tf_data.index >= entry_time - pd.Timedelta(minutes=tf_mt5_to_minutes(tf_mt5) * lookback_cfg)) &
                (current_tf_data.index <= entry_time + pd.Timedelta(minutes=tf_mt5_to_minutes(tf_mt5) * (ltf_plot_candles_forward if tf_str == "M5" else 20)))
            ]
        else:
            entry_idx_in_tf = indexer_pos
            plot_start_idx = max(0, entry_idx_in_tf - lookback_cfg + 1) 
            plot_end_idx_offset = ltf_plot_candles_forward if tf_str == "M5" else 20
            plot_end_idx = min(len(current_tf_data), entry_idx_in_tf + plot_end_idx_offset + 1) 
            plot_slice = current_tf_data.iloc[plot_start_idx:plot_end_idx]
        
        if plot_slice.empty:
            print(f"  Warning: Plot slice empty for {tf_str} for trade {overall_trade_id}.")
            continue
            
        fig = go.Figure(data=[go.Candlestick(x=plot_slice.index,
                                             open=plot_slice['open'], high=plot_slice['high'],
                                             low=plot_slice['low'], close=plot_slice['close'])])
        shapes = []
        annotations = []
        plot_entry_time = entry_time
        if not plot_slice.empty:
            if entry_time < plot_slice.index[0]: plot_entry_time = plot_slice.index[0]
            if entry_time > plot_slice.index[-1]: plot_entry_time = plot_slice.index[-1]

        shapes.append(dict(type="line", xref="x", yref="y", x0=plot_entry_time, y0=entry_price, x1=plot_slice.index[-1] if not plot_slice.empty else plot_entry_time, y1=entry_price, line=dict(color="blue", width=1, dash="dash")))
        annotations.append(dict(x=plot_entry_time, y=entry_price, text=f"E {entry_price:.5f}", showarrow=False, font=dict(color="blue"), xshift=-30, yshift=10 if direction == "bearish" else -10))
        
        shapes.append(dict(type="line", xref="x", yref="y", x0=plot_slice.index[0] if not plot_slice.empty else plot_entry_time, y0=sl_price, x1=plot_slice.index[-1] if not plot_slice.empty else plot_entry_time, y1=sl_price, line=dict(color="red", width=1, dash="dashdot")))
        annotations.append(dict(x=plot_slice.index[0] if not plot_slice.empty else plot_entry_time, y=sl_price, text=f"SL {sl_price:.5f}", showarrow=False, xanchor="left", yanchor="bottom" if direction == "bullish" else "top", font=dict(color="red")))

        shapes.append(dict(type="line", xref="x", yref="y", x0=plot_slice.index[0] if not plot_slice.empty else plot_entry_time, y0=tp_price, x1=plot_slice.index[-1] if not plot_slice.empty else plot_entry_time, y1=tp_price, line=dict(color="green", width=1, dash="dashdot")))
        annotations.append(dict(x=plot_slice.index[0] if not plot_slice.empty else plot_entry_time, y=tp_price, text=f"TP {tp_price:.5f}", showarrow=False, xanchor="left", yanchor="top" if direction == "bullish" else "bottom", font=dict(color="green")))

        if exit_time and exit_price and not plot_slice.empty and exit_time >= plot_slice.index[0] and exit_time <= plot_slice.index[-1]:
            exit_marker_color = "darkred" if "sl" in status else "darkgreen" if "tp" in status else "grey"
            shapes.append(dict(type="line", xref="x", yref="paper", x0=exit_time, y0=0, x1=exit_time, y1=1, line=dict(color=exit_marker_color, width=2, dash="dot")))
            annotations.append(dict(x=exit_time, y=exit_price, text=f"X {exit_price:.5f}", showarrow=True, arrowhead=1, font=dict(color=exit_marker_color, size=10), ax=20, ay=-30))

        fig.update_layout(
            title=f"T{overall_trade_id}:{symbol} {tf_str} ({direction[:1].upper()}) E@{entry_price:.4f} SL@{sl_price:.4f} TP@{tp_price:.4f} Status:{status}",
            xaxis_title="Time (UTC)", yaxis_title="Price",
            xaxis_rangeslider_visible=True, # Enable rangeslider for HTML interactivity
            shapes=shapes, annotations=annotations,
            margin=dict(l=50, r=50, t=60, b=50) 
        )
        
        plot_filename_html = os.path.join(trade_plot_dir, f"Trade_{overall_trade_id}_{symbol}_{suffix}.html") # Save as .html
        # print(f"      DEBUG_PLOT: Attempting to save {tf_str} plot to {plot_filename_html}...")
        try:
            offline.plot(fig, filename=plot_filename_html, auto_open=False) # Use offline.plot
            print(f"    Chart saved: {plot_filename_html}")
        except Exception as e:
            print(f"    Error saving plotly HTML chart {plot_filename_html}: {e}")
        # print(f"    DEBUG_PLOT: Finished plotting {tf_str} for trade {overall_trade_id}.")

    # print(f"  DEBUG_PLOT: Exiting plot_trade_chart_plotly for Trade ID {overall_trade_id}")