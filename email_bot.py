import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import requests
import yfinance as yf
from datetime import datetime
import os

# ==========================================
# 1. CONFIGURATION (SECRETS)
# ==========================================
# Ces infos seront lues depuis les "Secrets" GitHub pour la sécurité
EMAIL_SENDER = os.environ.get("EMAIL_SENDER")
EMAIL_PASSWORD = os.environ.get("EMAIL_PASSWORD") # Mot de passe d'application (pas le vrai mdp)
# Liste des destinataires (séparés par des virgules dans les secrets ou ici)
RECIPIENTS = os.environ.get("EMAIL_RECIPIENTS").split(",")

SEUIL_SPREAD = 0.50
SEUIL_LIQ = 10000

# ==========================================
# 2. MOTEUR DE DONNÉES (Copie conforme du Dashboard)
# ==========================================
class HKMA_Data:
    BASE_URL = "https://api.hkma.gov.hk/public/market-data-and-statistics"
    @staticmethod
    def get_data():
        headers = {"User-Agent": "Mozilla/5.0"}
        hibor, liq = 0.0, 0.0
        try:
            # Liquidité
            url_liq = f"{HKMA_Data.BASE_URL}/daily-monetary-statistics/daily-figures-interbank-liquidity"
            r = requests.get(url_liq, params={"pagesize": "1", "sortby": "end_of_date", "sortorder": "desc"}, headers=headers, timeout=10)
            if r.status_code == 200:
                rec = r.json()['result']['records'][0]
                liq = float(rec.get('closing_balance', 0))
                hibor = float(rec.get('hibor_fixing_1m', 0))
        except: pass
        
        try:
            # HIBOR 3M
            url_h = f"{HKMA_Data.BASE_URL}/monthly-statistical-bulletin/er-ir/hk-interbank-ir-daily"
            r_h = requests.get(url_h, params={"pagesize": "1", "segment": "hibor.fixing", "sortby": "end_of_day", "sortorder": "desc"}, headers=headers, timeout=10)
            if r_h.status_code == 200:
                val = float(r_h.json()['result']['records'][0].get('ir_3m', 0))
                if val > 0: hibor = val
        except: pass
        return hibor, liq

def get_market_context():
    try:
        spot = yf.Ticker("USDHKD=X").history(period="1d")['Close'].iloc[-1]
        us_rate = yf.Ticker("^IRX").history(period="1d")['Close'].iloc[-1]
    except:
        return None, None, None, None
    
    hk_rate, liq = HKMA_Data.get_data()
    return spot, us_rate, hk_rate, liq

# ==========================================
# 3. CONSTRUCTION DU RAPPORT
# ==========================================
def send_daily_report():
    print("🔄 Récupération des données en cours...")
    spot, us, hk, liq = get_market_context()
    
    if spot is None:
        print("❌ Erreur de données Yahoo.")
        return

    spread = us - hk
    date_now = datetime.now().strftime("%d/%m/%Y")
    
    # Détermination du Signal
    signal_color = "#888888" # Gris
    signal_text = "NEUTRE"
    signal_desc = "Marché calme. Pas d'action requise."
    
    if spread > SEUIL_SPREAD and spot < 7.845:
        signal_color = "#00C805" # Vert
        signal_text = "ACHAT FORT (STRONG BUY)"
        signal_desc = f"Le Spread est très favorable (+{spread:.2f}%). Opportunité de Carry Trade."
    elif (liq < SEUIL_LIQ and liq > 0) or (spread < 0):
        signal_color = "#FF4B4B" # Rouge
        signal_text = "VENTE FORTE (STRONG SELL)"
        signal_desc = "Alerte Liquidité ou Inversion des taux. Risque baissier."

    # Création du corps de l'email en HTML
    html_content = f"""
    <html>
    <body style="font-family: Arial, sans-serif; color: #333;">
        <div style="max-width: 600px; margin: auto; border: 1px solid #ddd; border-radius: 10px; overflow: hidden;">
            <div style="background-color: #0e1117; color: white; padding: 20px; text-align: center;">
                <h2 style="margin:0;">🇭🇰 Rapport Quotidien USD/HKD</h2>
                <p style="margin:5px 0 0 0; font-size: 0.9em;">Date : {date_now}</p>
            </div>
            
            <div style="padding: 20px;">
                <div style="background-color: {signal_color}; color: white; padding: 15px; text-align: center; border-radius: 5px; font-weight: bold; font-size: 1.2em;">
                    SIGNAL : {signal_text}
                </div>
                <p style="text-align: center; font-style: italic;">{signal_desc}</p>
                
                <table style="width: 100%; border-collapse: collapse; margin-top: 20px;">
                    <tr style="background-color: #f9f9f9;">
                        <td style="padding: 10px; border-bottom: 1px solid #ddd;">💵 <b>Prix Spot</b></td>
                        <td style="padding: 10px; border-bottom: 1px solid #ddd; text-align: right;">{spot:.4f}</td>
                    </tr>
                    <tr>
                        <td style="padding: 10px; border-bottom: 1px solid #ddd;">⚡ <b>Spread (US-HK)</b></td>
                        <td style="padding: 10px; border-bottom: 1px solid #ddd; text-align: right;"><b>{spread:.2f}%</b></td>
                    </tr>
                    <tr style="background-color: #f9f9f9;">
                        <td style="padding: 10px; border-bottom: 1px solid #ddd;">💧 <b>Liquidité</b></td>
                        <td style="padding: 10px; border-bottom: 1px solid #ddd; text-align: right;">{liq:,.0f} M HKD</td>
                    </tr>
                    <tr>
                        <td style="padding: 10px; border-bottom: 1px solid #ddd;">🇺🇸 <b>Taux US (3M)</b></td>
                        <td style="padding: 10px; border-bottom: 1px solid #ddd; text-align: right;">{us:.2f}%</td>
                    </tr>
                    <tr style="background-color: #f9f9f9;">
                        <td style="padding: 10px; border-bottom: 1px solid #ddd;">🇭🇰 <b>Taux HK (HIBOR)</b></td>
                        <td style="padding: 10px; border-bottom: 1px solid #ddd; text-align: right;">{hk:.2f}%</td>
                    </tr>
                </table>
                
                <p style="font-size: 0.8em; color: #777; margin-top: 20px; text-align: center;">
                    Données certifiées HKMA & NYSE.<br>
                    Ceci est un rapport automatique généré par USD/HKD Sentinel.
                </p>
            </div>
        </div>
    </body>
    </html>
    """

    # Envoi de l'email
    msg = MIMEMultipart()
    msg['From'] = EMAIL_SENDER
    msg['Subject'] = f"Rapport USD/HKD : {signal_text} ({date_now})"
    msg.attach(MIMEText(html_content, 'html'))

    try:
        # Connexion SMTP (Exemple pour Gmail)
        server = smtplib.SMTP('smtp.gmail.com', 587)
        server.starttls()
        server.login(EMAIL_SENDER, EMAIL_PASSWORD)
        
        # Envoi à tous les destinataires
        for recipient in RECIPIENTS:
            msg['To'] = recipient.strip()
            server.sendmail(EMAIL_SENDER, recipient.strip(), msg.as_string())
            print(f"✅ Email envoyé à {recipient}")
            
        server.quit()
    except Exception as e:
        print(f"❌ Erreur d'envoi d'email : {e}")

if __name__ == "__main__":
    send_daily_report()
