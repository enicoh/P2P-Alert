# 🔔 P2P Multi-Exchange Price Alert Notifier (Bybit, Binance, OKX, KuCoin)

Surveillance automatique en temps réel des meilleurs marchés **P2P en Algérie** (**Bybit**, **Binance P2P**, **OKX**, **KuCoin** pour **USDT / DZD**) avec comparateur instantané et notifications par **Telegram** (push mobile avec alerte sonore), **Email** ou **Discord**.

Le projet inclut un **serveur web cloud avec tableau de bord en direct** (`app_cloud.py`) affichant la comparaison des prix entre chaque plateforme, prêt à être déployé gratuitement 24h/24 et 7j/7 sur **Render**, sans jamais s'interrompre grâce à un système keep-alive **UptimeRobot**.

---

## 📑 Sommaire
1. [⚡ Fonctionnalités Clés](#-fonctionnalités-clés)
2. [🌐 Choix des Plateformes (Bybit, Binance, OKX, KuCoin)](#-choix-des-plateformes)
3. [📱 1. Configuration des Notifications Telegram](#-1-configuration-des-notifications-telegram-recommandé)
4. [☁️ 2. Déploiement Cloud 24/7 sur Render](#-2-déploiement-cloud-247-sur-render-gratuit)
5. [⏱️ 3. Empêcher Render de Dormir (Keep-Alive 24/7 avec UptimeRobot)](#-3-empêcher-render-de-dormir-keep-alive-247-avec-uptimerobot)
6. [⚙️ 4. Paramètres de Configuration (`config.json`)](#-4-paramètres-de-configuration-configjson)
7. [📧 5. Configuration Email (Optionnel - Gmail)](#-5-configuration-email-optionnel---gmail)
8. [💻 6. Utilisation Locale (Windows / Mac / Linux)](#-6-utilisation-locale-windows--mac--linux)
9. [🛡️ 7. Filtre d'Éligibilité Acheteur](#-7-filtre-déligibilité-acheteur)
10. [❓ 8. FAQ & Dépannage](#-8-faq--dépannage)

---

## ⚡ Fonctionnalités Clés

- **Agrégateur Multi-Plateformes** : Interroge en parallèle **Binance P2P**, **Bybit**, **OKX** et **KuCoin** pour trouver automatiquement la plateforme la moins chère.
- **Sélection Simple & Flexible** : Choisissez une seule plateforme (`"binance"` ou `"bybit"` ou `"okx"`) ou comparez-les toutes à la fois (`"all"`).
- **Notifications Multi-Canaux** : Alerte instantanée sur smartphone via **Telegram Bot**, webhook **Discord** ou **Email HTML** avec badge de la plateforme gagnante.
- **Filtre Intelligent du Budget** : Vérifie que le vendeur accepte bien votre montant d'achat (ex: entre 2 000 DA et 13 000 DA) en analysant ses limites minimales et maximales.
- **Filtre d'Éligibilité Acheteur** : Écarte automatiquement les marchands qui imposent des conditions bloquantes pour les petits acheteurs (ex: marchands exigeant plus de 5, 10 ou 60 ordres sur 30 jours).
- **Tableau de Bord Web en Direct (`app_cloud.py`)** : Interface sombre moderne avec comparateur en temps réel des prix Bybit / Binance / OKX / KuCoin et historique des alertes.
- **Anti-Spam (Cooldown)** : Évite de vous submerger de notifications pour la même offre (intervalle configurable, ex: 15 minutes).
- **Zéro Dépendance Lourde** : Fonctionne avec la bibliothèque standard Python (`urllib`, `smtplib`, `json`, `http.server`, `concurrent.futures`).

---

## 🌐 Choix des Plateformes

Dans votre fichier [`config.json`](config.json), vous pouvez choisir les plateformes à surveiller en toute simplicité :

```json
// Option 1 : Surveiller toutes les plateformes pour avoir le meilleur prix absolu (Recommandé)
"platforms": ["bybit", "binance", "okx", "kucoin"]

// Option 2 : Surveiller uniquement Binance P2P
"platforms": ["binance"]

// Option 3 : Surveiller uniquement Bybit
"platforms": ["bybit"]

// Option 4 : Surveiller Binance + Bybit
"platforms": ["binance", "bybit"]
```
*(Vous pouvez aussi utiliser le mot-clé `"platform": "all"` ou `"platform": "binance"`).*


---

## 📱 1. Configuration des Notifications Telegram (Recommandé)

Telegram est la solution idéale : **gratuite, instantanée, avec notification sonore sur votre smartphone**, et parfaitement compatible avec le Cloud (contrairement aux emails SMTP souvent bloqués par les hébergeurs gratuits).

### Étape 1 : Créer votre Bot Telegram
1. Ouvrez l'application Telegram et cherchez **[@BotFather](https://t.me/BotFather)** (compte officiel certifié).
2. Cliquez sur **Démarrer** et envoyez la commande :
   ```text
   /newbot
   ```
3. Donnez un nom d'affichage à votre bot (ex: `Bybit Alert DZD`).
4. Donnez un nom d'utilisateur unique se terminant par `bot` (ex: `MonAlerteBybit_bot`).
5. BotFather vous répond en affichant votre **API Token** :
   ```text
   7123456789:ABCDefgh-123456789xyz_tokenExemple
   ```
   > ⚠️ **Conservez précieusement ce Token**, il représente la clé d'accès de votre bot.

### Étape 2 : Activer votre Bot (Action obligatoire !)
> [!IMPORTANT]
> Par sécurité, un bot Telegram n'a pas le droit d'envoyer un message à un utilisateur sans son autorisation préalable.

1. Cliquez sur le lien de votre bot fourni par BotFather (ex: `t.me/MonAlerteBybit_bot`).
2. Cliquez impérativement sur le bouton **DÉMARRER** (ou envoyez `/start`).

### Étape 3 : Récupérer votre Chat ID
1. Dans Telegram, cherchez le bot **[@userinfobot](https://t.me/userinfobot)** (ou **[@raw_data_bot](https://t.me/raw_data_bot)**).
2. Cliquez sur **Démarrer** (`/start`).
3. Le bot vous répond avec votre profil. Copiez le numéro indiqué dans le champ **Id** (ex: `5850428919`).

### Étape 4 : Configurer vos identifiants
Vous pouvez renseigner ces deux identifiants :
- **Soit dans `config.json`** (usage local) :
  ```json
  "telegram": {
    "enabled": true,
    "bot_token": "7123456789:ABCDefgh-123456789xyz_tokenExemple",
    "chat_id": "5850428919"
  }
  ```
- **Soit dans les Variables d'Environnement** (déploiement Render) :
  - `TELEGRAM_BOT_TOKEN` = `7123456789:ABCDefgh-123456789xyz_tokenExemple`
  - `TELEGRAM_CHAT_ID` = `5850428919`
  - `TELEGRAM_ENABLED` = `true`

### Étape 5 : Tester la notification
Lancez la commande de test :
```bash
python bybit_p2p_notifier.py --test-telegram
```
Vous recevrez immédiatement une alerte de test sur Telegram avec un aperçu complet du format du message.

---

## ☁️ 2. Déploiement Cloud 24/7 sur Render (Gratuit)

Render permet d'héberger gratuitement l'application en continu. Le script exécutera `app_cloud.py`, qui lance la surveillance Bybit en arrière-plan et fournit un tableau de bord HTTP.

### Étape 1 : Mettre votre projet sur GitHub
Assurez-vous que votre projet est publié sur votre compte GitHub (ex: dépôt privé ou public `bybit-p2p-alert`).

### Étape 2 : Créer un Web Service sur Render
1. Rendez-vous sur [render.com](https://render.com) et connectez-vous (avec votre compte GitHub).
2. Dans le tableau de bord Render, cliquez sur le bouton bleu **New +** (en haut à droite), puis sélectionnez **Web Service**.
3. Choisissez l'option **Build and deploy from a Git repository**.
4. Associez votre compte GitHub et sélectionnez votre dépôt `bybit-p2p-alert` (cliquez sur **Connect**).

### Étape 3 : Remplir la configuration du service
Renseignez les champs suivants :

| Champ | Valeur recommandée |
| :--- | :--- |
| **Name** | `bybit-p2p-alert` |
| **Region** | `Frankfurt (EU Central)` *(ou la région la plus proche de vous)* |
| **Branch** | `main` |
| **Root Directory** | *(laisser vide)* |
| **Runtime** | `Python 3` |
| **Build Command** | `pip install -r requirements.txt` |
| **Start Command** | `python -u app_cloud.py` |
| **Instance Type** | `Free` (0 $/mois) |

### Étape 4 : Définir les Variables d'Environnement
Dans la section **Environment Variables** (ou en cliquant sur *Advanced* -> *Add Environment Variable*), ajoutez vos paramètres :

| Variable | Exemple de valeur | Description |
| :--- | :--- | :--- |
| `TELEGRAM_BOT_TOKEN` | `7123456789:ABCDef...` | Votre Token BotFather |
| `TELEGRAM_CHAT_ID` | `5850428919` | Votre Chat ID personnel |
| `TELEGRAM_ENABLED` | `true` | Active les alertes Telegram |
| `TARGET_MIN_PRICE` | `200.0` | Prix minimum recherché (DZD) |
| `TARGET_MAX_PRICE` | `255.0` | Prix maximum recherché (DZD) |
| `MIN_AMOUNT_DZD` | `2000.0` | Montant d'achat minimum en DZD |
| `MAX_AMOUNT_DZD` | `13000.0` | Montant d'achat maximum en DZD |
| `CHECK_INTERVAL_SECONDS` | `30` | Intervalle de vérification Bybit (secondes) |
| `NOTIFICATION_COOLDOWN_MINUTES` | `15` | Temps de pause avant de ré-alerter la même annonce |

> 💡 *Note : Si vous ne définissez pas ces variables, le script utilisera automatiquement les valeurs par défaut de votre fichier [`config.json`](config.json).*

### Étape 5 : Lancer le déploiement
1. Cliquez sur **Deploy Web Service** (ou **Create Web Service**).
2. Render installe les dépendances et démarre le serveur.
3. Dès que le statut affiche **Live**, cliquez sur l'URL générée par Render (ex: `https://bybit-p2p-alert.onrender.com`).
4. Vous accédez au tableau de bord en temps réel qui affiche l'état de surveillance, le dernier prix Bybit compatible et l'historique des alertes !

---

## ⏱️ 3. Empêcher Render de Dormir (Keep-Alive 24/7 avec UptimeRobot)

> [!WARNING]
> **Pourquoi cette étape est indispensable ?**  
> Sur le forfait gratuit de Render, les Web Services s'endorment automatiquement (**Spin down**) après **15 minutes d'inactivité** sans visiteur HTTP. Lorsqu'il s'endort, le bot arrête de surveiller les prix Bybit !

Pour garder votre bot actif 24h/24 et 7j/7 sans payer, il suffit d'utiliser un service externe gratuit qui envoie une requête HTTP à votre URL Render toutes les 5 à 10 minutes.

### Méthode 1 : UptimeRobot (Recommandé & 100% Gratuit)

1. Rendez-vous sur [uptimerobot.com](https://uptimerobot.com) et créez un compte gratuit.
2. Dans votre tableau de bord, cliquez sur **+ Add New Monitor**.
3. Remplissez les champs comme suit :
   - **Monitor Type** : Choisissez **`HTTP(s)`**.
   - **Friendly Name** : `Bybit P2P Keep-Alive` (nom libre).
   - **URL (or IP)** : Collez l'URL complète de votre Web Service Render (ex: `https://bybit-p2p-alert.onrender.com`).
   - **Monitoring Interval** : Sélectionnez **`5 minutes`** (ou `10 minutes`, impérativement inférieur à 15 minutes).
   - **Monitor Timeout** : `30 seconds`.
4. Cliquez sur **Create Monitor**.

🎉 **Résultat :** UptimeRobot visite automatiquement votre dashboard toutes les 5 minutes. Render ne s'endormira jamais et votre bot fonctionnera **en continu 24h/24**.

---

### Méthode 2 : Cron-job.org (Alternative Gratuite)

Si vous préférez une alternative à UptimeRobot :
1. Créez un compte gratuit sur [cron-job.org](https://cron-job.org).
2. Cliquez sur **Create cronjob**.
3. Renseignez :
   - **Title** : `Bybit Keep Alive`
   - **URL** : `https://bybit-p2p-alert.onrender.com`
   - **Execution schedule** : `Every 5 minutes` (Toutes les 5 minutes).
4. Cliquez sur **Create**.

---

## ⚙️ 4. Paramètres de Configuration (`config.json`)

Le fichier [`config.json`](config.json) permet de définir vos critères d'achat et vos alertes :

```json
{
  "platforms": ["bybit", "binance", "okx", "kucoin"],
  "target_min_price": 200.0,
  "target_max_price": 255.0,
  "min_amount_dzd": 2000.0,
  "max_amount_dzd": 13000.0,
  "token_id": "USDT",
  "currency_id": "DZD",
  "check_interval_seconds": 30,
  "notification_cooldown_minutes": 15,
  "buyer_profile": {
    "filter_eligible_only": true,
    "completed_orders_30d": 0,
    "has_kyc": true,
    "account_age_days": 90,
    "nationality": "DZA"
  },
  "telegram": {
    "enabled": true,
    "bot_token": "VOTRE_TOKEN_BOT_ICI",
    "chat_id": "VOTRE_CHAT_ID_ICI"
  },
  "discord": {
    "enabled": false,
    "webhook_url": ""
  },
  "email": {
    "enabled": false,
    "smtp_server": "smtp.gmail.com",
    "smtp_port": 587,
    "use_tls": true,
    "sender_email": "votre_email@gmail.com",
    "sender_password": "votre_mot_de_passe_application",
    "receiver_email": "votre_email@gmail.com"
  }
}
```

### Détail des options :

- `target_min_price` : Prix unitaire minimum pour déclencher l'alerte (ex: `200.0` DZD).
- `target_max_price` : Prix unitaire maximum acceptable (ex: `255.0` DZD). L'alerte sonne si une offre se trouve entre ces deux prix.
- `min_amount_dzd` : Montant minimum de votre budget d'achat en Dinars (ex: `2000.0` DA).
- `max_amount_dzd` : Montant maximum de votre budget d'achat en Dinars (ex: `13000.0` DA).
- `check_interval_seconds` : Intervalle de vérification des prix en secondes (ex: `30` secondes).
- `notification_cooldown_minutes` : Temps d'attente (en minutes) avant de ré-émettre une alerte pour la même annonce afin d'éviter le spam.

---

## 📧 5. Configuration Email (Optionnel - Gmail)

Si vous souhaitez également recevoir des emails en local :

1. Rendez-vous sur votre compte Google : [Sécurité Google](https://myaccount.google.com/security).
2. Activez la **Validation en deux étapes** (2-Step Verification) si ce n'est pas déjà fait.
3. Allez sur [Mots de passe des applications](https://myaccount.google.com/apppasswords).
4. Saisissez un nom d'application (ex: `Bybit Alert`) et cliquez sur **Créer**.
5. Google affiche un code secret à 16 lettres (ex: `abcd efgh ijkl mnop`).
6. Copiez ce code sans espaces dans le champ `sender_password` de `config.json`.
7. Passez `"enabled": true` dans la section `"email"`.

> [!NOTE]
> Sur les hébergeurs Cloud gratuits (Render Free, etc.), les ports d'envoi d'emails sortants SMTP (ports 587 et 465) sont systématiquement bloqués pour éviter le spam. Privilégiez toujours **Telegram** dans le Cloud.

---

## 💻 6. Utilisation Locale (Windows / Mac / Linux)

### A. Tester vos canaux de notification
```bash
# Tester Telegram
python bybit_p2p_notifier.py --test-telegram

# Tester Email
python bybit_p2p_notifier.py --test-email

# Tester tous les canaux activés
python bybit_p2p_notifier.py --test-all
```

### B. Obtenir le meilleur prix actuel une seule fois
```bash
python bybit_p2p_notifier.py --once
```

### C. Lancer la surveillance continue en console
```bash
python bybit_p2p_notifier.py
```
*(Sur Windows, vous pouvez aussi double-cliquer directement sur [`start_notifier.bat`](start_notifier.bat)).*

### D. Lancer le tableau de bord web en local
```bash
python app_cloud.py
```
Puis ouvrez votre navigateur sur [http://localhost:8080](http://localhost:8080).

---

## 🛡️ 7. Filtre d'Éligibilité Acheteur

Sur Bybit P2P, certains marchands imposent des critères stricts aux acheteurs (exigences de 5, 10 ou 60 ordres réussis sur les 30 derniers jours, compte vérifié KYC, ancienneté du compte, nationalité).

Sans ce filtre, vous recevriez des alertes pour des prix attractifs mais sur lesquels vous ne pouvez pas acheter ("*Vous ne remplissez pas les conditions requises par le commerçant*").

Le script analyse le champ `tradingPreferenceSet` de chaque annonce et compare les critères du marchand avec votre profil configuré dans `buyer_profile` :
- `filter_eligible_only` : `true` pour écarter automatiquement toutes les annonces où vous êtes bloqué.
- `completed_orders_30d` : Nombre d'ordres que vous avez finalisés ces 30 derniers jours (laissez à `0` si vous achetez rarement).
- `has_kyc` : `true` si votre compte Bybit a passé la vérification d'identité.
- `account_age_days` : Âge de votre compte Bybit en jours (ex: `90`).
- `nationality` : Code pays de votre compte (ex: `"DZA"` pour l'Algérie).

---

## ❓ 8. FAQ & Dépannage

### 1. Le bot Telegram ne m'envoie aucun message
- Avez-vous cliqué sur **Démarrer** (`/start`) dans la discussion privée avec votre bot ? C'est la cause numéro 1 d'échec de Telegram.
- Votre `chat_id` est-il bien le vôtre ? Vérifiez-le avec [@userinfobot](https://t.me/userinfobot).
- Testez la commande `python bybit_p2p_notifier.py --test-telegram` pour lire le message d'erreur exact.

### 2. Le serveur Render s'arrête ou s'endort
- Avez-vous configuré UptimeRobot ou Cron-job.org ?
- Vérifiez que l'intervalle dans UptimeRobot est de **5 minutes** (et non 30 minutes ou 1 heure).
- Assurez-vous que l'URL renseignée dans UptimeRobot commence bien par `https://` et correspond exactement à celle de votre Render.

### 3. Comment modifier mes prix cibles sans toucher au code ?
- Sur Render, rendez-vous dans l'onglet **Environment** de votre Web Service.
- Modifiez `TARGET_MAX_PRICE` ou `MIN_AMOUNT_DZD`.
- Cliquez sur **Save Changes** : Render rechargera automatiquement vos nouveaux paramètres.