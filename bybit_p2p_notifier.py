#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bybit P2P Price Alert Notifier
Monitors Bybit P2P offers and sends Telegram, Discord, or Email notifications
when a seller offers the desired price and matches your target purchase budget range.
"""

import sys
import json
import time
import smtplib
import argparse
import ssl
from datetime import datetime
import urllib.request
import urllib.error
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from pathlib import Path
import os

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

CONFIG_FILE = Path(__file__).resolve().parent / "config.json"
BYBIT_P2P_URL = "https://api2.bybit.com/fiat/otc/item/online"


def make_urlopen(req, timeout=15):
    """
    Open URL with automatic fallback to unverified SSL context if local
    antivirus, VPN, or corporate proxy intercepts HTTPS with a self-signed certificate.
    """
    try:
        return urllib.request.urlopen(req, timeout=timeout)
    except urllib.error.URLError as e:
        err_str = str(e).lower()
        if "certificate_verify_failed" in err_str or "certificate verify failed" in err_str:
            ctx = ssl._create_unverified_context()
            return urllib.request.urlopen(req, context=ctx, timeout=timeout)
        raise


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

    # Telegram configuration
    tg_cfg = cfg.setdefault("telegram", {})
    if os.environ.get("TELEGRAM_BOT_TOKEN"):
        tg_cfg["bot_token"] = os.environ["TELEGRAM_BOT_TOKEN"].strip()
    if os.environ.get("TELEGRAM_CHAT_ID"):
        tg_cfg["chat_id"] = os.environ["TELEGRAM_CHAT_ID"].strip()
    if os.environ.get("TELEGRAM_ENABLED") is not None:
        tg_cfg["enabled"] = os.environ["TELEGRAM_ENABLED"].lower() in ("1", "true", "yes")

    # Discord configuration
    dc_cfg = cfg.setdefault("discord", {})
    if os.environ.get("DISCORD_WEBHOOK_URL"):
        dc_cfg["webhook_url"] = os.environ["DISCORD_WEBHOOK_URL"].strip()
    if os.environ.get("DISCORD_ENABLED") is not None:
        dc_cfg["enabled"] = os.environ["DISCORD_ENABLED"].lower() in ("1", "true", "yes")

    # Email configuration
    email_cfg = cfg.setdefault("email", {})
    if os.environ.get("SENDER_EMAIL"):
        email_cfg["sender_email"] = os.environ["SENDER_EMAIL"].strip()
    if os.environ.get("SENDER_PASSWORD"):
        email_cfg["sender_password"] = os.environ["SENDER_PASSWORD"].strip()
    if os.environ.get("RECEIVER_EMAIL"):
        email_cfg["receiver_email"] = os.environ["RECEIVER_EMAIL"].strip()

    # Buyer eligibility configuration
    buyer_cfg = cfg.setdefault("buyer_profile", {})
    if os.environ.get("FILTER_ELIGIBLE_ONLY") is not None:
        buyer_cfg["filter_eligible_only"] = os.environ["FILTER_ELIGIBLE_ONLY"].lower() in ("1", "true", "yes")
    if os.environ.get("BUYER_COMPLETED_ORDERS_30D") is not None:
        buyer_cfg["completed_orders_30d"] = int(os.environ["BUYER_COMPLETED_ORDERS_30D"])
    if os.environ.get("BUYER_HAS_KYC") is not None:
        buyer_cfg["has_kyc"] = os.environ["BUYER_HAS_KYC"].lower() in ("1", "true", "yes")
    if os.environ.get("BUYER_ACCOUNT_AGE_DAYS") is not None:
        buyer_cfg["account_age_days"] = int(os.environ["BUYER_ACCOUNT_AGE_DAYS"])
    if os.environ.get("BUYER_NATIONALITY"):
        buyer_cfg["nationality"] = os.environ["BUYER_NATIONALITY"].strip().upper()

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


def is_buyer_eligible(item, config):
    """
    Check if the buyer is eligible according to the merchant's trading preferences (tradingPreferenceSet).
    Specifically handles infrequent buyers (e.g. < 5 purchases/month) who are blocked by merchants
    requiring 5, 10, or 60 completed orders in the last 30 days.
    """
    profile = config.get("buyer_profile", {})
    if not profile.get("filter_eligible_only", True):
        return True, "Filtre désactivé"

    pref = item.get("tradingPreferenceSet") or {}

    # 1. Check required completed orders in last 30 days
    if pref.get("hasOrderFinishNumberDay30") in (1, "1", True):
        try:
            req_orders = int(pref.get("orderFinishNumberDay30") or 0)
        except (ValueError, TypeError):
            req_orders = 0
        user_orders = int(profile.get("completed_orders_30d", 0))
        if user_orders < req_orders:
            return False, f"exige >= {req_orders} ordres/30j (profil acheteur: {user_orders})"

    # 2. Check KYC requirement
    if pref.get("isKyc") in (1, "1", True):
        if not profile.get("has_kyc", True):
            return False, "exige KYC vérifié"

    # 3. Check account registration age requirement (days)
    if pref.get("hasRegisterTime") in (1, "1", True):
        try:
            req_days = int(pref.get("registerTimeThreshold") or 0)
        except (ValueError, TypeError):
            req_days = 0
        user_age = int(profile.get("account_age_days", 90))
        if user_age < req_days:
            return False, f"compte créé depuis au moins {req_days} jours (profil: {user_age}j)"

    # 4. Check 30-day order completion rate requirement
    if pref.get("hasCompleteRateDay30") in (1, "1", True):
        try:
            req_rate = float(pref.get("completeRateDay30") or 0)
        except (ValueError, TypeError):
            req_rate = 0.0
        user_rate = float(profile.get("completion_rate_30d", 100.0))
        if user_rate < req_rate:
            return False, f"taux de réussite >= {req_rate}% (profil: {user_rate}%)"

    # 5. Check nationality limit requirement
    if pref.get("hasNationalLimit") in (1, "1", True):
        req_nat = str(pref.get("nationalLimit") or "").strip().upper()
        user_nat = str(profile.get("nationality", "DZA")).strip().upper()
        if req_nat and user_nat and req_nat != user_nat:
            return False, f"nationalité {req_nat} requise (profil: {user_nat})"

    return True, "Éligible"


def get_p2p_items(token_id="USDT", currency_id="DZD", page=1, size=50):
    """
    Fetch P2P ads from Bybit.
    side = '1' corresponds to Sell ads (sellers offering crypto for fiat).
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
        with make_urlopen(req, timeout=15) as resp:
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


def send_telegram(text, config):
    """Send an alert message via Telegram Bot API using standard HTTPS POST."""
    tg_cfg = config.get("telegram", {})
    if not tg_cfg.get("enabled", True):
        return False, "Telegram désactivé dans la configuration"

    bot_token = tg_cfg.get("bot_token", "").strip()
    chat_id = tg_cfg.get("chat_id", "").strip()

    if not bot_token or not chat_id:
        return False, "Token de bot ou Chat ID Telegram non renseigné"

    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True
    }
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "BybitNotifier/2.0"},
        method="POST"
    )

    try:
        with make_urlopen(req, timeout=15) as resp:
            res_body = resp.read().decode("utf-8")
            res_json = json.loads(res_body)
            if res_json.get("ok"):
                print("[SUCCÈS] 📱 Notification Telegram envoyée avec succès !")
                return True, "Envoyé avec succès sur Telegram"
            else:
                err = res_json.get("description", "Erreur Telegram inconnue")
                print(f"[ERREUR TELEGRAM] {err}")
                return False, f"Erreur API Telegram: {err}"
    except Exception as e:
        print(f"[ERREUR TELEGRAM] Échec de l'envoi: {e}")
        return False, f"Échec de l'envoi Telegram: {e}"


def build_telegram_message(matched_items, min_price, max_price, min_budget, max_budget, token_id, currency_id):
    """Build a clean, high-priority HTML formatted message for Telegram."""
    if min_budget == max_budget:
        budget_str = f"{min_budget:,.0f} {currency_id}".replace(",", " ")
    else:
        budget_str = f"{min_budget:,.0f} à {max_budget:,.0f} {currency_id}".replace(",", " ")

    price_range_str = f"{min_price:.2f} - {max_price:.2f} {currency_id}" if min_price else f"<= {max_price:.2f} {currency_id}"

    lines = [
        "🚨 <b>ALERTE BYBIT P2P DÉTECTÉE !</b>",
        f"🎯 <b>Cible :</b> <code>{price_range_str}</code>",
        f"💼 <b>Budget :</b> <code>{budget_str}</code>",
        "🛡️ <b>Éligibilité :</b> <code>Vendeur compatible vérifié</code>",
        "────────────────────"
    ]

    for item in matched_items[:4]:
        nick = item.get("nickName", "Inconnu")
        price = float(item.get("price", 0))
        min_amt = item.get("minAmount", "0")
        max_amt = item.get("maxAmount", "0")
        orders = item.get("recentOrderNum", 0)
        rate = item.get("recentExecuteRate", 0)

        if min_budget == max_budget:
            crypto_est = f"~{min_budget / price:.2f} {token_id}"
        else:
            crypto_est = f"~{min_budget / price:.2f} à ~{max_budget / price:.2f} {token_id}"

        lines.append(
            f"👤 <b>{nick}</b>\n"
            f"💵 Prix : <b>{price:.2f} {currency_id}</b> / {token_id}\n"
            f"🪙 Obtenu : <b>{crypto_est}</b>\n"
            f"📊 Limites : {min_amt} à {max_amt} {currency_id}\n"
            f"⭐ Ordres : {orders} ({rate}%)\n"
        )

    lines.append('🔗 <a href="https://www.bybit.com/fiat/otc/">👉 <b>Ouvrir Bybit P2P pour acheter</b></a>')
    return "\n".join(lines)


def send_discord(content, config):
    """Send a notification message via Discord Webhook."""
    dc_cfg = config.get("discord", {})
    if not dc_cfg.get("enabled", False):
        return False, "Discord désactivé dans la configuration"

    webhook_url = dc_cfg.get("webhook_url", "").strip()
    if not webhook_url:
        return False, "URL Webhook Discord manquante"

    payload = {"content": content}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        webhook_url,
        data=data,
        headers={"Content-Type": "application/json", "User-Agent": "BybitNotifier/2.0"},
        method="POST"
    )

    try:
        with make_urlopen(req, timeout=15) as resp:
            print("[SUCCÈS] 💬 Notification Discord envoyée avec succès !")
            return True, "Envoyé avec succès sur Discord"
    except Exception as e:
        print(f"[ERREUR DISCORD] {e}")
        return False, f"Échec de l'envoi Discord: {e}"


def send_email(subject, html_body, text_body, config):
    """Send an email using SMTP credentials configured in config.json."""
    email_cfg = config.get("email", {})
    if not email_cfg.get("enabled", True):
        print("[INFO] Envoi d'email désactivé dans la configuration.")
        return False, "Email désactivé dans la configuration"

    sender = email_cfg.get("sender_email")
    password = email_cfg.get("sender_password")
    receiver = email_cfg.get("receiver_email")
    smtp_server = email_cfg.get("smtp_server", "smtp.gmail.com")
    smtp_port = email_cfg.get("smtp_port", 587)
    use_tls = email_cfg.get("use_tls", True)

    if not sender or not password or not receiver or "votre_email" in sender:
        print("[ATTENTION] Veuillez renseigner 'sender_email', 'sender_password' et 'receiver_email' dans config.json !")
        return False, "Identifiants email incomplets dans config.json"

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
        print(f"[SUCCÈS] 📧 Email envoyé à {receiver} !")
        return True, f"Email envoyé à {receiver}"
    except Exception as e:
        err_msg = str(e)
        if "timed out" in err_msg.lower() or "110" in err_msg or "refused" in err_msg.lower():
            err_msg += " (Port SMTP bloqué par l'hébergeur cloud, ex: Render Free)"
        print(f"[ERREUR EMAIL] Échec de l'envoi de l'email: {err_msg}")
        return False, err_msg


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


def test_telegram(config):
    """Send a test message via Telegram."""
    print("[TEST TELEGRAM] Envoi d'un message test...")
    text = (
        "🤖 <b>Test de Notification Bybit P2P</b>\n\n"
        "✅ Votre bot Telegram est parfaitement connecté et configuré !\n"
        f"⏰ Horodatage : <code>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</code>\n\n"
        "Vous recevrez une alerte instantanée dès qu'une offre compatible est trouvée."
    )
    ok, msg = send_telegram(text, config)
    if ok:
        print("[TEST TELEGRAM] ✅ Succès ! Message reçu sur votre Telegram.")
    else:
        print(f"[TEST TELEGRAM] ❌ Échec : {msg}")
    return ok


def test_discord(config):
    """Send a test message via Discord webhook."""
    print("[TEST DISCORD] Envoi d'un message test...")
    content = f"🧪 **Test Réussi !** Le webhook Discord du notificateur Bybit P2P fonctionne correctement. ({datetime.now().strftime('%H:%M:%S')})"
    ok, msg = send_discord(content, config)
    if ok:
        print("[TEST DISCORD] ✅ Succès ! Message envoyé sur Discord.")
    else:
        print(f"[TEST DISCORD] ❌ Échec : {msg}")
    return ok


def test_email(config):
    """Send a test email to verify credentials."""
    print("[TEST EMAIL] Envoi d'un email de test...")
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
    ok, msg = send_email(sub, html, text, config)
    if ok:
        print("[TEST EMAIL] ✅ Email de test envoyé avec succès ! Vos identifiants sont valides.")
    else:
        print(f"[TEST EMAIL] ❌ Échec de l'envoi : {msg}")
    return ok


def run_check(config, alerted_ads):
    """
    Run a single check of Bybit P2P prices and dispatch notifications across configured channels.
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
        return None

    # Extract valid price items that pass buyer eligibility check
    valid_items = []
    ineligible_items = []
    for item in items:
        try:
            p = float(item.get("price", 0))
            is_ok, reason = is_buyer_eligible(item, config)
            if not is_ok:
                ineligible_items.append((p, item, reason))
                continue
            valid_items.append((p, item))
        except (ValueError, TypeError):
            continue

    valid_items.sort(key=lambda x: x[0])

    if ineligible_items:
        excluded_preview = ", ".join([f"{it.get('nickName')} ({rs})" for _, it, rs in ineligible_items[:3]])
        more_cnt = len(ineligible_items) - 3
        more_str = f" et +{more_cnt} autre(s)" if more_cnt > 0 else ""
        print(f"[{now_str}] 🛡️ {len(ineligible_items)} offre(s) écartée(s) (critères d'éligibilité non remplis : {excluded_preview}{more_str})")

    if not valid_items:
        print(f"[{now_str}] Aucune offre éligible disponible actuellement sur Bybit.")
        return {
            "time": now_str,
            "best_price": None,
            "seller": None,
            "limits": None,
            "matched_count": 0,
            "target_range": target_range_str,
            "budget_label": budget_label,
            "notifications_sent": [],
            "telegram_active": bool(config.get("telegram", {}).get("enabled", True) and config.get("telegram", {}).get("bot_token") and config.get("telegram", {}).get("chat_id")),
            "email_active": bool(config.get("email", {}).get("enabled", True) and config.get("email", {}).get("sender_email")),
            "ineligible_count": len(ineligible_items),
            "eligible_filter_active": bool(config.get("buyer_profile", {}).get("filter_eligible_only", True))
        }

    if min_budget == max_budget:
        budget_label = f"{min_budget:.0f} {currency_id}"
    else:
        budget_label = f"{min_budget:.0f}-{max_budget:.0f} {currency_id}"

    target_range_str = f"[{min_price:.2f} - {max_price:.2f} {currency_id}]" if min_price else f"<= {max_price:.2f} {currency_id}"

    # Find the best price that accepts the user's budget range
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

    notifications_sent = []

    if matched:
        print(f"[{now_str}] 🎉 {len(matched)} offre(s) trouvée(s) dans la fourchette {target_range_str} acceptant ({budget_label}) !")

        # 1. Telegram Alert
        tg_cfg = config.get("telegram", {})
        if tg_cfg.get("enabled", True) and tg_cfg.get("bot_token") and tg_cfg.get("chat_id"):
            tg_text = build_telegram_message(matched, min_price, max_price, min_budget, max_budget, token_id, currency_id)
            ok, msg = send_telegram(tg_text, config)
            notifications_sent.append({"channel": "Telegram", "success": ok, "detail": msg, "time": now_str})
        elif tg_cfg.get("enabled", True) and not tg_cfg.get("bot_token"):
            print(f"[{now_str}] [INFO] Telegram activé mais token non configuré.")

        # 2. Discord Alert
        dc_cfg = config.get("discord", {})
        if dc_cfg.get("enabled", False) and dc_cfg.get("webhook_url"):
            dc_text = f"🚀 **Alerte Bybit P2P** : {len(matched)} offre(s) compatible(s) trouvée(s) ! Meilleur prix: {matched[0].get('price')} {currency_id}. https://www.bybit.com/fiat/otc/"
            ok, msg = send_discord(dc_text, config)
            notifications_sent.append({"channel": "Discord", "success": ok, "detail": msg, "time": now_str})

        # 3. Email Alert
        em_cfg = config.get("email", {})
        if em_cfg.get("enabled", True) and em_cfg.get("sender_email") and em_cfg.get("sender_password"):
            sub, html, text = build_alert_message(matched, min_price, max_price, min_budget, max_budget, token_id, currency_id)
            ok, msg = send_email(sub, html, text, config)
            notifications_sent.append({"channel": "Email", "success": ok, "detail": msg, "time": now_str})

    tg_active = bool(config.get("telegram", {}).get("enabled", True) and config.get("telegram", {}).get("bot_token") and config.get("telegram", {}).get("chat_id"))
    email_active = bool(config.get("email", {}).get("enabled", True) and config.get("email", {}).get("sender_email"))

    return {
        "time": now_str,
        "best_price": bp if best_matching_offer else (first_p if valid_items else None),
        "seller": bi.get('nickName') if best_matching_offer else (first_item.get('nickName') if valid_items else None),
        "limits": f"{b_min} à {b_max} {currency_id}" if best_matching_offer else None,
        "matched_count": len(matched),
        "target_range": target_range_str,
        "budget_label": budget_label,
        "notifications_sent": notifications_sent,
        "telegram_active": tg_active,
        "email_active": email_active,
        "ineligible_count": len(ineligible_items),
        "eligible_filter_active": bool(config.get("buyer_profile", {}).get("filter_eligible_only", True))
    }


def main():
    parser = argparse.ArgumentParser(description="Moniteur de prix Bybit P2P avec alertes Telegram & Email.")
    parser.add_argument("--test-email", action="store_true", help="Envoyer un email de test pour valider la configuration SMTP.")
    parser.add_argument("--test-telegram", action="store_true", help="Envoyer un message de test sur Telegram.")
    parser.add_argument("--test-discord", action="store_true", help="Envoyer un message de test sur Discord.")
    parser.add_argument("--test-all", action="store_true", help="Tester tous les canaux de notifications configurés.")
    parser.add_argument("--once", action="store_true", help="Vérifier le prix une seule fois et quitter.")
    args = parser.parse_args()

    config = load_config()

    if args.test_telegram or args.test_all:
        test_telegram(config)
    if args.test_discord or args.test_all:
        test_discord(config)
    if args.test_email or args.test_all:
        test_email(config)
    if args.test_telegram or args.test_discord or args.test_email or args.test_all:
        return

    min_p = config.get("target_min_price")
    max_p = float(config.get("target_max_price", 250.0))
    min_budget, max_budget = get_budget_range(config)
    curr = config.get("currency_id", "DZD")
    tok = config.get("token_id", "USDT")

    tg_ready = bool(config.get("telegram", {}).get("enabled", True) and config.get("telegram", {}).get("bot_token") and config.get("telegram", {}).get("chat_id"))
    em_ready = bool(config.get("email", {}).get("enabled", False) and config.get("email", {}).get("sender_email") and config.get("email", {}).get("sender_password"))

    buyer_cfg = config.get("buyer_profile", {})
    filt_on = buyer_cfg.get("filter_eligible_only", True)
    ord_lim = buyer_cfg.get("completed_orders_30d", 0)

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

    print(f"• Filtre éligibilité vendeur : {'✅ Actif (exclut vendeurs exigeant > ' + str(ord_lim) + ' ordres/30j)' if filt_on else '❌ Désactivé'}")
    print(f"• Intervalle de test : {config.get('check_interval_seconds', 30)} secondes")
    print(f"• Canal Telegram : {'✅ Configuré (Recommandé Cloud)' if tg_ready else '⚠️ Non configuré (bot_token/chat_id manquants)'}")
    print(f"• Canal Email : {'✅ Configuré' if em_ready else '⚪ Désactivé'}")
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
