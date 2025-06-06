# test_plotly_export.py
import plotly.graph_objects as go
import plotly
import os

print("Attempting to create a simple Plotly figure...")
fig = go.Figure(data=[go.Scatter(x=[1, 2, 3], y=[4, 1, 2])])
output_path = "test_plotly_fig.html"

print(f"Attempting to save figure to {output_path} using pio.write_image...")
try:
    # Using the explicit pio.write_image as per docs
    plotly.offline.plot(fig, filename='canada_offline.html') 
    print(f"Figure saved successfully to {output_path}!")
    if os.path.exists(output_path):
        print("File exists.")
    else:
        print("File was NOT created despite no error.")
except Exception as e:
    print(f"Error during pio.write_image: {e}")
    if "kaleido" in str(e).lower() or "command not found" in str(e).lower() or "failed to start" in str(e).lower():
        print("This strongly suggests a Kaleido installation or PATH issue.")
        print("Please ensure Kaleido is installed correctly in your 'trading_env' environment.")
        print("Try: pip install kaleido")
        print("Or: conda install -c conda-forge python-kaleido")
    elif "timeout" in str(e).lower():
        print("Kaleido process timed out. This can happen with complex figures or resource issues, but unlikely for this simple test.")