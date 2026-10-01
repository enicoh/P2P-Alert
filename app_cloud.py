#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Serveur Cloud 24/7 pour Render / Koyeb / Railway.
Lance la surveillance Bybit P2P en arrière-plan et fournit un endpoint HTTP
pour les hébergeurs gratuits qui requièrent un port ouvert.
"""

import os
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
import bybit_p2p_notifier


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-type", "text/html; charset=utf-8")
        self.end_headers()
        html = f"""
        <html>
        <head><title>Bybit P2P Notifier 24/7</title></head>
        <body style="font-family: Arial; padding: 20px; background: #0f172a; color: white;">
            <h2>✅ Le moniteur Bybit P2P tourne en ligne 24h/24</h2>
            <p>Dernière vérification active.</p>
        </body>
        </html>
        """
        self.wfile.write(html.encode("utf-8"))

    def log_message(self, format, *args):
        # Silence les logs HTTP pour ne pas polluer la console
        return


def monitor_loop():
    config = bybit_p2p_notifier.load_config()
    alerted_ads = {}
    interval = max(10, int(config.get("check_interval_seconds", 30)))
    print(f"[CLOUD] Surveillance démarrée en tâche de fond (intervalle: {interval}s)...")
    while True:
        try:
            bybit_p2p_notifier.run_check(config, alerted_ads)
        except Exception as e:
            print(f"[CLOUD ERREUR] {e}")
        time.sleep(interval)


def main():
    # Démarre la boucle de surveillance en thread d'arrière-plan
    t = threading.Thread(target=monitor_loop, daemon=True)
    t.start()

    # Démarre le serveur web léger sur le port requis par l'hébergeur cloud
    port = int(os.environ.get("PORT", 8080))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    print(f"[CLOUD] Serveur HTTP démarré sur le port {port}. Prêt pour le cloud 24/7 !")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("[CLOUD] Arrêt du serveur.")


if __name__ == "__main__":
    main()
