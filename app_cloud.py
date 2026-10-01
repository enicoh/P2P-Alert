#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Serveur Cloud 24/7 pour Render / Koyeb / Railway / Local.
Lance la surveillance Bybit P2P en arrière-plan et fournit un tableau de bord HTTP
en temps réel avec auto-rafraîchissement et monitoring multi-canaux (Telegram & Email).
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
    "seller": None,
    "limits": None,
    "target_range": None,
    "budget_label": None,
    "telegram_active": False,
    "email_active": False,
    "notifications_history": []
}


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()

        t = latest_state.get("time", "N/A")
        price = latest_state.get("best_price")
        price_str = f"{price:.2f} DZD" if isinstance(price, (int, float)) else "En attente..."
        seller = latest_state.get("seller") or "En recherche..."
        limits = latest_state.get("limits") or "N/A"
        target = latest_state.get("target_range") or "N/A"
        budget = latest_state.get("budget_label") or "N/A"
        tg_active = latest_state.get("telegram_active", False)
        email_active = latest_state.get("email_active", False)
        history = latest_state.get("notifications_history", [])

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
                
                history_rows += f"""
                <div style="background:#0f172a; border-radius:8px; padding:10px; margin-bottom:8px; border:1px solid #334155;">
                    <div style="display:flex; justify-content:space-between; font-size:13px; font-weight:600; color:#f1f5f9;">
                        <span>{item.get('seller', 'Offre')} à {item.get('price', '')} DZD</span>
                        <span style="color:#94a3b8; font-weight:normal;">{item.get('time', '')}</span>
                    </div>
                    {ch_badges}
                </div>
                """
            history_html = f"""
            <div style="margin-top: 18px; border-top: 1px solid #334155; padding-top: 14px;">
                <div class="metric-label" style="margin-bottom:8px;">Dernière(s) alerte(s) déclenchée(s) :</div>
                {history_rows}
            </div>
            """

        html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta http-equiv="refresh" content="30">
    <title>Bybit P2P Monitor - Cloud 24/7</title>
    <style>
        body {{
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #0b1120;
            color: #f8fafc;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            margin: 0;
            padding: 20px;
            box-sizing: border-box;
        }}
        .card {{
            background: #1e293b;
            border: 1px solid #334155;
            border-radius: 20px;
            padding: 28px;
            max-width: 520px;
            width: 100%;
            box-shadow: 0 20px 40px rgba(0,0,0,0.5);
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
        .metric-box {{
            background: #0f172a;
            border-radius: 14px;
            padding: 18px;
            margin-bottom: 14px;
            border: 1px solid #1e293b;
        }}
        .metric-label {{
            color: #64748b;
            font-size: 11px;
            text-transform: uppercase;
            font-weight: 700;
            letter-spacing: 0.6px;
            margin-bottom: 4px;
        }}
        .metric-val {{
            font-size: 24px;
            font-weight: 800;
            color: #38bdf8;
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
        .cloud-tip {{
            background: #172554;
            border: 1px solid #1e40af;
            border-radius: 12px;
            padding: 12px 14px;
            margin-top: 16px;
            font-size: 12px;
            line-height: 1.5;
            color: #93c5fd;
        }}
        .footer {{
            text-align: center;
            margin-top: 20px;
            color: #64748b;
            font-size: 12px;
        }}
    </style>
</head>
<body>
    <div class="card">
        <div class="badge">SURVEILLANCE ACTIVE 24/7</div>
        <h1>Bybit P2P Notifier</h1>
        <div class="subtitle">Dernière actualisation : {t}</div>

        <div class="metric-box">
            <div class="metric-label">Meilleur prix compatible détecté</div>
            <div class="metric-val">{price_str}</div>
            <div style="color: #94a3b8; font-size: 13px; margin-top: 6px;">Vendeur : <strong style="color:#f8fafc;">{seller}</strong> ({limits})</div>
        </div>

        <div style="margin-top: 8px;">
            <div class="info-row">
                <span class="info-lbl">Fourchette de prix cible :</span>
                <span class="info-data" style="color: #f59e0b;">{target}</span>
            </div>
            <div class="info-row">
                <span class="info-lbl">Budget recherché :</span>
                <span class="info-data">{budget}</span>
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

        {"" if tg_active else '''
        <div class="cloud-tip">
            💡 <strong>Conseil Cloud :</strong> Render bloque les emails SMTP gratuits. Pour recevoir les alertes sur votre smartphone sans aucun blocage, configurez <strong>Telegram</strong> (variables d\'environnement <code>TELEGRAM_BOT_TOKEN</code> et <code>TELEGRAM_CHAT_ID</code> sur Render).
        </div>
        '''}

        <div class="footer">
            Page rafraîchie automatiquement toutes les 30s.
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
    print(f"[CLOUD] Surveillance démarrée en tâche de fond (intervalle: {interval}s)...", flush=True)

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
    print(f"[CLOUD] Serveur HTTP démarré sur le port {port}. Prêt pour le cloud 24/7 !", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("[CLOUD] Arrêt du serveur.", flush=True)


if __name__ == "__main__":
    main()
