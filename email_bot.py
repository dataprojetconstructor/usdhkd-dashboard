import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests
import yfinance as yf
from datetime import datetime
import os
import time

# --- CONFIGURATION ---
EMAIL_SENDER = os.environ.get("EMAIL_SENDER")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD")
# On nettoie la liste : on sépare par virgule et on enlève les espaces vides
raw_recipients = os.environ.get("EMAIL_RECIPIENTS", "")
RECIPIENTS = [email.strip() for email in raw_recipients.split(",") if email.strip()]

SEUIL_SPREAD = 0.50
SEUIL_LIQ = 10000

# --- MOTEUR DE DONNÉES (Identique au Dashboard) ---
class HKMA_Data:
    BASE_URL = "https://api.hkma.gov.hk/public/market-data-and-statistics"
    @staticmethod
    def get_data():
        headers = {"User-Agent": "Mozilla/5.0"}
        hibor, liq = 0.0, 0.0
        try:
            url_l = f"{HKMA_Data.BASE_URL}/daily-monetary-statistics/daily-figures-interbank-liquidity"
            r = requests.get(url_l, params={"pagesize": "1", "sortby": "end_of_date", "sortorder": "desc"}, headers=headers)
            rec = r.json()['result']['records'][0]
            liq = float(rec.get('closing_balance', 0))
            
            url_h = f"{HKMA_Data.BASE_URL}/monthly-statistical-bulletin/er-ir/hk-interbank-ir-daily"
            r_h = requests.get(url_h, params={"pagesize": "1", "segment": "hibor.fixing", "sortby": "end_of_day", "sortorder": "desc"}, headers=headers)
            rec_h = r_h.json()['result']['records'][0]
            val = float(rec_h.get('ir_3m', rec_h.get('ir_hibor_3m', 0)))
            if val > 0: hibor = val
        except: pass
        return hibor, liq

def get_context():
    try:
        spot = yf.Ticker("USDHKD=X").history(period="1d")['Close'].iloc[-1]
        us = yf.Ticker("^IRX").history(period="1d")['Close'].iloc[-1]
        hk, liq = HKMA_Data.get_data()
        return spot, us, hk, liq
    except: return None, None, None, None

# --- ENVOI DE L'EMAIL ---
def send_report():
    print("🔄 Analyse du marché...")
    spot, us, hk, liq = get_context()
    if spot is None: return

    spread = us - hk
    date_now = datetime.now().strftime("%d/%m/%Y")
    
    # Définition du contenu (couleurs, textes)
    color, status, desc = "#888", "NEUTRE", "Marché calme."
    if spread > SEUIL_SPREAD and spot < 7.845:
        color, status, desc = "#00C805", "ACHAT (BUY)", f"Spread favorable (+{spread:.2f}%)."
    elif (liq < SEUIL_LIQ and liq > 0) or (spread < 0):
        color, status, desc = "#FF4B4B", "VENTE (SELL)", "Alerte Liquidité."

    # Construction du HTML (Corps du message)
    # On le prépare une seule fois
    html_body = f"""
    <html><body>
        <div style="border:1px solid #ddd; border-radius:10px; padding:20px; max-width:600px;">
            <h2 style="text-align:center;">🇭🇰 Rapport USD/HKD ({date_now})</h2>
            <div style="background:{color}; color:white; padding:15px; text-align:center; font-weight:bold; border-radius:5px;">
                {status}
            </div>
            <p style="text-align:center;">{desc}</p>
            <table style="width:100%; margin-top:20px;">
                <tr><td>💵 Prix Spot</td><td style="text-align:right;">{spot:.4f}</td></tr>
                <tr><td>⚡ Spread</td><td style="text-align:right;"><b>{spread:.2f}%</b></td></tr>
                <tr><td>💧 Liquidité</td><td style="text-align:right;">{liq:,.0f} M</td></tr>
                <tr><td>🇺🇸 Taux US</td><td style="text-align:right;">{us:.2f}%</td></tr>
                <tr><td>🇭🇰 Taux HK</td><td style="text-align:right;">{hk:.2f}%</td></tr>
            </table>
        </div>
    </body></html>
    """

    try:
        # Connexion au serveur SMTP
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        
        # BOUCLE D'ENVOI CORRIGÉE
        for email_addr in RECIPIENTS:
            print(f"Envoi à : {email_addr}...")
            
            # CRUCIAL : On recrée l'objet message pour chaque destinataire
            # pour éviter les conflits d'en-têtes
            msg = MIMEMultipart()
            msg['From'] = EMAIL_SENDER
            msg['To'] = email_addr
            msg['Subject'] = f"Signal USD/HKD : {status}"
            msg.attach(MIMEText(html_body, 'html'))
            
            server.sendmail(EMAIL_SENDER, email_addr, msg.as_string())
            print("✅ Envoyé.")
            time.sleep(1) # Petite pause pour ne pas brusquer Gmail
            
        server.quit()
        print("🎉 Tous les emails ont été envoyés.")
        
    except Exception as e:
        print(f"❌ Erreur SMTP : {e}")

if __name__ == "__main__":
    send_report()
