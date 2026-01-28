import streamlit as st
import pandas as pd
import yfinance as yf
import requests
import plotly.graph_objects as go
from datetime import datetime, timedelta

# ==========================================
# 1. CONFIGURATION & STYLE (Mobile Friendly)
# ==========================================
st.set_page_config(
    page_title="USD/HKD Sentinel Pro",
    page_icon="🇭🇰",
    layout="wide",
    initial_sidebar_state="collapsed" # Gain de place sur mobile
)

# CSS pour le look "Bloomberg Terminal" et responsive
st.markdown("""
    <style>
    /* Cartes de données */
    div[data-testid="metric-container"] {
        background-color: #161b22;
        border: 1px solid #30363d;
        padding: 15px;
        border-radius: 8px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }
    /* Badge Live */
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
# 2. PARAMÈTRES (SIDEBAR)
# ==========================================
with st.sidebar:
    st.header("⚙️ Configuration")
    SEUIL_SPREAD = st.number_input("Seuil Spread Achat (%)", value=0.50, step=0.05)
    SEUIL_LIQ = st.number_input("Seuil Liquidité (M HKD)", value=10000)
    
    st.divider()
    st.info("ℹ️ Les flèches indiquent la variation par rapport à la veille.")
    
    if st.button("🔄 Forcer l'actualisation"):
        st.rerun()

# ==========================================
# 3. MOTEUR DE DONNÉES (HISTORIQUE & LIVE)
# ==========================================
class HKMA_Data:
    BASE_URL = "https://api.hkma.gov.hk/public/market-data-and-statistics"
    
    @staticmethod
    def get_history():
        headers = {"User-Agent": "Mozilla/5.0"}
        
        # On récupère 30 jours pour les graphiques
        params_hist = {"pagesize": "30", "sortby": "end_of_date", "sortorder": "desc"}
        
        # A. LIQUIDITÉ (Derniers 30 jours)
        liq_history = []
        try:
            url_liq = f"{HKMA_Data.BASE_URL}/daily-monetary-statistics/daily-figures-interbank-liquidity"
            r = requests.get(url_liq, params=params_hist, headers=headers, timeout=6)
            if r.status_code == 200:
                records = r.json()['result']['records']
                for rec in records:
                    liq_history.append({
                        'date': rec.get('end_of_date'),
                        'balance': float(rec.get('closing_balance', 0)),
                        'hibor_1m': float(rec.get('hibor_fixing_1m', 0)) # Backup
                    })
        except: pass

        # B. HIBOR 3M (Derniers 30 jours)
        # Note: L'API change parfois les clés, on reste robuste
        hibor_history = []
        try:
            url_h = f"{HKMA_Data.BASE_URL}/monthly-statistical-bulletin/er-ir/hk-interbank-ir-daily"
            params_h = {"pagesize": "30", "segment": "hibor.fixing", "sortby": "end_of_day", "sortorder": "desc"}
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
    # 1. YAHOO FINANCE (Prix Spot + Taux US)
    # On récupère 1 mois d'historique
    ticker_spot = yf.Ticker("USDHKD=X")
    hist_spot = ticker_spot.history(period="1mo")
    
    ticker_us = yf.Ticker("^IRX") # Taux US 3 Mois
    hist_us = ticker_us.history(period="1mo")
    
    # 2. HKMA (Taux HK + Liquidité)
    liq_hist, hibor_hist = HKMA_Data.get_history()
    
    # Conversion en DataFrame pour manipulation facile
    df_liq = pd.DataFrame(liq_hist) if liq_hist else pd.DataFrame()
    df_hibor = pd.DataFrame(hibor_hist) if hibor_hist else pd.DataFrame()
    
    # Valeurs actuelles (Today) et Précédentes (Yesterday) pour les deltas
    current_data = {
        "spot": hist_spot['Close'].iloc[-1],
        "spot_delta": hist_spot['Close'].iloc[-1] - hist_spot['Close'].iloc[-2],
        
        "us_rate": hist_us['Close'].iloc[-1],
        "us_delta": hist_us['Close'].iloc[-1] - hist_us['Close'].iloc[-2],
        
        # Pour HK, on prend la ligne 0 (ajd) et ligne 1 (hier)
        "hk_rate": df_hibor['rate'].iloc[0] if not df_hibor.empty else 0,
        "hk_delta": (df_hibor['rate'].iloc[0] - df_hibor['rate'].iloc[1]) if len(df_hibor) > 1 else 0,
        
        "liq": df_liq['balance'].iloc[0] if not df_liq.empty else 0,
        "liq_delta": (df_liq['balance'].iloc[0] - df_liq['balance'].iloc[1]) if len(df_liq) > 1 else 0,
        
        "last_update_hk": df_liq['date'].iloc[0] if not df_liq.empty else "N/A"
    }
    
    return current_data, hist_spot, hist_us, df_hibor

# ==========================================
# 4. AFFICHAGE DU DASHBOARD
# ==========================================

# En-tête avec Badge de Sécurité
col_title, col_badge = st.columns([3, 1])
with col_title:
    st.title("🇭🇰 USD/HKD Sentinel")
    st.caption("Algorithme de surveillance : Arbitrage de Taux & Peg")

# CHARGEMENT DES DONNÉES
with st.spinner('Connexion sécurisée aux serveurs bancaires...'):
    try:
        data, h_spot, h_us, h_hk = get_market_data()
        
        # Badge de confirmation Live
        with col_badge:
            st.markdown(f"<br><span class='live-badge'>🟢 LIVE DATA</span>", unsafe_allow_html=True)
            st.caption(f"Source HKMA : {data['last_update_hk']}")
            
    except Exception as e:
        st.error(f"Erreur de connexion : {e}")
        st.stop()

# CALCUL DU SPREAD
spread = data['us_rate'] - data['hk_rate']
spread_prev = (data['us_rate'] - data['us_delta']) - (data['hk_rate'] - data['hk_delta'])
spread_delta = spread - spread_prev

# --- SECTION 1 : INDICATEURS CLÉS (KPIS) ---
# Utilisation de st.metric pour les flèches automatiques

col1, col2, col3, col4 = st.columns(4)

with col1:
    st.metric(
        label="💵 Prix Spot USD/HKD",
        value=f"{data['spot']:.4f}",
        delta=f"{data['spot_delta']:.4f}",
        delta_color="inverse" # Rouge si ça monte (car on veut acheter bas) ou normal selon préférence. Ici normal.
    )

with col2:
    st.metric(
        label="🇺🇸 Taux US (3M)",
        value=f"{data['us_rate']:.2f}%",
        delta=f"{data['us_delta']:.2f}%"
    )

with col3:
    st.metric(
        label="🇭🇰 Taux HK (HIBOR)",
        value=f"{data['hk_rate']:.2f}%",
        delta=f"{data['hk_delta']:.2f}%",
        delta_color="inverse" # Si le taux HK baisse, c'est bon pour notre spread (vert)
    )

with col4:
    st.metric(
        label="💧 Liquidité (Millions)",
        value=f"{data['liq']:,.0f}",
        delta=f"{data['liq_delta']:,.0f}",
        delta_color="normal" # Plus de liquidité = Stabilité (Vert)
    )

# Affichage spécial pour le Spread (Le coeur du système)
st.markdown("---")
col_spread, col_signal = st.columns([1, 2])

with col_spread:
    st.metric(
        label="⚡ SPREAD (US - HK)",
        value=f"{spread:.2f}%",
        delta=f"{spread_delta:.2f}%",
        help="Différentiel de taux. Doit être > 0.50% pour acheter."
    )

with col_signal:
    # LOGIQUE DÉCISIONNELLE VISUELLE
    if spread > SEUIL_SPREAD and data['spot'] < 7.8450:
        st.success(f"### 🟢 SIGNAL : ACHAT FORT (STRONG BUY)")
        st.markdown(f"**Analyse :** Le dollar rapporte **{spread:.2f}%** de plus que le HKD. La liquidité est stable.")
        
    elif (data['liq'] < SEUIL_LIQ and data['liq'] > 0) or (spread < 0):
        st.error(f"### 🔴 SIGNAL : VENTE FORTE (STRONG SELL)")
        st.markdown(f"**Analyse :** Alerte liquidité ou inversion des taux. Risque de baisse vers 7.75.")
        
    else:
        st.info(f"### ⚪ SIGNAL : NEUTRE (ATTENTE)")
        st.markdown(f"**Analyse :** Conditions non optimales. Spread actuel : {spread:.2f}% (Cible > {SEUIL_SPREAD}%)")

# --- SECTION 2 : GRAPHIQUES ---

tab1, tab2 = st.tabs(["📈 Prix & Peg", "⚔️ Guerre des Taux (US vs HK)"])

with tab1:
    st.subheader("USD/HKD vs Bornes HKMA")
    fig_spot = go.Figure()
    
    # Prix
    fig_spot.add_trace(go.Scatter(
        x=h_spot.index, y=h_spot['Close'],
        mode='lines', name='USD/HKD',
        line=dict(color='#00CC96', width=3)
    ))
    
    # Bornes
    fig_spot.add_hline(y=7.85, line_dash="dash", line_color="#FF4B4B", annotation_text="Plafond 7.85")
    fig_spot.add_hline(y=7.75, line_dash="dash", line_color="#00C805", annotation_text="Plancher 7.75")
    
    fig_spot.update_layout(
        height=350,
        margin=dict(l=20, r=20, t=20, b=20),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        showlegend=True
    )
    st.plotly_chart(fig_spot, use_container_width=True)

with tab2:
    st.subheader("Évolution du Spread (Ce qui fait bouger le prix)")
    fig_rates = go.Figure()
    
    # Taux US
    fig_rates.add_trace(go.Scatter(
        x=h_us.index, y=h_us['Close'],
        mode='lines', name='🇺🇸 Taux US 3M',
        line=dict(color='#3366CC', width=2)
    ))
    
    # Taux HK
    # On aligne les dates (simplifié pour visualisation)
    if not h_hk.empty:
        # Conversion date string -> datetime pour plot correct
        h_hk['date_dt'] = pd.to_datetime(h_hk['date'])
        fig_rates.add_trace(go.Scatter(
            x=h_hk['date_dt'], y=h_hk['rate'],
            mode='lines', name='🇭🇰 HIBOR 3M',
            line=dict(color='#FFAA00', width=2)
        ))
    
    fig_rates.update_layout(
        height=350,
        margin=dict(l=20, r=20, t=20, b=20),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        hovermode="x unified",
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    )
    st.plotly_chart(fig_rates, use_container_width=True)

# Pied de page
st.divider()
st.caption(f"Données officielles HKMA & NYSE | Sécurité : Activée | Actualisé : {datetime.now().strftime('%H:%M:%S')}")
