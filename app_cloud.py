#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Serveur Cloud 24/7 pour Render / Koyeb / Railway / Local.
Lance la surveillance P2P Multi-Plateformes (Bybit, Binance, OKX, KuCoin) en arrière-plan
et fournit un tableau de bord HTTP en temps réel avec auto-rafraîchissement et monitoring multi-canaux.
"""

import sys
import os
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
import bybit_p2p_notifier

# Enable unbuffered line-by-line output
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

# Global state shared with the web handler
latest_state = {
    "status": "Démarrage en cours...",
    "time": "En attente...",
    "best_price": None,
    "best_platform": None,
    "seller": None,
    "limits": None,
    "target_range": None,
    "budget_label": None,
    "active_platforms": ["bybit", "binance", "okx", "kucoin"],
    "platform_stats": {},
    "platform_best": {},
    "telegram_active": False,
    "email_active": False,
    "eligible_filter_active": True,
    "ineligible_count": 0,
    "notifications_history": []
}


def get_platform_badge_html(platform):
    """Return a styled badge HTML for a platform."""
    p_lower = str(platform).lower()
    if "binance" in p_lower:
        return '<span class="platform-badge badge-binance">🟡 Binance</span>'
    elif "bybit" in p_lower:
        return '<span class="platform-badge badge-bybit">🟠 Bybit</span>'
    elif "okx" in p_lower:
        return '<span class="platform-badge badge-okx">🔵 OKX</span>'
    elif "kucoin" in p_lower:
        return '<span class="platform-badge badge-kucoin">🟢 KuCoin</span>'
    return f'<span class="platform-badge badge-default">🏷️ {platform}</span>'


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()

        t = latest_state.get("time", "N/A")
        price = latest_state.get("best_price")
        price_str = f"{price:.2f} DZD" if isinstance(price, (int, float)) else "En attente..."
        best_platform = latest_state.get("best_platform") or "P2P"
        seller = latest_state.get("seller") or "En recherche..."
        limits = latest_state.get("limits") or "N/A"
        target = latest_state.get("target_range") or "N/A"
        budget = latest_state.get("budget_label") or "N/A"
        active_plats = latest_state.get("active_platforms", ["bybit", "binance", "okx", "kucoin"])
        platform_stats = latest_state.get("platform_stats", {})
        platform_best = latest_state.get("platform_best", {})
        tg_active = latest_state.get("telegram_active", False)
        email_active = latest_state.get("email_active", False)
        eligible_active = latest_state.get("eligible_filter_active", True)
        ineligible_cnt = latest_state.get("ineligible_count", 0)
        history = latest_state.get("notifications_history", [])

        # Best platform badge
        best_plat_badge = get_platform_badge_html(best_platform) if price else ""

        # Platforms pills
        plat_pills = ""
        for p in active_plats:
            cnt = platform_stats.get(p.lower(), 0)
            plat_pills += f'<span class="plat-chip">{get_platform_badge_html(p)} <small style="opacity:0.75; font-weight:normal;">({cnt} offres)</small></span>'

        # Multi-exchange comparison grid
        comp_cards = ""
        for p_name in ["Bybit", "Binance", "OKX", "KuCoin"]:
            p_key = p_name.lower()
            if p_key in [ap.lower() for ap in active_plats]:
                info = platform_best.get(p_name)
                if info and info.get("price"):
                    p_val = f"{info['price']:.2f} DZD"
                    p_sel = info.get("seller", "")
                    p_url = info.get("url", "#")
                    p_card = f"""
                    <div class="comp-card">
                        <div class="comp-head">{get_platform_badge_html(p_name)}</div>
                        <div class="comp-price">{p_val}</div>
                        <div class="comp-seller">{p_sel}</div>
                        <a href="{p_url}" target="_blank" class="comp-link">Voir l'offre &rarr;</a>
                    </div>
                    """
                else:
                    p_card = f"""
                    <div class="comp-card" style="opacity:0.55;">
                        <div class="comp-head">{get_platform_badge_html(p_name)}</div>
                        <div class="comp-price" style="font-size:16px; margin:10px 0;">Aucune offre</div>
                        <div class="comp-seller">Marché vide</div>
                    </div>
                    """
                comp_cards += p_card

        # Eligibility status badge
        if eligible_active:
            eligible_badge = '<span class="status-pill status-ok">✅ Actif (&lt; 5 achats/mois)</span>'
        else:
            eligible_badge = '<span class="status-pill status-muted">Désactivé</span>'

        # Notification status badges
        if tg_active:
            tg_badge = '<span class="status-pill status-ok">✅ Actif (Recommandé)</span>'
        else:
            tg_badge = '<span class="status-pill status-warn">⚠️ Non configuré</span>'

        if email_active:
            email_badge = '<span class="status-pill status-ok">Configuré (Gmail)</span>'
        else:
            email_badge = '<span class="status-pill status-muted">Désactivé</span>'

        # Build notification history HTML
        history_html = ""
        if history:
            history_rows = ""
            for item in history[:3]:
                ch_badges = ""
                for n in item.get("notifs", []):
                    ch = n.get("channel", "")
                    ok = n.get("success", False)
                    detail = n.get("detail", "")
                    color = "#34d399" if ok else "#f87171"
                    icon = "✅" if ok else "❌"
                    ch_badges += f'<div style="font-size:12px; margin-top:2px; color:{color};">{icon} <strong>{ch}:</strong> {detail}</div>'

                item_plat = item.get("platform", "P2P")
                history_rows += f"""
                <div style="background:#0f172a; border-radius:10px; padding:12px; margin-bottom:8px; border:1px solid #334155;">
                    <div style="display:flex; justify-content:space-between; align-items:center; font-size:13px; font-weight:600; color:#f1f5f9;">
                        <span>{get_platform_badge_html(item_plat)} {item.get('seller', 'Offre')} à {item.get('price', '')} DZD</span>
                        <span style="color:#94a3b8; font-weight:normal; font-size:12px;">{item.get('time', '')}</span>
                    </div>
                    {ch_badges}
                </div>
                """
            history_html = f"""
            <div style="margin-top: 20px; border-top: 1px solid #334155; padding-top: 16px;">
                <div class="metric-label" style="margin-bottom:10px;">Dernières alertes déclenchées :</div>
                {history_rows}
            </div>
            """

        html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="refresh" content="30">
    <title>P2P Multi-Exchange Monitor (Algérie) - Cloud 24/7</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif;
            background: #0b1120;
            color: #f8fafc;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            margin: 0;
            padding: 24px 16px;
            box-sizing: border-box;
        }}
        .card {{
            background: #1e293b;
            border: 1px solid #334155;
            border-radius: 24px;
            padding: 32px;
            max-width: 600px;
            width: 100%;
            box-shadow: 0 25px 50px -12px rgba(0,0,0,0.6);
        }}
        .badge {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
            background: #064e3b;
            color: #34d399;
            padding: 6px 14px;
            border-radius: 9999px;
            font-size: 12px;
            font-weight: 700;
            letter-spacing: 0.5px;
        }}
        .badge::before {{
            content: '';
            width: 8px;
            height: 8px;
            border-radius: 50%;
            background: #34d399;
            box-shadow: 0 0 10px #34d399;
        }}
        h1 {{
            font-size: 24px;
            margin: 16px 0 4px 0;
            font-weight: 800;
        }}
        .subtitle {{
            color: #94a3b8;
            font-size: 13px;
            margin-bottom: 20px;
        }}
        .plat-chips-row {{
            display: flex;
            flex-wrap: wrap;
            gap: 8px;
            margin-bottom: 16px;
        }}
        .plat-chip {{
            background: #0f172a;
            border: 1px solid #334155;
            padding: 4px 10px;
            border-radius: 8px;
            font-size: 12px;
            display: inline-flex;
            align-items: center;
            gap: 6px;
        }}
        .platform-badge {{
            display: inline-flex;
            align-items: center;
            padding: 2px 8px;
            border-radius: 6px;
            font-size: 11px;
            font-weight: 700;
        }}
        .badge-binance {{ background: #713f12; color: #facc15; border: 1px solid #a16207; }}
        .badge-bybit {{ background: #7c2d12; color: #fb923c; border: 1px solid #c2410c; }}
        .badge-okx {{ background: #1e3a8a; color: #60a5fa; border: 1px solid #2563eb; }}
        .badge-kucoin {{ background: #064e3b; color: #34d399; border: 1px solid #059669; }}
        .badge-default {{ background: #334155; color: #e2e8f0; }}

        .metric-box {{
            background: linear-gradient(135deg, #0f172a, #1e293b);
            border-radius: 16px;
            padding: 20px;
            margin-bottom: 16px;
            border: 1px solid #3b82f640;
            box-shadow: 0 4px 16px rgba(0,0,0,0.3);
        }}
        .metric-label {{
            color: #94a3b8;
            font-size: 11px;
            text-transform: uppercase;
            font-weight: 700;
            letter-spacing: 0.6px;
            margin-bottom: 4px;
        }}
        .metric-val {{
            font-size: 30px;
            font-weight: 900;
            color: #38bdf8;
            display: flex;
            align-items: center;
            gap: 12px;
        }}
        .comp-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(120px, 1fr));
            gap: 10px;
            margin: 16px 0;
        }}
        .comp-card {{
            background: #0f172a;
            border: 1px solid #334155;
            border-radius: 12px;
            padding: 12px;
            text-align: center;
        }}
        .comp-head {{
            margin-bottom: 6px;
        }}
        .comp-price {{
            font-size: 16px;
            font-weight: 800;
            color: #f1f5f9;
        }}
        .comp-seller {{
            font-size: 11px;
            color: #94a3b8;
            white-space: nowrap;
            overflow: hidden;
            text-overflow: ellipsis;
            margin: 4px 0;
        }}
        .comp-link {{
            font-size: 11px;
            color: #38bdf8;
            text-decoration: none;
            font-weight: 600;
        }}
        .comp-link:hover {{
            text-decoration: underline;
        }}

        .info-row {{
            display: flex;
            justify-content: space-between;
            align-items: center;
            padding: 10px 0;
            border-bottom: 1px solid #334155;
            font-size: 14px;
        }}
        .info-row:last-child {{
            border-bottom: none;
        }}
        .info-lbl {{
            color: #94a3b8;
        }}
        .info-data {{
            font-weight: 600;
            color: #f1f5f9;
        }}
        .status-pill {{
            font-size: 12px;
            padding: 3px 10px;
            border-radius: 6px;
            font-weight: 600;
        }}
        .status-ok {{
            background: #064e3b;
            color: #34d399;
        }}
        .status-warn {{
            background: #78350f;
            color: #fbbf24;
        }}
        .status-muted {{
            background: #334155;
            color: #94a3b8;
        }}
        .footer {{
            text-align: center;
            margin-top: 24px;
            color: #64748b;
            font-size: 12px;
        }}
    </style>
</head>
<body>
    <div class="card">
        <div class="badge">SURVEILLANCE P2P MULTI-EXCHANGE 24/7</div>
        <h1>P2P Price Alert Notifier</h1>
        <div class="subtitle">Dernière vérification : {t} &bull; USDT / DZD</div>

        <div class="plat-chips-row">
            {plat_pills}
        </div>

        <div class="metric-box">
            <div class="metric-label">Meilleur prix compatible détecté</div>
            <div class="metric-val">
                {price_str} {best_plat_badge}
            </div>
            <div style="color: #94a3b8; font-size: 13px; margin-top: 6px;">Vendeur : <strong style="color:#f8fafc;">{seller}</strong> ({limits})</div>
            {f'<div style="color: #64748b; font-size: 12px; margin-top: 6px;">🛡️ {ineligible_cnt} vendeur(s) inéligible(s) écarté(s) (exigences &gt; 0 ordre)</div>' if ineligible_cnt > 0 else ''}
        </div>

        <div class="metric-label" style="margin-top:16px;">Comparateur en direct par plateforme :</div>
        <div class="comp-grid">
            {comp_cards}
        </div>

        <div style="margin-top: 12px;">
            <div class="info-row">
                <span class="info-lbl">Fourchette de prix cible :</span>
                <span class="info-data" style="color: #f59e0b;">{target}</span>
            </div>
            <div class="info-row">
                <span class="info-lbl">Budget d'achat :</span>
                <span class="info-data">{budget}</span>
            </div>
            <div class="info-row">
                <span class="info-lbl">Filtre éligibilité acheteur :</span>
                <span>{eligible_badge}</span>
            </div>
            <div class="info-row">
                <span class="info-lbl">Alerte Telegram :</span>
                <span>{tg_badge}</span>
            </div>
            <div class="info-row">
                <span class="info-lbl">Alerte Email :</span>
                <span>{email_badge}</span>
            </div>
        </div>

        {history_html}

        <div class="footer">
            Surveillance automatique Bybit &bull; Binance &bull; OKX &bull; KuCoin &bull; Auto-refresh 30s
        </div>
    </div>
</body>
</html>
"""
        self.wfile.write(html.encode("utf-8"))

    def log_message(self, format, *args):
        # Silence HTTP access logs
        return


def monitor_loop():
    config = bybit_p2p_notifier.load_config()
    alerted_ads = {}
    interval = max(10, int(config.get("check_interval_seconds", 30)))
    print(f"[CLOUD] Surveillance multi-plateformes démarrée en tâche de fond (intervalle: {interval}s)...", flush=True)

    # Initial check on launch
    try:
        res = bybit_p2p_notifier.run_check(config, alerted_ads)
        if res and isinstance(res, dict):
            latest_state.update(res)
    except Exception as e:
        print(f"[CLOUD ERREUR DÉMARRAGE] {e}", flush=True)

    while True:
        try:
            # Reload config to support dynamic env or file updates
            config = bybit_p2p_notifier.load_config()
            res = bybit_p2p_notifier.run_check(config, alerted_ads)
            if res and isinstance(res, dict):
                # If notifications were sent in this tick, save them to history
                notifs = res.get("notifications_sent")
                if notifs:
                    hist = latest_state.get("notifications_history", [])
                    hist.insert(0, {
                        "time": res.get("time"),
                        "platform": res.get("best_platform"),
                        "seller": res.get("seller"),
                        "price": res.get("best_price"),
                        "notifs": notifs
                    })
                    latest_state["notifications_history"] = hist[:10]

                latest_state.update(res)
        except Exception as e:
            print(f"[CLOUD ERREUR] {e}", flush=True)
        time.sleep(interval)


def main():
    # Start monitor loop in background thread
    t = threading.Thread(target=monitor_loop, daemon=True)
    t.start()

    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    print(f"[CLOUD] Serveur HTTP démarré sur le port {port}. Tableau de bord multi-plateformes prêt !", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("[CLOUD] Arrêt du serveur.", flush=True)


if __name__ == "__main__":
    main()
