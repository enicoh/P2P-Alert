#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
P2P Multi-Exchange Price Alert Notifier (Algeria - USDT/DZD)
Monitors P2P offers across Bybit, Binance, OKX, and KuCoin.
Sends Telegram, Discord, or Email notifications when a seller offers
the desired price within your target purchase budget range.
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
import concurrent.futures

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
BINANCE_P2P_URL = "https://p2p.binance.com/bapi/c2c/v2/friendly/c2c/adv/search"


def make_urlopen(req, timeout=12, retries=1):
    """
    Open URL with automatic retry and fallback to unverified SSL context if local
    antivirus, VPN, or corporate proxy intercepts HTTPS with a self-signed certificate.
    """
    for attempt in range(retries + 1):
        try:
            return urllib.request.urlopen(req, timeout=timeout)
        except urllib.error.URLError as e:
            err_str = str(e).lower()
            if "certificate_verify_failed" in err_str or "certificate verify failed" in err_str:
                ctx = ssl._create_unverified_context()
                return urllib.request.urlopen(req, context=ctx, timeout=timeout)
            if attempt < retries:
                time.sleep(0.8)
                continue
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

    # Platforms configuration
    if os.environ.get("PLATFORMS"):
        cfg["platforms"] = os.environ["PLATFORMS"].strip()
    elif os.environ.get("PLATFORM"):
        cfg["platforms"] = os.environ["PLATFORM"].strip()
    elif "platforms" not in cfg and "platform" not in cfg:
        cfg["platforms"] = ["bybit", "binance", "okx", "kucoin"]

    # Target prices and amounts
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


def get_configured_platforms(config):
    """
    Get the list of normalized platforms to monitor.
    Supports config key 'platforms' (list or string), 'platform' (string or list),
    or environment variables 'PLATFORMS' / 'PLATFORM'.
    Options: 'all', 'bybit', 'binance', 'okx', 'kucoin'.
    """
    env_plat = os.environ.get("PLATFORMS") or os.environ.get("PLATFORM")
    raw = env_plat if env_plat is not None else config.get("platforms", config.get("platform", "all"))

    if isinstance(raw, str):
        parts = [p.strip().lower() for p in raw.replace(";", ",").split(",") if p.strip()]
    elif isinstance(raw, (list, tuple)):
        parts = [str(p).strip().lower() for p in raw if str(p).strip()]
    else:
        parts = ["all"]

    if not parts or "all" in parts:
        return ["bybit", "binance", "okx", "kucoin"]

    valid = ["bybit", "binance", "okx", "kucoin"]
    filtered = [p for p in parts if p in valid]
    return filtered if filtered else ["bybit", "binance", "okx", "kucoin"]


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
        min_b = 2000.0
        max_b = 13000.0

    if min_b > max_b:
        min_b, max_b = max_b, min_b
    return min_b, max_b


def is_buyer_eligible(item, config):
    """
    Check if the buyer is eligible according to the merchant's trading preferences.
    Dispatches to platform-specific eligibility rules (Bybit, Binance, OKX, KuCoin).
    """
    profile = config.get("buyer_profile", {})
    if not profile.get("filter_eligible_only", True):
        return True, "Filtre désactivé"

    platform = item.get("platform", "").lower()
    raw = item.get("raw", {})
    user_orders = int(profile.get("completed_orders_30d", 0))
    has_kyc = bool(profile.get("has_kyc", True))
    user_age = int(profile.get("account_age_days", 90))
    user_rate = float(profile.get("completion_rate_30d", 100.0))
    user_nat = str(profile.get("nationality", "DZA")).strip().upper()

    if platform == "bybit":
        pref = raw.get("tradingPreferenceSet") or {}
        if pref.get("hasOrderFinishNumberDay30") in (1, "1", True):
            try:
                req_orders = int(pref.get("orderFinishNumberDay30") or 0)
            except (ValueError, TypeError):
                req_orders = 0
            if user_orders < req_orders:
                return False, f"Bybit: exige >= {req_orders} ordres/30j (profil: {user_orders})"
        if pref.get("isKyc") in (1, "1", True) and not has_kyc:
            return False, "Bybit: exige KYC vérifié"
        if pref.get("hasRegisterTime") in (1, "1", True):
            try:
                req_days = int(pref.get("registerTimeThreshold") or 0)
            except (ValueError, TypeError):
                req_days = 0
            if user_age < req_days:
                return False, f"Bybit: compte >= {req_days} jours (profil: {user_age}j)"
        if pref.get("hasCompleteRateDay30") in (1, "1", True):
            try:
                req_rate = float(pref.get("completeRateDay30") or 0)
            except (ValueError, TypeError):
                req_rate = 0.0
            if user_rate < req_rate:
                return False, f"Bybit: taux >= {req_rate}% (profil: {user_rate}%)"
        if pref.get("hasNationalLimit") in (1, "1", True):
            req_nat = str(pref.get("nationalLimit") or "").strip().upper()
            if req_nat and user_nat and req_nat != user_nat:
                return False, f"Bybit: nationalité {req_nat} requise (profil: {user_nat})"

    elif platform == "binance":
        adv = raw.get("adv", {})
        b_buy = int(adv.get("userBuyTradeCountMin") or 0)
        b_all = int(adv.get("userAllTradeCountMin") or 0)
        req_orders = max(b_buy, b_all)
        if req_orders > 0 and user_orders < req_orders:
            return False, f"Binance: exige >= {req_orders} ordres (profil: {user_orders})"
        b_days = int(adv.get("buyerRegDaysLimit") or 0)
        if b_days > 0 and user_age < b_days:
            return False, f"Binance: compte >= {b_days} jours (profil: {user_age}j)"
        if adv.get("takerAdditionalKycRequired", 0) > 0 and not has_kyc:
            return False, "Binance: exige KYC additionnel"

    elif platform == "okx":
        min_orders = int(raw.get("minCompletedOrderQuantity") or 0)
        if min_orders > 0 and user_orders < min_orders:
            return False, f"OKX: exige >= {min_orders} ordres (profil: {user_orders})"
        min_kyc = int(raw.get("minKycLevel") or 0)
        if min_kyc > 1 and not has_kyc:
            return False, f"OKX: exige KYC niveau {min_kyc}"

    elif platform == "kucoin":
        if raw.get("needKyc") == "YES" and not has_kyc:
            return False, "KuCoin: exige KYC vérifié"

    return True, "Éligible"


def fetch_bybit(token_id="USDT", currency_id="DZD", timeout=12):
    """Fetch active P2P ads from Bybit."""
    payload = {
        "tokenId": token_id,
        "currencyId": currency_id,
        "side": "1",
        "page": "1",
        "size": "50",
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
    req = urllib.request.Request(BYBIT_P2P_URL, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    try:
        with make_urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if data.get("ret_code") != 0:
            return []
        items = data.get("result", {}).get("items", []) or []
        res = []
        for it in items:
            raw_payments = it.get("payments", [])
            payments = []
            for p in raw_payments:
                if isinstance(p, dict) and p.get("paymentName"):
                    payments.append(p.get("paymentName"))
                elif isinstance(p, str):
                    payments.append(p)
            res.append({
                "platform": "Bybit",
                "id": f"bybit_{it.get('id')}",
                "nickName": it.get("nickName", "Inconnu"),
                "price": float(it.get("price", 0)),
                "minAmount": float(it.get("minAmount", 0)),
                "maxAmount": float(it.get("maxAmount", 0)),
                "quantity": float(it.get("lastQuantity", it.get("quantity", 0))),
                "recentOrderNum": int(it.get("recentOrderNum", 0)),
                "recentExecuteRate": float(it.get("recentExecuteRate", 0)),
                "payments": payments,
                "url": "https://www.bybit.com/fiat/otc/",
                "raw": it
            })
        return res
    except Exception as e:
        print(f"[BYBIT] Erreur de récupération: {e}")
        return []


def fetch_binance(token_id="USDT", currency_id="DZD", timeout=12):
    """Fetch active P2P ads from Binance."""
    payload = {
        "asset": token_id,
        "fiat": currency_id,
        "merchantCheck": False,
        "page": 1,
        "payTypes": [],
        "publisherType": None,
        "rows": 30,
        "tradeType": "BUY"
    }
    headers = {
        "Content-Type": "application/json",
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Origin": "https://p2p.binance.com",
        "Referer": "https://p2p.binance.com/"
    }
    req = urllib.request.Request(BINANCE_P2P_URL, data=json.dumps(payload).encode("utf-8"), headers=headers, method="POST")
    try:
        with make_urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        items = data.get("data", []) or []
        res = []
        for it in items:
            adv = it.get("adv", {})
            adv_er = it.get("advertiser", {})
            payments = [m.get("tradeMethodName") for m in adv.get("tradeMethods", []) if m.get("tradeMethodName")]
            rate = float(adv_er.get("monthFinishRate", 0)) * 100
            user_no = adv_er.get("userNo", "")
            ad_url = f"https://p2p.binance.com/fr/advertiserDetail?userNo={user_no}" if user_no else "https://p2p.binance.com/fr/express/buy/USDT/DZD"
            res.append({
                "platform": "Binance",
                "id": f"binance_{adv.get('advNo')}",
                "nickName": adv_er.get("nickName", "Inconnu"),
                "price": float(adv.get("price", 0)),
                "minAmount": float(adv.get("minSingleTransAmount", 0)),
                "maxAmount": float(adv.get("dynamicMaxSingleTransAmount", adv.get("maxSingleTransAmount", 0))),
                "quantity": float(adv.get("tradableQuantity", adv.get("surplusAmount", 0))),
                "recentOrderNum": int(adv_er.get("monthOrderCount", 0)),
                "recentExecuteRate": round(rate, 1),
                "payments": payments,
                "url": ad_url,
                "raw": it
            })
        return res
    except Exception as e:
        print(f"[BINANCE] Erreur de récupération: {e}")
        return []


def fetch_okx(token_id="USDT", currency_id="DZD", timeout=12):
    """
    Fetch active P2P sell ads from OKX (merchants selling crypto to buyers).
    side=sell represents sellers offering USDT for fiat.
    """
    url = f"https://www.okx.com/v3/c2c/tradingOrders/books?quoteCurrency={currency_id.lower()}&baseCurrency={token_id.lower()}&side=sell&paymentMethod=all&userType=all&showTrade=false&showAlreadyTraded=false&isAbleFilter=false"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Referer": "https://www.okx.com/p2p-markets/dzd/buy-usdt"
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with make_urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        items = data.get("data", {}).get("sell", []) or []
        res = []
        for it in items:
            rate = float(it.get("completedRate", 0)) * 100
            res.append({
                "platform": "OKX",
                "id": f"okx_{it.get('id')}",
                "nickName": it.get("nickName", "Inconnu"),
                "price": float(it.get("price", 0)),
                "minAmount": float(it.get("quoteMinAmountPerOrder", 0)),
                "maxAmount": float(it.get("quoteMaxAmountPerOrder", 0)),
                "quantity": float(it.get("availableAmount", 0)),
                "recentOrderNum": int(it.get("completedOrderQuantity", 0)),
                "recentExecuteRate": round(rate, 1),
                "payments": it.get("paymentMethods", []),
                "url": "https://www.okx.com/p2p-markets/dzd/buy-usdt",
                "raw": it
            })
        return res
    except Exception as e:
        print(f"[OKX] Erreur de récupération: {e}")
        return []


def fetch_kucoin(token_id="USDT", currency_id="DZD", timeout=12):
    """
    Fetch active P2P ads from KuCoin.
    Filters out merchants who are offline.
    """
    url = f"https://www.kucoin.com/_api/otc/ad/list?status=PUTUP&currency={token_id.upper()}&legal={currency_id.upper()}&page=1&pageSize=20&side=SELL"
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Accept": "application/json",
        "Referer": "https://www.kucoin.com/otc"
    }
    req = urllib.request.Request(url, headers=headers)
    try:
        with make_urlopen(req, timeout=timeout) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        items = data.get("items", []) or []
        res = []
        for it in items:
            # Skip merchants who are offline or inactive
            if str(it.get("onlineStatus", "")).upper() == "OFFLINE" and not it.get("online", False):
                continue

            rate_str = str(it.get("dealOrderRate", "0")).replace("%", "")
            try:
                rate = float(rate_str)
            except Exception:
                rate = 0.0
            p = float(it.get("floatPrice") or it.get("premium", 0))
            res.append({
                "platform": "KuCoin",
                "id": f"kucoin_{it.get('id')}",
                "nickName": it.get("nickName", "Inconnu"),
                "price": p,
                "minAmount": float(it.get("limitMinQuote", 0)),
                "maxAmount": float(it.get("limitMaxQuote", 0)),
                "quantity": float(it.get("currencyBalanceQuantity", it.get("currencyQuantity", 0))),
                "recentOrderNum": int(it.get("dealOrderNum", 0)),
                "recentExecuteRate": round(rate, 1),
                "payments": ["BaridiMob / CCP"],
                "url": "https://www.kucoin.com/otc/buy/USDT/DZD",
                "raw": it
            })
        return res
    except Exception as e:
        print(f"[KUCOIN] Erreur de récupération: {e}")
        return []


def get_p2p_items(token_id="USDT", currency_id="DZD", page=1, size=50):
    """Backward compatibility helper - fetches Bybit items."""
    return fetch_bybit(token_id=token_id, currency_id=currency_id)


def fetch_all_offers(config):
    """
    Fetch P2P items across all configured platforms in parallel using ThreadPoolExecutor.
    Returns (all_items, platform_stats).
    """
    platforms = get_configured_platforms(config)
    token_id = config.get("token_id", "USDT")
    currency_id = config.get("currency_id", "DZD")

    fetch_map = {
        "bybit": fetch_bybit,
        "binance": fetch_binance,
        "okx": fetch_okx,
        "kucoin": fetch_kucoin
    }

    all_items = []
    platform_stats = {}

    with concurrent.futures.ThreadPoolExecutor(max_workers=len(platforms) or 1) as executor:
        future_to_plat = {
            executor.submit(fetch_map[plat], token_id, currency_id): plat
            for plat in platforms if plat in fetch_map
        }
        for future in concurrent.futures.as_completed(future_to_plat):
            plat = future_to_plat[future]
            try:
                items = future.result()
                platform_stats[plat] = len(items)
                all_items.extend(items)
            except Exception as e:
                print(f"[{plat.upper()}] Échec du fetch: {e}")
                platform_stats[plat] = 0

    return all_items, platform_stats


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
        headers={"Content-Type": "application/json", "User-Agent": "P2PNotifier/3.0"},
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
    best = matched_items[0]
    best_platform = best.get("platform", "P2P")
    best_price = float(best.get("price", 0))

    if min_budget == max_budget:
        budget_str = f"{min_budget:,.0f} {currency_id}".replace(",", " ")
    else:
        budget_str = f"{min_budget:,.0f} à {max_budget:,.0f} {currency_id}".replace(",", " ")

    price_range_str = f"{min_price:.2f} - {max_price:.2f} {currency_id}" if min_price else f"<= {max_price:.2f} {currency_id}"

    lines = [
        f"🚨 <b>ALERTE P2P MULTI-PLATEFORMES !</b>",
        f"🏆 <b>Meilleur prix :</b> <code>{best_price:.2f} {currency_id}</code> ({best_platform})",
        f"🎯 <b>Cible :</b> <code>{price_range_str}</code>",
        f"💼 <b>Budget :</b> <code>{budget_str}</code>",
        "────────────────────"
    ]

    for item in matched_items[:5]:
        plat = item.get("platform", "P2P")
        nick = item.get("nickName", "Inconnu")
        price = float(item.get("price", 0))
        min_amt = float(item.get("minAmount", 0))
        max_amt = float(item.get("maxAmount", 0))
        orders = item.get("recentOrderNum", 0)
        rate = item.get("recentExecuteRate", 0)
        url = item.get("url", "https://www.bybit.com/fiat/otc/")

        if min_budget == max_budget:
            crypto_est = f"~{min_budget / price:.2f} {token_id}"
        else:
            crypto_est = f"~{min_budget / price:.2f} à ~{max_budget / price:.2f} {token_id}"

        lim_str = f"{min_amt:,.0f} à {max_amt:,.0f} {currency_id}".replace(",", " ")
        lines.append(
            f"🏷️ [<b>{plat}</b>] <b>{nick}</b>\n"
            f"💵 Prix : <b>{price:.2f} {currency_id}</b> / {token_id}\n"
            f"🪙 Obtenu : <b>{crypto_est}</b>\n"
            f"📊 Limites : {lim_str}\n"
            f"⭐ Ordres : {orders} ({rate}%)\n"
            f"👉 <a href=\"{url}\"><b>Acheter sur {plat}</b></a>\n"
        )

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
        headers={"Content-Type": "application/json", "User-Agent": "P2PNotifier/3.0"},
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
    msg["From"] = f"Alerte P2P Multi-Exchange <{sender}>"
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
    """Build formatted plain text and HTML emails for matching offers across platforms."""
    first_item = matched_items[0]
    first_price = float(first_item.get("price", 0))
    first_platform = first_item.get("platform", "P2P")

    if min_budget == max_budget:
        budget_str = f"{min_budget:,.0f} {currency_id}".replace(",", " ")
    else:
        budget_str = f"{min_budget:,.0f} à {max_budget:,.0f} {currency_id}".replace(",", " ")

    price_range_str = f"{min_price:.2f} à {max_price:.2f} {currency_id}" if min_price else f"<= {max_price:.2f} {currency_id}"
    subject = f"🔥 Alerte P2P : {first_price:.2f} {currency_id} sur {first_platform} (Budget {budget_str})"

    rows_html = ""
    rows_text = ""

    for item in matched_items:
        plat = item.get("platform", "P2P")
        nick = item.get("nickName", "Inconnu")
        price = float(item.get("price", 0))
        min_amt = float(item.get("minAmount", 0))
        max_amt = float(item.get("maxAmount", 0))
        qty = item.get("quantity", 0)
        orders = item.get("recentOrderNum", 0)
        rate = item.get("recentExecuteRate", 0)
        url = item.get("url", "https://p2p.binance.com")

        if min_budget == max_budget:
            crypto_detail = f"~{min_budget / price:.2f} {token_id}"
        else:
            crypto_detail = f"~{min_budget / price:.2f} à ~{max_budget / price:.2f} {token_id}"

        lim_str = f"{min_amt:,.0f} - {max_amt:,.0f} {currency_id}".replace(",", " ")

        rows_text += (
            f"\n- [{plat}] {nick}\n"
            f"  Prix: {price:.2f} {currency_id} / {token_id}\n"
            f"  Pour votre budget ({budget_str}): {crypto_detail}\n"
            f"  Limites vendeur: {lim_str}\n"
            f"  Ordres récents: {orders} (Taux: {rate}%)\n"
            f"  Lien: {url}\n"
        )

        rows_html += f"""
        <tr style="border-bottom: 1px solid #e0e0e0;">
            <td style="padding: 12px; font-weight: bold; color: #f59e0b;">{plat}</td>
            <td style="padding: 12px; font-weight: bold; color: #1e293b;">{nick}</td>
            <td style="padding: 12px; color: #16a34a; font-weight: bold; font-size: 16px;">{price:.2f} {currency_id}</td>
            <td style="padding: 12px; font-weight: bold; color: #0284c7;">{crypto_detail}</td>
            <td style="padding: 12px; color: #64748b;">{lim_str}</td>
            <td style="padding: 12px; color: #64748b;">{orders} ({rate}%)</td>
            <td style="padding: 12px;"><a href="{url}" style="color:#0284c7; font-weight:bold; text-decoration:none;">Ouvrir</a></td>
        </tr>
        """

    text_body = f"""Bonjour,

Une ou plusieurs offres correspondent à vos critères sur les marchés P2P !

Critères configurés :
- Prix recherché : {price_range_str}
- Fourchette de budget : {budget_str} (limites vendeur compatibles)

Offres trouvées :{rows_text}

Bon achat !
"""

    html_body = f"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
</head>
<body style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif; background-color: #f8fafc; padding: 20px; margin: 0;">
    <div style="max-width: 780px; margin: 0 auto; background-color: #ffffff; border-radius: 12px; box-shadow: 0 4px 12px rgba(0,0,0,0.06); overflow: hidden; border: 1px solid #e2e8f0;">
        <div style="background: linear-gradient(135deg, #f59e0b, #d97706); padding: 24px; color: #ffffff; text-align: center;">
            <h1 style="margin: 0; font-size: 24px;">🚀 Alerte P2P Multi-Plateformes Déclenchée</h1>
            <p style="margin: 8px 0 0 0; opacity: 0.95; font-size: 15px;">
                Meilleur prix sur <strong>{first_platform}</strong> : <strong>{first_price:.2f} {currency_id}</strong> | Budget : <strong>{budget_str}</strong>
            </p>
        </div>
        <div style="padding: 24px;">
            <p style="color: #334155; font-size: 15px; margin-top: 0;">
                De nouvelles offres correspondent à vos critères (prix + limites compatibles avec votre budget de {budget_str}) :
            </p>
            <table style="width: 100%; border-collapse: collapse; margin: 20px 0; font-size: 14px; text-align: left;">
                <thead>
                    <tr style="background-color: #f1f5f9; color: #475569;">
                        <th style="padding: 10px 12px;">Plateforme</th>
                        <th style="padding: 10px 12px;">Vendeur</th>
                        <th style="padding: 10px 12px;">Prix / {token_id}</th>
                        <th style="padding: 10px 12px;">Reçu estimé</th>
                        <th style="padding: 10px 12px;">Limites vendeur</th>
                        <th style="padding: 10px 12px;">Taux</th>
                        <th style="padding: 10px 12px;">Lien</th>
                    </tr>
                </thead>
                <tbody>
                    {rows_html}
                </tbody>
            </table>
            <div style="text-align: center; margin: 30px 0 10px 0;">
                <a href="{first_item.get('url', 'https://p2p.binance.com')}" target="_blank"
                   style="background-color: #0284c7; color: #ffffff; text-decoration: none; padding: 12px 28px; border-radius: 8px; font-weight: bold; display: inline-block;">
                   Ouvrir l'offre sur {first_platform}
                </a>
            </div>
        </div>
        <div style="background-color: #f8fafc; padding: 14px; text-align: center; font-size: 12px; color: #94a3b8; border-top: 1px solid #e2e8f0;">
            Alerte automatique multi-plateformes générée à {datetime.now().strftime('%H:%M:%S')}
        </div>
    </div>
</body>
</html>
"""
    return subject, html_body, text_body


def test_telegram(config):
    """Send a test message via Telegram."""
    platforms = [p.capitalize() for p in get_configured_platforms(config)]
    print("[TEST TELEGRAM] Envoi d'un message test...")
    text = (
        "🤖 <b>Test de Notification P2P Multi-Plateformes</b>\n\n"
        "✅ Votre bot Telegram est parfaitement connecté et configuré !\n"
        f"🌐 <b>Plateformes surveillées :</b> {', '.join(platforms)}\n"
        f"⏰ Horodatage : <code>{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}</code>\n\n"
        "Vous recevrez une alerte instantanée dès qu'une offre compatible est trouvée avec le meilleur prix parmi toutes les plateformes."
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
    content = f"🧪 **Test Réussi !** Le webhook Discord du notificateur P2P Multi-Plateformes fonctionne correctement. ({datetime.now().strftime('%H:%M:%S')})"
    ok, msg = send_discord(content, config)
    if ok:
        print("[TEST DISCORD] ✅ Succès ! Message envoyé sur Discord.")
    else:
        print(f"[TEST DISCORD] ❌ Échec : {msg}")
    return ok


def test_email(config):
    """Send a test email to verify credentials."""
    print("[TEST EMAIL] Envoi d'un email de test...")
    sub = "🧪 Test de notification - P2P Multi-Exchange Alert"
    text = "Ceci est un email de test pour confirmer que vos paramètres SMTP fonctionnent correctement."
    html = f"""
    <html>
    <body style="font-family: Arial, sans-serif; padding: 20px;">
        <h2 style="color: #0284c7;">Test Réussi !</h2>
        <p>Vos paramètres d'envoi d'email pour le script P2P Alert fonctionnent parfaitement.</p>
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
    Run a single check of P2P prices across configured exchanges and dispatch notifications.
    """
    min_price_cfg = config.get("target_min_price")
    min_price = float(min_price_cfg) if min_price_cfg is not None and float(min_price_cfg) > 0 else None
    max_price = float(config.get("target_max_price", 255.0))

    min_budget, max_budget = get_budget_range(config)
    token_id = config.get("token_id", "USDT")
    currency_id = config.get("currency_id", "DZD")
    cooldown_seconds = config.get("notification_cooldown_minutes", 15) * 60

    active_platforms = get_configured_platforms(config)
    now_ts = time.time()
    now_str = datetime.now().strftime("%H:%M:%S")

    # Fetch offers across all configured platforms in parallel
    items, platform_stats = fetch_all_offers(config)

    plat_summary = ", ".join([f"{p.upper()}: {cnt}" for p, cnt in platform_stats.items()])
    print(f"[{now_str}] Offres récupérées ({plat_summary})")

    if min_budget == max_budget:
        budget_label = f"{min_budget:,.0f} {currency_id}".replace(",", " ")
    else:
        budget_label = f"{min_budget:,.0f}-{max_budget:,.0f} {currency_id}".replace(",", " ")

    target_range_str = f"[{min_price:.2f} - {max_price:.2f} {currency_id}]" if min_price else f"<= {max_price:.2f} {currency_id}"

    if not items:
        print(f"[{now_str}] Aucune offre disponible pour le moment ({token_id}/{currency_id}).")
        return {
            "time": now_str,
            "best_price": None,
            "best_platform": None,
            "seller": None,
            "limits": None,
            "matched_count": 0,
            "target_range": target_range_str,
            "budget_label": budget_label,
            "active_platforms": active_platforms,
            "platform_stats": platform_stats,
            "platform_best": {},
            "notifications_sent": [],
            "telegram_active": bool(config.get("telegram", {}).get("enabled", True) and config.get("telegram", {}).get("bot_token") and config.get("telegram", {}).get("chat_id")),
            "email_active": bool(config.get("email", {}).get("enabled", True) and config.get("email", {}).get("sender_email")),
            "ineligible_count": 0,
            "eligible_filter_active": bool(config.get("buyer_profile", {}).get("filter_eligible_only", True))
        }

    # Extract valid price items that pass buyer eligibility check
    valid_items = []
    ineligible_items = []
    platform_best = {}

    for item in items:
        try:
            p = float(item.get("price", 0))
            if p <= 0:
                continue

            plat = item.get("platform", "P2P")
            if plat not in platform_best or p < platform_best[plat]["price"]:
                platform_best[plat] = {
                    "price": p,
                    "seller": item.get("nickName"),
                    "limits": f"{item.get('minAmount', 0):,.0f} à {item.get('maxAmount', 0):,.0f} {currency_id}".replace(",", " "),
                    "url": item.get("url")
                }

            is_ok, reason = is_buyer_eligible(item, config)
            if not is_ok:
                ineligible_items.append((p, item, reason))
                continue
            valid_items.append((p, item))
        except (ValueError, TypeError):
            continue

    valid_items.sort(key=lambda x: x[0])

    if ineligible_items:
        excluded_preview = ", ".join([f"{it.get('platform')}:{it.get('nickName')} ({rs})" for _, it, rs in ineligible_items[:3]])
        more_cnt = len(ineligible_items) - 3
        more_str = f" et +{more_cnt} autre(s)" if more_cnt > 0 else ""
        print(f"[{now_str}] 🛡️ {len(ineligible_items)} offre(s) écartée(s) (critères d'éligibilité non remplis : {excluded_preview}{more_str})")

    if not valid_items:
        print(f"[{now_str}] Aucune offre éligible disponible actuellement sur les marchés surveillés.")
        return {
            "time": now_str,
            "best_price": None,
            "best_platform": None,
            "seller": None,
            "limits": None,
            "matched_count": 0,
            "target_range": target_range_str,
            "budget_label": budget_label,
            "active_platforms": active_platforms,
            "platform_stats": platform_stats,
            "platform_best": platform_best,
            "notifications_sent": [],
            "telegram_active": bool(config.get("telegram", {}).get("enabled", True) and config.get("telegram", {}).get("bot_token") and config.get("telegram", {}).get("chat_id")),
            "email_active": bool(config.get("email", {}).get("enabled", True) and config.get("email", {}).get("sender_email")),
            "ineligible_count": len(ineligible_items),
            "eligible_filter_active": bool(config.get("buyer_profile", {}).get("filter_eligible_only", True))
        }

    # Find the best price that accepts the user's budget range within target price
    best_matching_offer = None
    for p, it in valid_items:
        if min_price is not None and p < min_price:
            continue
        if p > max_price:
            continue
        min_a = float(it.get("minAmount", 0))
        max_a = float(it.get("maxAmount", 0))
        if min_a <= max_budget and (max_a >= min_budget or max_a == 0):
            best_matching_offer = (p, it)
            break

    # If none found within target price, find best compatible offer above min_price (or first valid)
    if not best_matching_offer:
        for p, it in valid_items:
            if min_price is not None and p < min_price:
                continue
            min_a = float(it.get("minAmount", 0))
            max_a = float(it.get("maxAmount", 0))
            if min_a <= max_budget and (max_a >= min_budget or max_a == 0):
                best_matching_offer = (p, it)
                break

    if best_matching_offer:
        bp, bi = best_matching_offer
        b_plat = bi.get('platform', 'P2P')
        b_min = bi.get('minAmount', 0)
        b_max = bi.get('maxAmount', 0)
        lim_fmt = f"{b_min:,.0f} à {b_max:,.0f} {currency_id}".replace(",", " ")
        print(f"[{now_str}] 🏆 Meilleur prix compatible ({budget_label}): {bp:.2f} {currency_id} sur [{b_plat}] | Vendeur: {bi.get('nickName')} (Limites: {lim_fmt}) | Cible: {target_range_str}")
    else:
        first_p, first_item = valid_items[0]
        f_plat = first_item.get('platform', 'P2P')
        f_min = first_item.get('minAmount', 0)
        f_max = first_item.get('maxAmount', 0)
        lim_fmt = f"{f_min:,.0f} à {f_max:,.0f} {currency_id}".replace(",", " ")
        print(f"[{now_str}] Aucune offre acceptant ({budget_label}). Meilleur prix brut marché: {first_p:.2f} {currency_id} sur [{f_plat}] ({first_item.get('nickName')}, Limites: {lim_fmt}) | Cible: {target_range_str}")

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
        winner = matched[0]
        print(f"[{now_str}] 🎉 {len(matched)} offre(s) trouvée(s) dans la fourchette {target_range_str} acceptant ({budget_label}) ! (Top: {winner.get('price')} {currency_id} sur {winner.get('platform')})")

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
            dc_text = f"🚀 **Alerte P2P** : {len(matched)} offre(s) compatible(s) trouvée(s) ! Meilleur prix: {matched[0].get('price')} {currency_id} sur **{matched[0].get('platform')}** ({matched[0].get('nickName')}). {matched[0].get('url')}"
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
        "best_platform": bi.get('platform') if best_matching_offer else (first_item.get('platform') if valid_items else None),
        "seller": bi.get('nickName') if best_matching_offer else (first_item.get('nickName') if valid_items else None),
        "limits": f"{b_min:,.0f} à {b_max:,.0f} {currency_id}".replace(",", " ") if best_matching_offer else None,
        "matched_count": len(matched),
        "target_range": target_range_str,
        "budget_label": budget_label,
        "active_platforms": active_platforms,
        "platform_stats": platform_stats,
        "platform_best": platform_best,
        "notifications_sent": notifications_sent,
        "telegram_active": tg_active,
        "email_active": email_active,
        "ineligible_count": len(ineligible_items),
        "eligible_filter_active": bool(config.get("buyer_profile", {}).get("filter_eligible_only", True))
    }


def main():
    parser = argparse.ArgumentParser(description="Moniteur de prix P2P Multi-Plateformes (Bybit, Binance, OKX, KuCoin) avec alertes Telegram & Email.")
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
    max_p = float(config.get("target_max_price", 255.0))
    min_budget, max_budget = get_budget_range(config)
    curr = config.get("currency_id", "DZD")
    tok = config.get("token_id", "USDT")
    active_plats = [p.capitalize() for p in get_configured_platforms(config)]

    tg_ready = bool(config.get("telegram", {}).get("enabled", True) and config.get("telegram", {}).get("bot_token") and config.get("telegram", {}).get("chat_id"))
    em_ready = bool(config.get("email", {}).get("enabled", False) and config.get("email", {}).get("sender_email") and config.get("email", {}).get("sender_password"))

    buyer_cfg = config.get("buyer_profile", {})
    filt_on = buyer_cfg.get("filter_eligible_only", True)
    ord_lim = buyer_cfg.get("completed_orders_30d", 0)

    print("=" * 65)
    print("🚀 DÉMARRAGE DU MONITEUR P2P MULTI-PLATEFORMES")
    print(f"• Plateformes surveillées : {', '.join(active_plats)}")
    print(f"• Crypto / Devise : {tok} / {curr}")
    if min_budget == max_budget:
        print(f"• Budget d'achat : {min_budget:,.0f} {curr} (~{min_budget / max_p:.2f} {tok} à {max_p:.2f} {curr})".replace(",", " "))
    else:
        print(f"• Fourchette de budget : {min_budget:,.0f} à {max_budget:,.0f} {curr} (~{min_budget / max_p:.2f} à ~{max_budget / max_p:.2f} {tok})".replace(",", " "))

    if min_p is not None and float(min_p) > 0:
        print(f"• Fourchette de prix d'alerte : {float(min_p):.2f} à {max_p:.2f} {curr}")
    else:
        print(f"• Prix max d'alerte : <= {max_p:.2f} {curr}")

    print(f"• Filtre éligibilité vendeur : {'✅ Actif (exclut vendeurs exigeant > ' + str(ord_lim) + ' ordres)' if filt_on else '❌ Désactivé'}")
    print(f"• Intervalle de test : {config.get('check_interval_seconds', 30)} secondes")
    print(f"• Canal Telegram : {'✅ Configuré (Recommandé Cloud)' if tg_ready else '⚠️ Non configuré'}")
    print(f"• Canal Email : {'✅ Configuré' if em_ready else '⚪ Désactivé'}")
    print("=" * 65)

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
