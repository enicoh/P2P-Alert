#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Serveur Cloud 24/7 pour Render / Koyeb / Railway.
Lance la surveillance Bybit P2P en arrière-plan et fournit un tableau de bord HTTP
en temps réel avec auto-rafraîchissement.
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
    "budget_label": None
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
            background: #0f172a;
            color: #f8fafc;
            display: flex;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            margin: 0;
            padding: 20px;
        }}
        .card {{
            background: #1e293b;
            border: 1px solid #334155;
            border-radius: 16px;
            padding: 32px;
            max-width: 500px;
            width: 100%;
            box-shadow: 0 10px 25px rgba(0,0,0,0.4);
        }}
        .badge {{
            display: inline-flex;
            align-items: center;
            gap: 8px;
            background: #064e3b;
            color: #34d399;
            padding: 6px 14px;
            border-radius: 9999px;
            font-size: 13px;
            font-weight: 600;
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
            font-size: 22px;
            margin: 18px 0 6px 0;
        }}
        .subtitle {{
            color: #94a3b8;
            font-size: 14px;
            margin-bottom: 24px;
        }}
        .metric-box {{
            background: #0f172a;
            border-radius: 12px;
            padding: 16px;
            margin-bottom: 12px;
            border: 1px solid #1e293b;
        }}
        .metric-label {{
            color: #64748b;
            font-size: 12px;
            text-transform: uppercase;
            letter-spacing: 0.5px;
            margin-bottom: 4px;
        }}
        .metric-val {{
            font-size: 20px;
            font-weight: 700;
            color: #38bdf8;
        }}
        .info-row {{
            display: flex;
            justify-content: space-between;
            padding: 8px 0;
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
            <div style="color: #94a3b8; font-size: 13px; margin-top: 4px;">Vendeur : <strong>{seller}</strong> ({limits})</div>
        </div>

        <div style="margin-top: 16px;">
            <div class="info-row">
                <span class="info-lbl">Fourchette de prix cible :</span>
                <span class="info-data" style="color: #f59e0b;">{target}</span>
            </div>
            <div class="info-row">
                <span class="info-lbl">Budget recherché :</span>
                <span class="info-data">{budget}</span>
            </div>
            <div class="info-row">
                <span class="info-lbl">Alerte Email :</span>
                <span class="info-data" style="color: #34d399;">Active (Gmail)</span>
            </div>
        </div>

        <div class="footer">
            Page rafraîchie automatiquement toutes les 30s.<br>
            Vous recevrez un email dès que le prix cible est atteint !
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
    while True:
        try:
            res = bybit_p2p_notifier.run_check(config, alerted_ads)
            if res and isinstance(res, dict):
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
