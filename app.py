import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import plotly.graph_objects as go
from datetime import datetime

# ==========================================
# 1. CONFIGURATION DE LA PAGE
# ==========================================
st.set_page_config(
    page_title="USD/HKD Sentinel",
    page_icon="🇭🇰",
    layout="wide"
)

# Style CSS pour le look "Pro"
st.markdown("""
    <style>
    .metric-card {
        background-color: #0e1117;
        border: 1px solid #303030;
        padding: 20px;
        border-radius: 10px;
    }
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 2. SIDEBAR (Paramètres Simples)
# ==========================================
with st.sidebar:
    st.header("⚙️ Paramètres")
    # Valeurs par défaut standards
    SEUIL_SPREAD = st.number_input("Seuil Spread (%)", value=0.50, step=0.05)
    SEUIL_LIQ = st.number_input("Seuil Liquidité (M HKD)", value=10000)
    
    st.divider()
    st.caption("Dernière actualisation :")
    st.caption(datetime.now().strftime('%H:%M:%S'))
    
    if st.button("🔄 Rafraîchir les données"):
        st.rerun()

# ==========================================
# 3. MOTEUR DE DONNÉES (HKMA + YAHOO)
# ==========================================
class HKMA_Data:
    BASE_URL = "https://api.hkma.gov.hk/public/market-data-and-statistics"
    
    @staticmethod
    def get_data():
        headers = {"User-Agent": "Mozilla/5.0"}
        hibor_final = 0.0
        liq_val = 0.0
        
        # A. LIQUIDITÉ (Base Daily)
        try:
            url_liq = f"{HKMA_Data.BASE_URL}/daily-monetary-statistics/daily-figures-interbank-liquidity"
            # On demande la dernière donnée dispo
            params = {"pagesize": "1", "sortby": "end_of_date", "sortorder": "desc"}
            r = requests.get(url_liq, params=params, headers=headers, timeout=5)
            
            if r.status_code == 200:
                data = r.json()
                if data.get('header', {}).get('success'):
                    rec = data['result']['records'][0]
                    # Récupération Liquidité
                    liq_val = float(rec.get('closing_balance', 0))
                    # Récupération HIBOR 1M (Secours)
                    hibor_final = float(rec.get('hibor_fixing_1m', 0))
        except:
            pass

        # B. HIBOR 3M (Précision)
        try:
            url_hibor = f"{HKMA_Data.BASE_URL}/monthly-statistical-bulletin/er-ir/hk-interbank-ir-daily"
            params_h = {
                "pagesize": "1", 
                "segment": "hibor.fixing", 
                "sortby": "end_of_day", 
                "sortorder": "desc"
            }
            r_h = requests.get(url_hibor, params=params_h, headers=headers, timeout=5)
            
            if r_h.status_code == 200:
                data_h = r_h.json()
                if data_h.get('header', {}).get('success'):
                    rec = data_h['result']['records'][0]
                    # On cherche ir_3m ou ir_hibor_3m
                    val = float(rec.get('ir_3m', rec.get('ir_hibor_3m', 0)))
                    if val > 0:
                        hibor_final = val
        except:
            pass
        
        return hibor_final, liq_val

def get_market_data():
    # Yahoo Finance pour le Spot et le Taux US
    ticker_spot = yf.Ticker("USDHKD=X")
    hist_spot = ticker_spot.history(period="1mo")
    
    ticker_us = yf.Ticker("^IRX") # Taux US 3 Mois
    hist_us = ticker_us.history(period="5d")
    
    # Sécurités si Yahoo bug
    if hist_spot.empty or hist_us.empty:
        return None
        
    current_spot = hist_spot['Close'].iloc[-1]
    prev_spot = hist_spot['Close'].iloc[-2]
    us_rate = hist_us['Close'].iloc[-1]
    
    # Appel API Hong Kong
    hk_rate, liquidity = HKMA_Data.get_data()
    
    return {
        "spot": current_spot,
        "spot_prev": prev_spot,
        "hist_spot": hist_spot,
        "us_rate": us_rate,
        "hk_rate": hk_rate,
        "liquidity": liquidity
    }

# ==========================================
# 4. AFFICHAGE PRINCIPAL
# ==========================================

st.title("🇭🇰 USD/HKD Institutionnel")
st.markdown("### Surveillance Stratégique du Peg & Liquidité")

with st.spinner('Connexion aux serveurs bancaires...'):
    data = get_market_data()

if data is None:
    st.error("Erreur de connexion Yahoo Finance. Veuillez rafraîchir.")
else:
    # Calculs
    spread = data['us_rate'] - data['hk_rate']
    
    # --- LIGNE 1 : KPIs ---
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Prix Spot", f"{data['spot']:.4f}", f"{(data['spot']-data['spot_prev']):.4f}")
    col2.metric("Taux US (3M)", f"{data['us_rate']:.2f}%")
    col3.metric("Taux HK (HIBOR)", f"{data['hk_rate']:.2f}%")
    col4.metric("SPREAD", f"{spread:.2f}%", delta_color="normal" if spread > 0 else "inverse")
    col5.metric("Liquidité", f"{data['liquidity']:,.0f}M", delta_color="normal" if data['liquidity'] > SEUIL_LIQ else "inverse")

    st.divider()

    # --- LIGNE 2 : SIGNAUX ---
    col_sig, col_gauge = st.columns([2, 1])

    with col_sig:
        # LOGIQUE DÉCISIONNELLE
        if spread > SEUIL_SPREAD and data['spot'] < 7.8450:
            st.success(f"### 🟢 SIGNAL ACHAT (STRONG BUY)")
            st.write(f"**Analyse :** Le différentiel de taux est très favorable (+{spread:.2f}%) pour le Dollar.")
            st.write("🎯 **Objectif :** 7.8490 (Haut du Peg)")
            
        elif (data['liquidity'] < SEUIL_LIQ and data['liquidity'] > 0) or (spread < 0):
            st.error(f"### 🔴 SIGNAL VENTE (STRONG SELL)")
            reason = "Crise de Liquidité" if data['liquidity'] < SEUIL_LIQ else "Inversion des Taux"
            st.write(f"**Analyse :** {reason} détectée. Pression sur le HKD.")
            st.write("🎯 **Objectif :** 7.7510 (Bas du Peg)")
        
        else:
            st.info("### ⚪ NEUTRE (ATTENTE)")
            st.write("**Analyse :** Marché calme. Pas d'avantage statistique clair pour le moment.")

    with col_gauge:
        st.write("**Position dans le Peg (7.75 - 7.85)**")
        st.slider("", 7.75, 7.85, float(data['spot']), disabled=True)
        if data['spot'] > 7.84: st.warning("⚠️ Intervention Probable (Vente USD)")
        if data['spot'] < 7.76: st.warning("⚠️ Intervention Probable (Achat USD)")

    # --- LIGNE 3 : GRAPHIQUE ---
    st.subheader("Tendance du Marché")
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=data['hist_spot'].index, y=data['hist_spot']['Close'],
        mode='lines', name='USD/HKD', line=dict(color='#00CC96', width=2)
    ))
    # Bornes
    fig.add_hline(y=7.85, line_dash="dash", line_color="red", annotation_text="Max 7.85")
    fig.add_hline(y=7.75, line_dash="dash", line_color="green", annotation_text="Min 7.75")
    
    fig.update_layout(height=400, margin=dict(l=20, r=20, t=30, b=20), paper_bgcolor="rgba(0,0,0,0)")
    st.plotly_chart(fig, use_container_width=True)
