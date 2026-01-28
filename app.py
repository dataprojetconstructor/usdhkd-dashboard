import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import plotly.graph_objects as go
from datetime import datetime, timedelta

# ==========================================
# 1. CONFIGURATION & STYLE
# ==========================================
st.set_page_config(
    page_title="USD/HKD Sentinel Pro",
    page_icon="🇭🇰",
    layout="wide",
    initial_sidebar_state="collapsed"
)

st.markdown("""
    <style>
    div[data-testid="metric-container"] {
        background-color: #161b22;
        border: 1px solid #30363d;
        padding: 15px;
        border-radius: 8px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }
    .live-badge {
        background-color: #00C805;
        color: black;
        padding: 4px 8px;
        border-radius: 4px;
        font-weight: bold;
        font-size: 0.8em;
        vertical-align: middle;
    }
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 2. PARAMÈTRES
# ==========================================
with st.sidebar:
    st.header("⚙️ Configuration")
    SEUIL_SPREAD = st.number_input("Seuil Spread Achat (%)", value=0.50, step=0.05)
    SEUIL_LIQ = st.number_input("Seuil Liquidité (M HKD)", value=10000)
    
    st.divider()
    if st.button("🔄 Forcer l'actualisation"):
        st.rerun()

# ==========================================
# 3. MOTEUR DE DONNÉES
# ==========================================
class HKMA_Data:
    BASE_URL = "https://api.hkma.gov.hk/public/market-data-and-statistics"
    
    @staticmethod
    def get_history():
        headers = {"User-Agent": "Mozilla/5.0"}
        # On récupère 60 jours pour avoir une belle courbe de liquidité
        params_hist = {"pagesize": "60", "sortby": "end_of_date", "sortorder": "desc"}
        
        # A. LIQUIDITÉ
        liq_history = []
        try:
            url_liq = f"{HKMA_Data.BASE_URL}/daily-monetary-statistics/daily-figures-interbank-liquidity"
            r = requests.get(url_liq, params=params_hist, headers=headers, timeout=6)
            if r.status_code == 200:
                records = r.json()['result']['records']
                for rec in records:
                    liq_history.append({
                        'date': rec.get('end_of_date'),
                        'balance': float(rec.get('closing_balance', 0))
                    })
        except: pass

        # B. HIBOR
        hibor_history = []
        try:
            url_h = f"{HKMA_Data.BASE_URL}/monthly-statistical-bulletin/er-ir/hk-interbank-ir-daily"
            params_h = {"pagesize": "60", "segment": "hibor.fixing", "sortby": "end_of_day", "sortorder": "desc"}
            r_h = requests.get(url_h, params=params_h, headers=headers, timeout=6)
            if r_h.status_code == 200:
                records = r_h.json()['result']['records']
                for rec in records:
                    val = float(rec.get('ir_3m', rec.get('ir_hibor_3m', 0)))
                    hibor_history.append({
                        'date': rec.get('end_of_day'),
                        'rate': val
                    })
        except: pass
        
        return liq_history, hibor_history

def get_market_data():
    # 1. YAHOO
    ticker_spot = yf.Ticker("USDHKD=X")
    hist_spot = ticker_spot.history(period="1mo")
    
    ticker_us = yf.Ticker("^IRX")
    hist_us = ticker_us.history(period="1mo")
    
    # 2. HKMA
    liq_hist, hibor_hist = HKMA_Data.get_history()
    
    df_liq = pd.DataFrame(liq_hist) if liq_hist else pd.DataFrame()
    df_hibor = pd.DataFrame(hibor_hist) if hibor_hist else pd.DataFrame()
    
    # Conversion dates
    if not df_liq.empty:
        df_liq['date_dt'] = pd.to_datetime(df_liq['date'])
    if not df_hibor.empty:
        df_hibor['date_dt'] = pd.to_datetime(df_hibor['date'])

    current_data = {
        "spot": hist_spot['Close'].iloc[-1],
        "spot_delta": hist_spot['Close'].iloc[-1] - hist_spot['Close'].iloc[-2],
        "us_rate": hist_us['Close'].iloc[-1],
        "us_delta": hist_us['Close'].iloc[-1] - hist_us['Close'].iloc[-2],
        "hk_rate": df_hibor['rate'].iloc[0] if not df_hibor.empty else 0,
        "hk_delta": (df_hibor['rate'].iloc[0] - df_hibor['rate'].iloc[1]) if len(df_hibor) > 1 else 0,
        "liq": df_liq['balance'].iloc[0] if not df_liq.empty else 0,
        "liq_delta": (df_liq['balance'].iloc[0] - df_liq['balance'].iloc[1]) if len(df_liq) > 1 else 0,
        "last_update_hk": df_liq['date'].iloc[0] if not df_liq.empty else "N/A"
    }
    
    return current_data, hist_spot, hist_us, df_hibor, df_liq

# ==========================================
# 4. AFFICHAGE DU DASHBOARD
# ==========================================

col_title, col_badge = st.columns([3, 1])
with col_title:
    st.title("🇭🇰 USD/HKD Sentinel")
    st.caption("Station de Trading : Arbitrage Taux & Liquidité")

with st.spinner('Synchronisation des données...'):
    try:
        data, h_spot, h_us, h_hk, h_liq = get_market_data()
        with col_badge:
            st.markdown(f"<br><span class='live-badge'>🟢 LIVE DATA</span>", unsafe_allow_html=True)
            st.caption(f"Data HKMA : {data['last_update_hk']}")
    except Exception as e:
        st.error(f"Erreur : {e}")
        st.stop()

spread = data['us_rate'] - data['hk_rate']
spread_prev = (data['us_rate'] - data['us_delta']) - (data['hk_rate'] - data['hk_delta'])
spread_delta = spread - spread_prev

# --- SECTION 1 : KPIS ---
col1, col2, col3, col4 = st.columns(4)
col1.metric("Prix Spot", f"{data['spot']:.4f}", f"{data['spot_delta']:.4f}", delta_color="inverse")
col2.metric("Taux US (3M)", f"{data['us_rate']:.2f}%", f"{data['us_delta']:.2f}%")
col3.metric("Taux HK (HIBOR)", f"{data['hk_rate']:.2f}%", f"{data['hk_delta']:.2f}%", delta_color="inverse")
col4.metric("Liquidité", f"{data['liq']:,.0f} M", f"{data['liq_delta']:,.0f}", delta_color="normal")

st.markdown("---")
col_spread, col_signal = st.columns([1, 2])
with col_spread:
    st.metric("⚡ SPREAD (US-HK)", f"{spread:.2f}%", f"{spread_delta:.2f}%")
with col_signal:
    if spread > SEUIL_SPREAD and data['spot'] < 7.8450:
        st.success(f"### 🟢 SIGNAL : ACHAT FORT (STRONG BUY)")
        st.write(f"Spread attractif (+{spread:.2f}%) et Liquidité stable.")
    elif (data['liq'] < SEUIL_LIQ and data['liq'] > 0) or (spread < 0):
        st.error(f"### 🔴 SIGNAL : VENTE FORTE (STRONG SELL)")
        st.write(f"Alerte liquidité ou inversion des taux.")
    else:
        st.info(f"### ⚪ SIGNAL : NEUTRE")
        st.write(f"En attente d'opportunité.")

# --- SECTION 2 : GRAPHIQUES (3 ONGLETS MAINTENANT) ---

tab1, tab2, tab3 = st.tabs(["📈 Prix & Peg", "⚔️ Guerre des Taux", "💧 Historique Liquidité"])

with tab1:
    fig_spot = go.Figure()
    fig_spot.add_trace(go.Scatter(x=h_spot.index, y=h_spot['Close'], mode='lines', name='USD/HKD', line=dict(color='#00CC96', width=3)))
    fig_spot.add_hline(y=7.85, line_dash="dash", line_color="#FF4B4B", annotation_text="Plafond")
    fig_spot.add_hline(y=7.75, line_dash="dash", line_color="#00C805", annotation_text="Plancher")
    fig_spot.update_layout(height=350, margin=dict(l=10, r=10, t=10, b=10), plot_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig_spot, use_container_width=True)

with tab2:
    fig_rates = go.Figure()
    fig_rates.add_trace(go.Scatter(x=h_us.index, y=h_us['Close'], mode='lines', name='🇺🇸 Taux US', line=dict(color='#3366CC')))
    if not h_hk.empty:
        fig_rates.add_trace(go.Scatter(x=h_hk['date_dt'], y=h_hk['rate'], mode='lines', name='🇭🇰 HIBOR', line=dict(color='#FFAA00')))
    fig_rates.update_layout(height=350, margin=dict(l=10, r=10, t=10, b=10), plot_bgcolor="rgba(0,0,0,0)", hovermode="x unified")
    st.plotly_chart(fig_rates, use_container_width=True)

with tab3:
    st.caption("Évolution de l'Aggregate Balance (Cash interbancaire)")
    fig_liq = go.Figure()
    if not h_liq.empty:
        # Zone remplie pour montrer le volume
        fig_liq.add_trace(go.Scatter(
            x=h_liq['date_dt'], 
            y=h_liq['balance'], 
            mode='lines', 
            fill='tozeroy', # Remplissage sous la courbe
            name='Liquidité (M HKD)', 
            line=dict(color='#00B4D8', width=2)
        ))
        
        # Ligne rouge de danger (SEUIL)
        fig_liq.add_hline(
            y=SEUIL_LIQ, 
            line_dash="dot", 
            line_color="red", 
            annotation_text=f"Seuil Critique ({SEUIL_LIQ:,.0f})", 
            annotation_position="bottom right"
        )
        
    fig_liq.update_layout(
        height=350, 
        margin=dict(l=10, r=10, t=10, b=10), 
        plot_bgcolor="rgba(0,0,0,0)",
        yaxis_title="Millions HKD"
    )
    st.plotly_chart(fig_liq, use_container_width=True)

st.divider()
st.caption("Système Algorithmique USD/HKD v5.0")
