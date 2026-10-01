# 🔔 Bybit P2P Price Alert Notifier

Script Python autonome pour surveiller en temps réel les prix sur le marché **Bybit P2P** (ex: **USDT / DZD**) et envoyer une **alerte par Email** dès qu'un vendeur propose le prix désiré (par exemple &le; 250 DA pour 20$).

---

## ⚡ Caractéristiques

- **Zéro installation externe requise** : fonctionne avec la bibliothèque standard Python (`urllib`, `smtplib`, `json`).
- **Filtre automatique du montant** : vérifie que le vendeur accepte bien votre montant d'achat (ex: 20$ soit ~5 000 DA) en respectant ses limites minimales et maximales.
- **Email soigné (HTML & Texte)** : détails complets sur le vendeur (nom, prix unitaire, total à payer, nombre d'ordres, taux d'exécution, lien direct vers Bybit).
- **Système anti-spam (Cooldown)** : évite de vous spammer d'emails toutes les 30 secondes pour la même annonce.
- **Commande de test** : permet de valider vos identifiants email en un instant sans attendre de baisse de prix.

---

## ⚙️ 1. Configuration (`config.json`)

Ouvrez le fichier [`config.json`](file:///c:/Users/tassili/Desktop/Bybit%20Script/config.json) et ajustez vos paramètres :

```json
{
  "target_min_price": 240.0,
  "target_max_price": 250.0,
  "target_amount_dzd": 5000.0,
  "buy_amount_usd": 20.0,
  "token_id": "USDT",
  "currency_id": "DZD",
  "check_interval_seconds": 30,
  "notification_cooldown_minutes": 15,
  "email": {
    "enabled": true,
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587,
    "use_tls": true,
    "sender_email": "votre_email@gmail.com",
    "sender_password": "votre_mot_de_passe_application",
    "receiver_email": "votre_email@gmail.com"
  }
}
```

### Explication des paramètres :
- `target_min_price` : Le prix minimum pour déclencher l'alerte (ex: `240.0`).
- `target_max_price` : Le prix maximum accepté en DZD (ex: `250.0`). L'alerte se déclenche si le prix est entre 240 et 250 DZD.
- `min_amount_dzd` : Votre montant d'achat minimum en DZD (ex: `10000.0`).
- `max_amount_dzd` : Votre montant d'achat maximum en DZD (ex: `13000.0`).
  > 💡 Le script vérifie la compatibilité des limites du vendeur : si un vendeur propose par exemple un minimum de 10 000 DA ou jusqu'à 13 000 DA, son offre est prise en compte !
- `check_interval_seconds` : Temps d'attente entre deux vérifications en secondes (ex: `30`).
- `notification_cooldown_minutes` : Temps avant de ré-alerter pour la même offre (ex: `15` minutes).

---

## 📧 2. Configuration Email (Exemple Gmail)

Pour autoriser Python à envoyer des emails via Gmail en toute sécurité :

1. Rendez-vous sur votre compte Google : [Sécurité Google](https://myaccount.google.com/security)
2. Activez la **Validation en deux étapes** (2-Step Verification) si ce n'est pas déjà fait.
3. Recherchez **Mots de passe des applications** (ou visitez directement [https://myaccount.google.com/apppasswords](https://myaccount.google.com/apppasswords)).
4. Donnez un nom (ex: `Bybit Bot`) et cliquez sur **Créer**.
5. Google vous donne un code à **16 lettres** (ex: `abcd efgh ijkl mnop`).
6. Copiez ce code dans `sender_password` dans [`config.json`](file:///c:/Users/tassili/Desktop/Bybit%20Script/config.json) (sans les espaces).

> 💡 *Note : Si vous utilisez Outlook, utilisez `smtp_server: "smtp-mail.outlook.com"`, port `587`.*

---

## 🚀 3. Utilisation

### A. Tester la configuration Email
Pour vérifier que votre email fonctionne sans attendre :
```bash
python bybit_p2p_notifier.py --test-email
```

### B. Voir le prix actuel une seule fois
Pour afficher immédiatement la meilleure offre actuelle du marché :
```bash
python bybit_p2p_notifier.py --once
```

### C. Lancer la surveillance continue
Pour lancer la surveillance en continu (Ctrl+C pour arrêter) :
```bash
python bybit_p2p_notifier.py
```
