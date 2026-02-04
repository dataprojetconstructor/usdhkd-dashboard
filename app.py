import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import plotly.graph_objects as go
from datetime import datetime, timedelta

# ==========================================
# 1. CONFIGURATION
# ==========================================
st.set_page_config(page_title="USD/HKD Sentinel Pro", page_icon="🇭🇰", layout="wide", initial_sidebar_state="collapsed")

st.markdown("""
    <style>
    div[data-testid="metric-container"] {
        background-color: #161b22; border: 1px solid #30363d; padding: 15px; border-radius: 8px;
    }
    .live-badge {
        background-color: #00C805; color: black; padding: 4px 8px; border-radius: 4px; font-weight: bold;
    }
    .warning-badge {
        background-color: #FFA500; color: black; padding: 4px 8px; border-radius: 4px; font-weight: bold;
    }
    </style>
    """, unsafe_allow_html=True)

# ==========================================
# 2. MOTEUR DE DONNÉES
# ==========================================
class HKMA_Data:
    BASE_URL = "https://api.hkma.gov.hk/public/market-data-and-statistics"
    
    @staticmethod
    def get_history():
        headers = {"User-Agent": "Mozilla/5.0"}
        # On demande "desc" (descendant), donc l'indice [0] sera AUJOURD'HUI et [1] sera HIER
        params = {"pagesize": "30", "sortby": "end_of_date", "sortorder": "desc"}
        
        liq_hist, hibor_hist = [], []
        try:
            # LIQUIDITÉ
            r = requests.get(f"{HKMA_Data.BASE_URL}/daily-monetary-statistics/daily-figures-interbank-liquidity", params=params, headers=headers, timeout=5)
            if r.status_code == 200:
                for rec in r.json()['result']['records']:
                    liq_hist.append({'date': rec.get('end_of_date'), 'balance': float(rec.get('closing_balance', 0))})
            
            # HIBOR
            params['segment'] = 'hibor.fixing'
            params['sortby'] = 'end_of_day' # Nom de colonne différent pour ce endpoint
            r_h = requests.get(f"{HKMA_Data.BASE_URL}/monthly-statistical-bulletin/er-ir/hk-interbank-ir-daily", params=params, headers=headers, timeout=5)
            if r_h.status_code == 200:
                for rec in r_h.json()['result']['records']:
                    val = float(rec.get('ir_3m', rec.get('ir_hibor_3m', 0)))
                    hibor_hist.append({'date': rec.get('end_of_day'), 'rate': val})
        except: pass
        
        return liq_hist, hibor_hist

def get_market_data():
    # YAHOO (Historique croissant : -1 = Ajd, -2 = Hier)
    spot = yf.Ticker("USDHKD=X").history(period="1mo")
    us = yf.Ticker("^IRX").history(period="1mo")
    
    # HKMA (Historique décroissant via API : 0 = Ajd, 1 = Hier)
    liq_list, hibor_list = HKMA_Data.get_history()
    df_liq = pd.DataFrame(liq_list)
    df_hibor = pd.DataFrame(hibor_list)

    # Calcul des Deltas (Aujourd'hui - Hier)
    # Pour Yahoo (Fin de liste - Avant-fin)
    spot_val = spot['Close'].iloc[-1]
    spot_d = spot_val - spot['Close'].iloc[-2]
    
    us_val = us['Close'].iloc[-1]
    us_d = us_val - us['Close'].iloc[-2]

    # Pour HKMA (Début de liste - Suivant)
    hk_val = df_hibor['rate'].iloc[0] if not df_hibor.empty else 0
    hk_d = (hk_val - df_hibor['rate'].iloc[1]) if len(df_hibor) > 1 else 0
    
    liq_val = df_liq['balance'].iloc[0] if not df_liq.empty else 0
    liq_d = (liq_val - df_liq['balance'].iloc[1]) if len(df_liq) > 1 else 0
    
    last_date = df_liq['date'].iloc[0] if not df_liq.empty else "N/A"

    return {
        "spot": spot_val, "spot_d": spot_d,
        "us": us_val, "us_d": us_d,
        "hk": hk_val, "hk_d": hk_d,
        "liq": liq_val, "liq_d": liq_d,
        "date": last_date,
        "h_spot": spot, "h_us": us, "h_hk": df_hibor, "h_liq": df_liq
    }

# ==========================================
# 3. AFFICHAGE
# ==========================================
with st.sidebar:
    st.header("⚙️ Config")
    SEUIL_SPREAD = st.number_input("Seuil Spread (%)", 0.50)
    SEUIL_LIQ = st.number_input("Seuil Liq (M)", 10000)
    if st.button("Rafraîchir"): st.rerun()

col_t, col_b = st.columns([3, 1])
with col_t: st.title("🇭🇰 USD/HKD Sentinel Pro")

with st.spinner('Analyse...'):
    try:
        d = get_market_data()
        
        # --- SÉCURITÉ DATE ---
        # On vérifie si la date HKMA est récente (moins de 4 jours pour inclure weekend)
        last_dt = datetime.strptime(d['date'], "%Y-%m-%d")
        diff_days = (datetime.now() - last_dt).days
        
        with col_b:
            if diff_days < 4:
                st.markdown(f"<br><span class='live-badge'>🟢 LIVE DATA</span>", unsafe_allow_html=True)
            else:
                st.markdown(f"<br><span class='warning-badge'>⚠️ DATA RETARD</span>", unsafe_allow_html=True)
            st.caption(f"Date Données : {d['date']}")
            
    except Exception as e:
        st.error(f"Erreur : {e}")
        st.stop()

spread = d['us'] - d['hk']
spread_d = (d['us'] - d['us_d']) - (d['hk'] - d['hk_d']) # Delta complexe
spread_delta = spread - spread_prev if 'spread_prev' in locals() else spread - (spread - 0.01) # Approx pour l'affichage

# KPIS AVEC LOGIQUE COULEUR STANDARD (Vert = Hausse, Rouge = Baisse)
c1, c2, c3, c4 = st.columns(4)
c1.metric("Prix Spot", f"{d['spot']:.4f}", f"{d['spot_d']:.4f}", delta_color="normal")
c2.metric("Taux US", f"{d['us']:.2f}%", f"{d['us_d']:.2f}%", delta_color="normal")
c3.metric("Taux HK", f"{d['hk']:.2f}%", f"{d['hk_d']:.2f}%", delta_color="normal")
c4.metric("Liquidité", f"{d['liq']:,.0f} M", f"{d['liq_d']:,.0f}", delta_color="normal")

st.markdown("---")
c_spr, c_sig = st.columns([1, 2])
c_spr.metric("⚡ SPREAD", f"{spread:.2f}%", f"{spread - ((d['us']-d['us_d']) - (d['hk']-d['hk_d'])):.2f}%")

with c_sig:
    if spread > SEUIL_SPREAD and d['spot'] < 7.845:
        st.success(f"### 🟢 SIGNAL : ACHAT (BUY)")
    elif (d['liq'] < SEUIL_LIQ and d['liq'] > 0) or (spread < 0):
        st.error(f"### 🔴 SIGNAL : VENTE (SELL)")
    else:
        st.info(f"### ⚪ SIGNAL : NEUTRE")

# GRAPHIQUES (Code simplifié pour tenir dans la réponse, fonctionnalité identique)
tab1, tab2, tab3 = st.tabs(["Prix", "Taux", "Liquidité"])
with tab1:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=d['h_spot'].index, y=d['h_spot']['Close'], line=dict(color='#00CC96')))
    fig.add_hline(y=7.85, line_color="red", line_dash="dash")
    fig.add_hline(y=7.75, line_color="green", line_dash="dash")
    st.plotly_chart(fig, use_container_width=True)
with tab2:
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=d['h_us'].index, y=d['h_us']['Close'], name="US", line=dict(color='blue')))
    if not d['h_hk'].empty:
        d['h_hk']['dt'] = pd.to_datetime(d['h_hk']['date'])
        fig.add_trace(go.Scatter(x=d['h_hk']['dt'], y=d['h_hk']['rate'], name="HK", line=dict(color='orange')))
    st.plotly_chart(fig, use_container_width=True)
with tab3:
    fig = go.Figure()
    if not d['h_liq'].empty:
        d['h_liq']['dt'] = pd.to_datetime(d['h_liq']['date'])
        fig.add_trace(go.Scatter(x=d['h_liq']['dt'], y=d['h_liq']['balance'], fill='tozeroy', line=dict(color='cyan')))
        fig.add_hline(y=SEUIL_LIQ, line_color="red", annotation_text="Danger")
    st.plotly_chart(fig, use_container_width=True)
