#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bybit P2P Price Alert Notifier
Monitors Bybit P2P offers and sends an email notification when a seller
offers the desired price and matches your target purchase budget range.
"""

import sys
import json
import time
import smtplib
import argparse
from datetime import datetime
import urllib.request
import urllib.error
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path

# Fix Windows and Cloud console UTF-8 and unbuffered output
try:
    if sys.stdout.encoding != 'utf-8':
        sys.stdout.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
    else:
        sys.stdout.reconfigure(line_buffering=True)
    if sys.stderr.encoding != 'utf-8':
        sys.stderr.reconfigure(encoding='utf-8', errors='replace', line_buffering=True)
    else:
        sys.stderr.reconfigure(line_buffering=True)
except Exception:
    pass

import os

CONFIG_FILE = Path(__file__).resolve().parent / "config.json"
BYBIT_P2P_URL = "https://api2.bybit.com/fiat/otc/item/online"


def load_config():
    """Load configuration from config.json with optional environment variable overrides."""
    cfg = {}
    if CONFIG_FILE.exists():
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                cfg = json.load(f)
        except Exception as e:
            print(f"[ATTENTION] Impossible de lire '{CONFIG_FILE}': {e}")
    else:
        print(f"[INFO] '{CONFIG_FILE}' introuvable, utilisation des variables d'environnement.")

    # Override with environment variables if present
    if os.environ.get("TARGET_MIN_PRICE"):
        cfg["target_min_price"] = float(os.environ["TARGET_MIN_PRICE"])
    if os.environ.get("TARGET_MAX_PRICE"):
        cfg["target_max_price"] = float(os.environ["TARGET_MAX_PRICE"])
    if os.environ.get("MIN_AMOUNT_DZD"):
        cfg["min_amount_dzd"] = float(os.environ["MIN_AMOUNT_DZD"])
    if os.environ.get("MAX_AMOUNT_DZD"):
        cfg["max_amount_dzd"] = float(os.environ["MAX_AMOUNT_DZD"])
    if os.environ.get("CHECK_INTERVAL_SECONDS"):
        cfg["check_interval_seconds"] = int(os.environ["CHECK_INTERVAL_SECONDS"])
    if os.environ.get("NOTIFICATION_COOLDOWN_MINUTES"):
        cfg["notification_cooldown_minutes"] = int(os.environ["NOTIFICATION_COOLDOWN_MINUTES"])

    email_cfg = cfg.setdefault("email", {})
    if os.environ.get("SENDER_EMAIL"):
        email_cfg["sender_email"] = os.environ["SENDER_EMAIL"]
    if os.environ.get("SENDER_PASSWORD"):
        email_cfg["sender_password"] = os.environ["SENDER_PASSWORD"]
    if os.environ.get("RECEIVER_EMAIL"):
        email_cfg["receiver_email"] = os.environ["RECEIVER_EMAIL"]

    return cfg


def get_budget_range(config):
    """
    Extract (min_budget_dzd, max_budget_dzd) from config.
    Supports min_amount_dzd / max_amount_dzd, target_amount_dzd, or buy_amount_usd.
    """
    if "min_amount_dzd" in config and "max_amount_dzd" in config:
        min_b = float(config["min_amount_dzd"])
        max_b = float(config["max_amount_dzd"])
    elif "min_amount_dzd" in config:
        min_b = float(config["min_amount_dzd"])
        max_b = min_b
    elif "max_amount_dzd" in config:
        max_b = float(config["max_amount_dzd"])
        min_b = max_b
    elif "target_amount_dzd" in config:
        min_b = max_b = float(config["target_amount_dzd"])
    elif "buy_amount_usd" in config:
        ref_price = float(config.get("target_max_price", 250.0))
        val = float(config["buy_amount_usd"]) * ref_price
        min_b = max_b = val
    else:
        min_b = 10000.0
        max_b = 13000.0

    if min_b > max_b:
        min_b, max_b = max_b, min_b
    return min_b, max_b


def get_p2p_items(token_id="USDT", currency_id="DZD", page=1, size=50):
    """
    Fetch P2P ads from Bybit.
    side = '1' corresponds to Sell ads (sellers offering crypto for fiat).
    We fetch without restrictive amount filter to ensure sellers whose min/max limits
    overlap with the user's budget range are captured.
    """
    payload = {
        "tokenId": token_id,
        "currencyId": currency_id,
        "side": "1",
        "page": str(page),
        "size": str(size),
        "authMaker": False,
        "canTrade": False
    }

    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://www.bybit.com",
        "Referer": "https://www.bybit.com/fiat/otc/"
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(BYBIT_P2P_URL, data=data, headers=headers, method="POST")

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            body = resp.read().decode("utf-8")
            result = json.loads(body)
            if result.get("ret_code") != 0:
                print(f"[ATTENTION] Réponse Bybit code={result.get('ret_code')}: {result.get('ret_msg')}")
                return []
            return result.get("result", {}).get("items", []) or []
    except urllib.error.URLError as e:
        print(f"[ERREUR RÉSEAU] Impossible de joindre Bybit: {e}")
        return []
    except Exception as e:
        print(f"[ERREUR] Erreur inattendue lors de la requête Bybit: {e}")
        return []


def send_email(subject, html_body, text_body, config):
    """Send an email using SMTP credentials configured in config.json."""
    email_cfg = config.get("email", {})
    if not email_cfg.get("enabled", True):
        print("[INFO] Envoi d'email désactivé dans la configuration.")
        return False

    sender = email_cfg.get("sender_email")
    password = email_cfg.get("sender_password")
    receiver = email_cfg.get("receiver_email")
    smtp_server = email_cfg.get("smtp_server", "smtp.gmail.com")
    smtp_port = email_cfg.get("smtp_port", 587)
    use_tls = email_cfg.get("use_tls", True)

    if not sender or not password or not receiver or "votre_email" in sender:
        print("[ATTENTION] Veuillez renseigner 'sender_email', 'sender_password' et 'receiver_email' dans config.json !")
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = f"Alerte Bybit P2P <{sender}>"
    msg["To"] = receiver

    part1 = MIMEText(text_body, "plain", "utf-8")
    part2 = MIMEText(html_body, "html", "utf-8")
    msg.attach(part1)
    msg.attach(part2)

    try:
        if smtp_port == 465:
            with smtplib.SMTP_SSL(smtp_server, smtp_port, timeout=15) as server:
                server.login(sender, password)
                server.sendmail(sender, [receiver], msg.as_string())
        else:
            with smtplib.SMTP(smtp_server, smtp_port, timeout=15) as server:
                if use_tls:
                    server.starttls()
                server.login(sender, password)
                server.sendmail(sender, [receiver], msg.as_string())
        print(f"[SUCCÈS] Email envoyé à {receiver} !")
        return True
    except Exception as e:
        print(f"[ERREUR EMAIL] Échec de l'envoi de l'email: {e}")
        return False


def build_alert_message(matched_items, min_price, max_price, min_budget, max_budget, token_id, currency_id):
    """Build formatted plain text and HTML emails for matching offers."""
    first_item = matched_items[0]
    first_price = float(first_item.get("price", 0))

    if min_budget == max_budget:
        budget_str = f"{min_budget:.0f} {currency_id}"
    else:
        budget_str = f"{min_budget:.0f} à {max_budget:.0f} {currency_id}"

    price_range_str = f"{min_price:.2f} à {max_price:.2f} {currency_id}" if min_price else f"<= {max_price:.2f} {currency_id}"
    subject = f"🔥 Alerte Bybit P2P : {first_price:.2f} {currency_id} pour 1 {token_id} (Budget {budget_str})"

    rows_html = ""
    rows_text = ""

    for item in matched_items:
        nick = item.get("nickName", "Inconnu")
        price = float(item.get("price", 0))
        min_amt = item.get("minAmount", "0")
        max_amt = item.get("maxAmount", "0")
        qty = item.get("quantity", "0")
        orders = item.get("recentOrderNum", 0)
        rate = item.get("recentExecuteRate", 0)

        if min_budget == max_budget:
            crypto_detail = f"~{min_budget / price:.2f} {token_id}"
        else:
            crypto_detail = f"~{min_budget / price:.2f} à ~{max_budget / price:.2f} {token_id}"

        rows_text += (
            f"\n- Vendeur: {nick}\n"
            f"  Prix: {price:.2f} {currency_id} / {token_id}\n"
            f"  Pour votre budget ({budget_str}): {crypto_detail}\n"
            f"  Limites vendeur: {min_amt} - {max_amt} {currency_id}\n"
            f"  Disponible vendeur: {qty} {token_id}\n"
            f"  Ordres récents: {orders} (Taux: {rate}%)\n"
        )

        rows_html += f"""
        <tr style="border-bottom: 1px solid #e0e0e0;">
            <td style="padding: 12px; font-weight: bold; color: #1e293b;">{nick}</td>
            <td style="padding: 12px; color: #16a34a; font-weight: bold; font-size: 16px;">{price:.2f} {currency_id}</td>
            <td style="padding: 12px; font-weight: bold; color: #0284c7;">{crypto_detail}</td>
            <td style="padding: 12px; color: #64748b;">{min_amt} à {max_amt} {currency_id}</td>
            <td style="padding: 12px; color: #64748b;">{orders} ({rate}%)</td>
        </tr>
        """

    text_body = f"""Bonjour,

Une ou plusieurs offres correspondent à vos critères sur Bybit P2P !

Critères configurés :
- Prix recherché : {price_range_str}
- Fourchette de budget : {budget_str} (limites vendeur compatibles)

Offres trouvées :{rows_text}

Lien direct vers Bybit P2P :
https://www.bybit.com/fiat/otc/

Bon achat !
"""

    html_body = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; padding: 20px; margin: 0;">
    <div style="max-width: 680px; margin: 0 auto; background-color: #ffffff; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.06); overflow: hidden; border: 1px solid #e2e8f0;">
        <div style="background: linear-gradient(135deg, #f59e0b, #d97706); padding: 24px; color: #ffffff; text-align: center;">
            <h1 style="margin: 0; font-size: 24px;">🚀 Alerte Bybit P2P Déclenchée</h1>
            <p style="margin: 8px 0 0 0; opacity: 0.95; font-size: 15px;">
                Prix cible atteint : <strong>{price_range_str}</strong> | Budget : <strong>{budget_str}</strong>
            </p>
        </div>
        <div style="padding: 24px;">
            <p style="color: #334155; font-size: 15px; margin-top: 0;">
                De nouvelles offres correspondent à vos critères (prix + limites compatibles avec votre budget de {budget_str}) :
            </p>
            <table style="width: 100%; border-collapse: collapse; margin: 20px 0; font-size: 14px; text-align: left;">
                <thead>
                    <tr style="background-color: #f1f5f9; color: #475569;">
                        <th style="padding: 10px 12px;">Vendeur</th>
                        <th style="padding: 10px 12px;">Prix / {token_id}</th>
                        <th style="padding: 10px 12px;">Reçu pour votre budget</th>
                        <th style="padding: 10px 12px;">Limites vendeur</th>
                        <th style="padding: 10px 12px;">Taux</th>
                    </tr>
                </thead>
                <tbody>
                    {rows_html}
                </tbody>
            </table>
            <div style="text-align: center; margin: 30px 0 10px 0;">
                <a href="https://www.bybit.com/fiat/otc/" target="_blank"
                   style="background-color: #0284c7; color: #ffffff; text-decoration: none; padding: 12px 28px; border-radius: 8px; font-weight: bold; display: inline-block;">
                   Ouvrir Bybit P2P
                </a>
            </div>
        </div>
        <div style="background-color: #f8fafc; padding: 14px; text-align: center; font-size: 12px; color: #94a3b8; border-top: 1px solid #e2e8f0;">
            Alerte automatique générée à {datetime.now().strftime('%H:%M:%S')}
        </div>
    </div>
</body>
</html>
"""
    return subject, html_body, text_body


def test_email(config):
    """Send a test email to verify credentials."""
    print("[TEST] Envoi d'un email de test...")
    sub = "🧪 Test de notification - Bybit P2P Alert"
    text = "Ceci est un email de test pour confirmer que vos paramètres SMTP fonctionnent correctement."
    html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; padding: 20px;">
        <h2 style="color: #0284c7;">Test Réussi !</h2>
        <p>Vos paramètres d'envoi d'email pour le script Bybit P2P fonctionnent parfaitement.</p>
        <p><small>Horodatage : {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</small></p>
    </body>
    </html>
    """
    success = send_email(sub, html, text, config)
    if success:
        print("[TEST] ✅ Email de test envoyé avec succès ! Vos identifiants sont valides.")
    else:
        print("[TEST] ❌ Échec de l'envoi. Veuillez vérifier vos identifiants dans config.json.")
    return success


def run_check(config, alerted_ads):
    """
    Run a single check of Bybit P2P prices and send alert if condition met.
    """
    min_price_cfg = config.get("target_min_price")
    min_price = float(min_price_cfg) if min_price_cfg is not None and float(min_price_cfg) > 0 else None
    max_price = float(config.get("target_max_price", 250.0))

    min_budget, max_budget = get_budget_range(config)
    token_id = config.get("token_id", "USDT")
    currency_id = config.get("currency_id", "DZD")
    cooldown_seconds = config.get("notification_cooldown_minutes", 15) * 60

    # Fetch top 50 offers to ensure we see all active sellers
    items = get_p2p_items(token_id=token_id, currency_id=currency_id, page=1, size=50)

    now_ts = time.time()
    now_str = datetime.now().strftime("%H:%M:%S")

    if not items:
        print(f"[{now_str}] Aucune offre disponible pour le moment sur Bybit ({token_id}/{currency_id}).")
        return

    # Extract valid price items and sort ascending
    valid_items = []
    for item in items:
        try:
            p = float(item.get("price", 0))
            valid_items.append((p, item))
        except (ValueError, TypeError):
            continue

    valid_items.sort(key=lambda x: x[0])

    if not valid_items:
        print(f"[{now_str}] Données d'offres invalides reçues.")
        return

    if min_budget == max_budget:
        budget_label = f"{min_budget:.0f} {currency_id}"
    else:
        budget_label = f"{min_budget:.0f}-{max_budget:.0f} {currency_id}"

    target_range_str = f"[{min_price:.2f} - {max_price:.2f} {currency_id}]" if min_price else f"<= {max_price:.2f} {currency_id}"

    # Find the best price that accepts the user's budget range:
    # A trade is possible if:
    # 1) seller.minAmount <= user.max_budget (seller doesn't require more than we want to spend)
    # 2) seller.maxAmount >= user.min_budget (seller has at least our minimum budget)
    best_matching_offer = None
    for p, it in valid_items:
        min_a = float(it.get("minAmount", 0))
        max_a = float(it.get("maxAmount", 0))
        if min_a <= max_budget and (max_a >= min_budget or max_a == 0):
            best_matching_offer = (p, it)
            break

    if best_matching_offer:
        bp, bi = best_matching_offer
        b_min = bi.get('minAmount')
        b_max = bi.get('maxAmount')
        print(f"[{now_str}] Meilleur prix compatible ({budget_label}): {bp:.2f} {currency_id} | Vendeur: {bi.get('nickName')} (Limites: {b_min} - {b_max} {currency_id}) | Cible: {target_range_str}")
    else:
        first_p, first_item = valid_items[0]
        print(f"[{now_str}] Aucune offre acceptant ({budget_label}). Meilleur prix brut marché: {first_p:.2f} {currency_id} ({first_item.get('nickName')}, Limites: {first_item.get('minAmount')} - {first_item.get('maxAmount')}) | Cible: {target_range_str}")

    # Filter matching items by price range and limit compatibility
    matched = []
    for price, item in valid_items:
        if min_price is not None:
            matches_price = (min_price <= price <= max_price)
        else:
            matches_price = (price <= max_price)

        if matches_price:
            ad_id = str(item.get("id"))
            min_amount = float(item.get("minAmount", 0))
            max_amount = float(item.get("maxAmount", 0))

            # Budget overlap verification
            if min_amount <= max_budget and (max_amount >= min_budget or max_amount == 0):
                last_alert = alerted_ads.get(ad_id, 0)
                if now_ts - last_alert > cooldown_seconds:
                    matched.append(item)
                    alerted_ads[ad_id] = now_ts

    if matched:
        print(f"[{now_str}] 🎉 {len(matched)} offre(s) trouvée(s) dans la fourchette {target_range_str} acceptant ({budget_label}) !")
        sub, html, text = build_alert_message(matched, min_price, max_price, min_budget, max_budget, token_id, currency_id)
        send_email(sub, html, text, config)

    return {
        "time": now_str,
        "best_price": bp if best_matching_offer else (first_p if valid_items else None),
        "seller": bi.get('nickName') if best_matching_offer else (first_item.get('nickName') if valid_items else None),
        "limits": f"{b_min} à {b_max} {currency_id}" if best_matching_offer else None,
        "matched_count": len(matched),
        "target_range": target_range_str,
        "budget_label": budget_label
    }


def main():
    parser = argparse.ArgumentParser(description="Moniteur de prix Bybit P2P avec alertes par Email.")
    parser.add_argument("--test-email", action="store_true", help="Envoyer un email de test pour valider la configuration.")
    parser.add_argument("--once", action="store_true", help="Vérifier le prix une seule fois et quitter.")
    args = parser.parse_args()

    config = load_config()

    if args.test_email:
        test_email(config)
        return

    min_p = config.get("target_min_price")
    max_p = float(config.get("target_max_price", 250.0))
    min_budget, max_budget = get_budget_range(config)
    curr = config.get("currency_id", "DZD")
    tok = config.get("token_id", "USDT")

    print("=" * 60)
    print("🚀 DÉMARRAGE DU MONITEUR BYBIT P2P")
    print(f"• Crypto / Devise : {tok} / {curr}")
    if min_budget == max_budget:
        print(f"• Budget d'achat souhaité : {min_budget:.0f} {curr} (soit ~{min_budget / max_p:.2f} {tok} à {max_p:.2f} {curr})")
    else:
        print(f"• Fourchette de budget d'achat : {min_budget:.0f} à {max_budget:.0f} {curr} (soit ~{min_budget / max_p:.2f} à ~{max_budget / max_p:.2f} {tok} à {max_p:.2f} {curr})")

    if min_p is not None and float(min_p) > 0:
        print(f"• Fourchette de prix d'alerte : {float(min_p):.2f} à {max_p:.2f} {curr}")
    else:
        print(f"• Prix max d'alerte : <= {max_p:.2f} {curr}")

    print(f"• Intervalle de test : {config.get('check_interval_seconds', 30)} secondes")
    print(f"• Destinataire email : {config.get('email', {}).get('receiver_email', 'Non configuré')}")
    print("=" * 60)

    alerted_ads = {}

    if args.once:
        run_check(config, alerted_ads)
        return

    interval = max(5, int(config.get("check_interval_seconds", 30)))
    try:
        while True:
            run_check(config, alerted_ads)
            time.sleep(interval)
    except KeyboardInterrupt:
        print("\n[ARRÊT] Surveillance arrêtée par l'utilisateur.")


if __name__ == "__main__":
    main()
