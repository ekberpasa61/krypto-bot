import streamlit as st
import pandas as pd
import numpy as np
import requests

st.set_page_config(page_title="Kyrpto Multi-Timeframe Dashboard", layout="wide")

st.title("💎 Kyrpto Multi-Timeframe Trading Dashboard")
st.markdown("Dynamische Strategien angepasst an den jeweiligen Zeitrahmen (1m bis 1W) mit TradingView-Integration.")

@st.cache_data(ttl=3600)
def get_top_50_pairs():
    url = "https://api.binance.com/api/v3/ticker/24hr"
    try:
        res = requests.get(url, timeout=5)
        data = res.json()
        usdt_pairs = [item for item in data if item['symbol'].endswith('USDT') and not 'UP' in item['symbol'] and not 'DOWN' in item['symbol']]
        usdt_pairs.sort(key=lambda x: float(x['quoteVolume']), reverse=True)
        return [item['symbol'] for item in usdt_pairs[:50]]
    except:
        return ["BTCUSDT", "ETHUSDT", "SOLUSDT", "XRPUSDT", "ADAUSDT"]

CRYPTO_PAIRS = get_top_50_pairs()

@st.cache_data(ttl=300)
def fetch_candles(symbol, interval, limit=500):
    url = f"https://api.binance.com/api/v3/klines?symbol={symbol}&interval={interval}&limit={limit}"
    try:
        res = requests.get(url, timeout=5)
        data = res.json()
        df = pd.DataFrame(data, columns=[
            'timestamp', 'open', 'high', 'low', 'close', 'volume',
            'close_time', 'qav', 'trades', 'tbb', 'tbq', 'ignore'
        ])
        for col in ['open', 'high', 'low', 'close', 'volume']:
            df[col] = df[col].astype(float)
        df['timestamp'] = pd.to_datetime(df['timestamp'], unit='ms')
        return df
    except:
        return pd.DataFrame()

# Session State für permanente Scan-Ergebnisse
if "scanned_results" not in st.session_state:
    st.session_state.scanned_results = None

# Sidebar Konfiguration
selected_coin = st.sidebar.selectbox("Wähle einen Coin:", CRYPTO_PAIRS)
timeframe = st.sidebar.selectbox("Zeitrahmen (Interval):", ["1m", "5m", "15m", "1h", "2h", "4h", "1d", "1w"])

# Strategie-Parameter dynamisch an Zeitrahmen anpassen
if timeframe in ["1m", "5m"]:
    fast_ema = 9
    slow_ema = 21
    rsi_threshold = 58
    holding_periods = 12
    strategy_desc = "Scalping-Modus: Sehr schnelle EMAs (9/21) & höherer RSI-Filter."
elif timeframe in ["15m", "1h"]:
    fast_ema = 20
    slow_ema = 50
    rsi_threshold = 55
    holding_periods = 16
    strategy_desc = "Intraday-Momentum: Standard EMA (20/50) & RSI >= 55."
elif timeframe in ["2h", "4h"]:
    fast_ema = 50
    slow_ema = 100
    rsi_threshold = 53
    holding_periods = 20
    strategy_desc = "Swing-Trading: Solide Trendfilter (EMA 50/100) im 2H/4H Chart."
else: # 1d, 1w
    fast_ema = 50
    slow_ema = 200
    rsi_threshold = 55
    holding_periods = 10
    strategy_desc = "Langfristiger Trend: Klassischer EMA (50/200) & RSI >= 55."

st.sidebar.markdown(f"--- \n⚙️ **Aktive Strategie ({timeframe}):**\n{strategy_desc}")

# Live-Scan Button
if st.button(f"🚀 Top 50 im Takt ({timeframe}) scannen"):
    with st.spinner(f"Scanne Märkte für {timeframe}-Strategie..."):
        signals_found = []
        for symbol in CRYPTO_PAIRS:
            df = fetch_candles(symbol, timeframe, limit=300)
            if df.empty or len(df) < slow_ema + 10:
                continue
            
            df['EMA_FAST'] = df['close'].ewm(span=fast_ema, adjust=False).mean()
            df['EMA_SLOW'] = df['close'].ewm(span=slow_ema, adjust=False).mean()
            
            delta = df['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            df['RSI'] = 100 - (100 / (1 + (gain / loss)))
            
            latest = df.iloc[-1]
            if latest['close'] > latest['EMA_SLOW'] and latest['RSI'] >= rsi_threshold:
                signals_found.append({
                    "Symbol": symbol, 
                    "Preis": round(latest['close'], 4), 
                    "RSI": round(latest['RSI'], 2)
                })
        
        st.session_state.scanned_results = pd.DataFrame(signals_found) if signals_found else pd.DataFrame()

# Scan-Ergebnisse anzeigen
if st.session_state.scanned_results is not None:
    if not st.session_state.scanned_results.empty:
        st.success(f"{len(st.session_state.scanned_results)} Setups für {timeframe} gefunden!")
        st.dataframe(st.session_state.scanned_results, use_container_width=True)
    else:
        st.info(f"Keine passenden Setups im {timeframe}-Takt gefunden.")

st.markdown("---")

# Backtest Sektion mit angepassten Parametern
st.subheader(f"📈 Backtest für {selected_coin} im {timeframe}-Takt")
st.markdown(f"**Regel:** Kurs > EMA {slow_ema} und RSI >= {rsi_threshold}. Haltedauer: {holding_periods} Kerzen.")

if st.button("🚀 Backtest starten"):
    with st.spinner(f"Führe Backtest für {selected_coin} ({timeframe}) durch..."):
        df_bt = fetch_candles(selected_coin, timeframe, limit=1000)
        
        if not df_bt.empty and len(df_bt) > slow_ema + holding_periods:
            df_bt['EMA_SLOW'] = df_bt['close'].ewm(span=slow_ema, adjust=False).mean()
            
            delta = df_bt['close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
            df_bt['RSI'] = 100 - (100 / (1 + (gain / loss)))
            
            capital = 1000.0
            position = 0
            trades = 0
            wins = 0
            
            for i in range(slow_ema, len(df_bt) - holding_periods):
                row = df_bt.iloc[i]
                if position == 0:
                    if row['close'] > row['EMA_SLOW'] and row['RSI'] >= rsi_threshold:
                        entry_price = row['close']
                        position = 1
                elif position == 1:
                    exit_price = df_bt.iloc[i + holding_periods]['close']
                    pnl_pct = (exit_price - entry_price) / entry_price
                    capital *= (1 + pnl_pct)
                    trades += 1
                    if pnl_pct > 0:
                        wins += 1
                    position = 0
            
            win_rate = (wins / trades * 100) if trades > 0 else 0
            total_return = ((capital - 1000) / 1000) * 100
            
            col1, col2, col3 = st.columns(3)
            col1.metric("Performance", f"{total_return:.2f}%", "aus $1,000 Startkapital")
            col2.metric("Trades", str(trades))
            col3.metric("Win-Rate", f"{win_rate:.1f}%")
        else:
            st.error("Nicht genügend historische Daten für diesen Zeitraum.")

st.markdown("---")

# TradingView Live-Chart Integration mit dynamischem Intervall
st.subheader(f"📊 TradingView Chart: {selected_coin} ({timeframe})")
tradingview_url = f"https://www.tradingview.com/chart/?symbol=BINANCE:{selected_coin}"
st.markdown(f"🔗 **[Auf TradingView öffnen]({tradingview_url})**", unsafe_allow_html=True)

tv_intervals = {
    "1m": "1", "5m": "5", "15m": "15", 
    "1h": "60", "2h": "120", "4h": "240", 
    "1d": "D", "1w": "W"
}
tv_int = tv_intervals.get(timeframe, "D")

# Hier wurden die JavaScript-Klammern mit {{ und }} maskiert, damit der f-string fehlerfrei läuft
tv_widget_html = f"""
<div class="tradingview-widget-container" style="height:550px;width:100%">
  <div id="tradingview_chart" style="height:100%;width:100%"></div>
  <script type="text/javascript" src="https://s3.tradingview.com/tv.js"></script>
  <script type="text/javascript">
  new TradingView.widget(
  {{
    "width": "100%",
    "height": 550,
    "symbol": "BINANCE:{selected_coin}",
    "interval": "{tv_int}",
    "timezone": "Etc/UTC",
    "theme": "dark",
    "style": "1",
    "locale": "de",
    "toolbar_bg": "#f1f3f6",
    "enable_publishing": false,
    "hide_side_toolbar": false,
    "allow_symbol_change": true,
    "container_id": "tradingview_chart"
  }});
  </script>
</div>
"""
st.components.v1.html(tv_widget_html, height=570)