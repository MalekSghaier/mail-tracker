# Mail Detector ARS — Correction des points mentionnés

**Destinataire :** khiari Mohamed  
**De :** SGHAIER Malek

**Objet :** Correction des points mentionnés avant de commencer le code


**Projet :** Système de suivi d'ouverture des e-mails et d'alerte desktop pour les employés ARS            
**Statut :** Document de cadrage technique, avant codage — à valider avant exécution

---

## 1. Idée centrale

Chaque e-mail envoyé entre employés ARS est suivi silencieusement (pixel invisible). Si le destinataire ne l'a pas ouvert après un délai défini (48h par défaut), une notification native s'affiche directement sur l'écran de la personne concernée — sans passer par un autre mail, sans navigateur ouvert, sans action de l'utilisateur. L'inscription d'un employé se fait une seule fois (e-mail + mot de passe), vérifiée auprès du serveur mail de l'ARS, puis jamais redemandée.

Deux briques logicielles distinctes :
- **Backend** : reçoit les pixels, stocke les e-mails suivis, vérifie les 48h, expose une API d'alertes.
- **Agent desktop** ("front") : tourne en arrière-plan sur le poste de chaque employé, gère la connexion unique, interroge le backend, affiche les popups.

---

## 2. Stack technique recommandée

| Composant | Choix | Justification |
|---|---|---|
| Backend API | **Python + FastAPI** | Async natif (utile pour le pixel à fort volume potentiel), validation automatique via Pydantic, plus robuste que Flask pour une mise en prod |
| Base de données | **PostgreSQL** | gère bien la concurrence, les index, et `INTERVAL` pour la logique 48h |
| ORM / migrations | **SQLAlchemy + Alembic** | Standard FastAPI, migrations versionnées propres |
| Vérification des mails non ouverts (48h) | **Celery Beat** (même Redis que le résumé IA) | Réutilise l'infrastructure déjà nécessaire pour l'IA — évite de faire tourner deux systèmes de scheduling séparés |
| Génération du résumé IA (par mail, à l'envoi) | **Celery + Redis** |Appel externe lent, doit être asynchrone, retry nécessaire |
| Modèle de résumé IA | **Ollama + Mistral 7B (local)** | Aucune donnée ne quitte l'infrastructure — répond à la confidentialité requise pour des documents de réassurance/assurance |
| Confidentialité résumé IA | **Décision actée : modèle local, aucun appel cloud externe** | Évite l'exposition de documents de réassurance/assurance à un tiers |
| Vérification identité employé | **Module interchangeable IMAP / OAuth2** | Décision technique interne (voir la partie 7 ci dessous ) — ne dépend pas de l'ARS, juste de ce que leur serveur autorise |
| Agent desktop | **C# / .NET (WinForms + NotifyIcon + Windows Toast Notifications)** | Parc 100% Windows confirmé → intégration native, binaire léger et signé, bien moins susceptible d'être bloqué par un antivirus/EDR qu'un `.exe` Python packagé |
| Stockage local agent | Fichier local chiffré via **DPAPI** (Data Protection API Windows) — flag "déjà inscrit" + identifiant employé | Aucun mot de passe stocké, jamais ; DPAPI lie le chiffrement au compte Windows de l'utilisateur |

---

## 3. Fonctionnalités MVP 

-  Injection d'un pixel de suivi unique par e-mail envoyé
-  Détection d'ouverture via requête HTTP sur le pixel
-  Vérification périodique des e-mails non ouverts après le délai seuil (48h, logique à trancher : continu ou ouvré — voir questions client)
-  Notification desktop native (pas web, pas dépendante d'un navigateur ou d'une session active), avec option sonore
-  Résumé court du message + expéditeur + destinataire affichés dans la notification
-  Inscription unique de l'employé (e-mail + mot de passe), vérifiée une seule fois, jamais réutilisée
-  Aucune ressaisie ultérieure (état "déjà connecté" mémorisé localement)
-  Alerte envoyée à l'expéditeur, au destinataire, ou aux deux — **à trancher avec l'ARS**
-  Couverture interne ET externe (déjà décrit comme tel dans le document Word — **à confirmer définitivement avec l'ARS avant développement**)
-  Répétition de l'alerte ou notification unique — **à trancher avec l'ARS**


---

## 4. Arborescence Backend (sans code, structure uniquement)

```
mail-detector-backend/
┣ 📂app
┃ ┣ 📂api
┃ ┃ ┣ 📜tracking.py          # GET /track/{tracking_id} — réception du pixel (rate-limiting via middleware, ex. slowapi ) 
┃ ┃ ┣ 📜emails.py            # POST /api/emails/register — reçoit {sender, recipient, subject,body, tracking_id, sent_at} depuis le relais/
┃ ┃ ┣                         milter à l'ENVOI
┃ ┃ ┣ 📜alerts.py            # GET /api/alerts + POST /api/alerts/{id}/ack — l'agent confirme l'affichage
┃ ┃ ┣ 📜registration.py      # POST /api/register — vérification identité (IMAP/OAuth2)
┃ ┃ ┣ 📜health.py            # GET /api/health — vérifie que le backend et la connexion DB répondent
┃ ┃ ┗ 📜__init__.py
┃ ┣ 📂core
┃ ┃ ┣ 📜config.py            # variables d'environnement, secrets
┃ ┃ ┣ 📜database.py          # connexion PostgreSQL
┃ ┃ ┣ 📜security.py          # génère un token opaque longue durée, vérifie le Bearer token à chaque requête
┃ ┃ ┗ 📜__init__.py
┃ ┣ 📂models
┃ ┃ ┣ 📜email_log.py         # table des e-mails suivis (inclut alert_acked: bool)
┃ ┃ ┣ 📜employee.py          # table des employés inscrits ("abonnés")
┃ ┃ ┗ 📜__init__.py
┃ ┣ 📂schemas
┃ ┃ ┣ 📜email_log.py
┃ ┃ ┣ 📜alert.py
┃ ┃ ┗ 📜__init__.py
┃ ┣ 📂services
┃ ┃ ┣ 📜email_registrar.py   # logique d'enregistrement à l'envoi + génération tracking_id
┃ ┃ ┣ 📜pixel_tracker.py     # logique de mise à jour opened_at — ignore les déclenchements dans les 5 sec après sent_at (filtrage anti-scanner basique)
┃ ┃ ┣ 📜threshold_checker.py # logique du seuil 48h (continu vs ouvré)
┃ ┃ ┣ 📜identity_verifier.py # interface commune IMAP / OAuth2 (interchangeable)
┃ ┃ ┗ 📜__init__.py
┃ ┣ 📂workers
┃ ┃ ┣ 📜scheduler.py         # tâche périodique Celery Beat (check 48h, même broker que le résumé IA)
┃ ┃ ┗ 📜__init__.py
┃ ┣ 📜main.py
┃ ┗ 📜__init__.py
┣ 📂alembic
┣ 📂tests
┣ 📜.env.example
┣ 📜docker-compose.yml
┣ 📜Dockerfile
┗ 📜requirements.txt
```

---

## 5. Arborescence Agent Desktop ("front") — C# / .NET (WinForms)

```
MailDetectorAgent/
┣ 📂Agent
┃ ┣ 📂UI
┃ ┃ ┣ 📜LoginForm.cs          # affichée une seule fois, à l'installation
┃ ┃ ┣ 📜TrayIcon.cs           # icône discrète dans la barre des tâches (NotifyIcon)
┃ ┃ ┗ 📜Notifier.cs           # Toast Notification Windows + son optionnel
┃ ┣ 📂Core
┃ ┃ ┣ 📜AppConfig.cs
┃ ┃ ┣ 📜LocalStorage.cs       # flag "déjà inscrit", chiffré via DPAPI — aucun mot de passe stocké
┃ ┃ ┗ 📜ApiClient.cs          # communication HTTP avec le backend
┃ ┣ 📂Services
┃ ┃ ┗ 📜Poller.cs             # interroge /api/alerts (Timer) + appelle POST /api/alerts/{id}/ack après affichage
┃ ┣ 📜Program.cs              # point d'entrée, démarrage avec Windows
┃ ┗ 📜MailDetectorAgent.csproj
┣ 📂Installer                 # script MSI / Inno Setup — réutilisé pour l'installation ET les mises à jour via déploiement centralisé ARS
┗ 📜README.md
```

---

## 6. Flux global (ASCII)

```
╔═══════════════════════════════════════════════════════════════════╗
║  EMPLOYÉ A envoie un mail à EMPLOYÉ B (client mail habituel)      ║
╚════════════════════════════╦══════════════════════════════════════╝
                             ║ (relais SMTP / milter / transport agent — selon serveur ARS)
╔════════════════════════════╩══════════════════════════════════════╗
║  POST /api/emails/register → email_log créé, tracking_id généré   ║
╚════════════════════════════╦══════════════════════════════════════╝
                             ▼
╔═══════════════════════════════════════════════════════════════════╗
║  PIXEL DE SUIVI injecté dans le mail avec ce tracking_id          ║
╚════════════════════════════╦══════════════════════════════════════╝
                             ▼
╔═══════════════════════════════════════════════════════════════════╗
║  B ouvre (ou non) le mail → pixel chargé ou non                   ║
║  → requête HTTP captée par api/tracking.py → opened_at mis à jour ║
╚════════════════════════════╦══════════════════════════════════════╝
                             ▼
╔═══════════════════════════════════════════════════════════════════╗
║  workers/scheduler.py (tâche Celery Beat) vérifie périodiquement :║
║  e-mails non ouverts depuis > seuil (48h) → alerte créée          ║
╚════════════════════════════╦══════════════════════════════════════╝
                             ▼
╔═══════════════════════════════════════════════════════════════════╗
║  AGENT DESKTOP C#/.NET (Poller.cs) interroge /api/alerts          ║
║  → Notifier.cs affiche le Toast Notification + résumé + son       ║
╚════════════════════════════╦══════════════════════════════════════╝
                             ▼
╔═══════════════════════════════════════════════════════════════════╗
║  Poller.cs appelle POST /api/alerts/{id}/ack                      ║
║  → alert_acked = true → cette alerte ne sera plus jamais renvoyée ║
╚═══════════════════════════════════════════════════════════════════╝
```

---

## 7. Roadmap par phases

```
┌─────────────────────────────────────────────────────────────────────────┐
│ PHASE 0 — Backend core (sans dépendance ARS)                            │
│   • Schéma Postgres, API tracking, API alerts, scheduler 48h            │
│   • Tests via Mailtrap (pas besoin du vrai SMTP ARS)                    │
│   • NON BLOQUANT — peut démarrer immédiatement                          │
├─────────────────────────────────────────────────────────────────────────┤
│ PHASE 1 — Agent desktop MVP (C#/.NET)                                   │
│   • LoginForm unique, TrayIcon, Toast Notification + son                │
│   • Stockage local chiffré DPAPI du flag "déjà inscrit"                 │
│   • NON BLOQUANT — développement indépendant, en parallèle de Phase 0   │
├─────────────────────────────────────────────────────────────────────────┤
│ PHASE 2 — Vérification d'identité réelle (IMAP ou OAuth2)               │
│   • Implémentation du module selon ce que supporte l'ARS                │
│   • 🔴 BLOQUANT — dépend de la confirmation ARS (IMAP actif ou non,    │
│     fournisseur de messagerie utilisé)                                  │
├─────────────────────────────────────────────────────────────────────────┤
│ PHASE 3 — Injection pixel à l'échelle réelle                            │
│   • Configuration de la règle de transport sur le serveur mail          │
│   • 🔴 BLOQUANT — nécessite accès admin Exchange/Zimbra/Postfix ARS     │
├─────────────────────────────────────────────────────────────────────────┤
│ PHASE 4 — Fiabilité de la délivrabilité (DKIM/SPF)                      │
│   • Vérification/configuration DKIM-SPF du domaine ARS                  │
│   • 🔴 BLOQUANT — sans ça, risque de classement spam des mails          │
├─────────────────────────────────────────────────────────────────────────┤
│ PHASE 5 — Intégration réelle + tests end-to-end                         │
│   • Bascule de Mailtrap vers le vrai SMTP ARS                           │
│   • Validation du cycle complet sur quelques comptes pilotes            │
──────────────────────────────────────────────────────────────────────────
```

---

## 8. Récapitulatif des points bloquants

| # | Point bloquant | Pourquoi ça bloque |
|---|---|---|
| 1 | Authentification IMAP activée ou non sur le serveur ARS | Détermine la méthode de vérification d'identité à l'inscription |
| 2.a | Logiciel de messagerie utilisé (Exchange/Zimbra/Postfix/autre) | Détermine quel composant développer pour l'enregistrement à l'envoi : milter (Postfix/Zimbra), Transport Agent (Exchange on-premise), ou relais SMTP dédié (Exchange Online) |
| 2.b | Mécanisme d'interception SMTP disponible et droits associés | Sans lui, POST /api/emails/register n'est jamais appelé — aucun mail n'est enregistré avant son ouverture, et le système ne fonctionne pas du tout |
| 3 | Accès admin au serveur mail | Sans lui, le pixel ne peut être injecté à l'échelle de tous les employés |
| 4 | Configuration DKIM/SPF du domaine | Sans elle, les mails de test/alerte risquent d'être classés spam |
| 5.a | Délai : calcul en continu (jours/nuits/week-ends inclus) ou en heures ouvrées uniquement | Change directement la logique de threshold_checker.py |
| 5.b | Délai : valeur fixe pour toute l'ARS, ou paramétrable (par employé ? par service ? par type de mail ?) | Change la structure de la table de configuration et l'interface d'administration éventuelle |
| 6 | Destinataire de l'alerte (expéditeur, destinataire, ou les deux) | Change la logique de `alerts.py` et du popup |
| 7 | Infrastructure disponible pour héberger Ollama/Mistral (CPU/RAM suffisants, GPU optionnel) | Sans serveur dimensionné pour le modèle local, le résumé IA ne peut pas tourner |
| 8 | Conformité loi 63-2004 (durée de conservation, accès aux données, information des employés) | Sans cadrage légal, le système pourrait être non conforme à la protection des données personnelles en Tunisie |
| 9 | Infrastructure de déploiement disponible (serveur existant, nouvelle VM, cloud autorisé ou non) |
| 10 | Supervision managériale (vue agrégée des mails non ouverts) : périmètre MVP ou post-MVP ? | Détermine si un endpoint de reporting + un rôle admin doivent être ajoutés au schéma dès cette version |
| 11 | Outil de déploiement centralisé disponible côté ARS pour pousser les mises à jour de l'agent |
| 12 | Certificat HTTPS disponible pour le backend (Let's Encrypt ou certificat ARS existant) | Sans HTTPS, les tokens Bearer circulent en clair sur le réseau — faille de sécurité critique |
| 13 | Annuaire des employés (liste e-mail + nom) — optionnel mais facilite les tests et l'affichage nom/prénom dans les popups | Sans lui, les popups afficheront l'adresse e-mail brute plutôt que le nom complet |

---

## 9. Limitations connues

| Client mail | Comportement | Impact sur la détection |
|---|---|---|
| Outlook (paramètres par défaut) | Bloque le chargement des images externes | Le mail peut sembler "jamais ouvert" même s'il a été lu |
| Gmail | Précharge les images via son propre serveur proxy | Détection possible même sans ouverture réelle, ou ouvertures multiples comptées comme une seule |
| Antivirus / filtres anti-spam | Pré-vérifient automatiquement les liens d'un mail dès réception | Peut déclencher une fausse détection d'ouverture |

**Ces limitations sont inhérentes au mécanisme du pixel de suivi et ne dépendent pas de la qualité d'implémentation.** Elles doivent être communiquées explicitement à l'ARS avant la mise en production, pour éviter une perception erronée de système peu fiable.


---

## 10. Schéma de base de données (MVP)

### Table `email_log`

| Colonne | Type | Description |
|---|---|---|
| tracking_id | UUID (PK) | Identifiant unique du pixel, généré à l'enregistrement |
| sender_email | string | Adresse de l'expéditeur |
| recipient_email | string | Adresse du destinataire |
| subject | string | Objet du mail |
| body | text | Corps du mail, reçu à l'enregistrement (sert au résumé IA) |
| ai_summary | text, nullable | Résumé généré par Ollama/Mistral, rempli après coup par le worker Celery |
| sent_at | timestamp | Date/heure d'envoi |
| opened_at | timestamp, nullable | Date/heure d'ouverture détectée via le pixel — NULL si jamais ouvert |
| alert_created_at | timestamp, nullable | Date/heure à laquelle l'alerte 48h a été générée |
| alert_acked | boolean, default false | Passe à true quand l'agent confirme avoir affiché le popup |

### Table `employee`

| Colonne | Type | Description |
|---|---|---|
| id | UUID/serial (PK) | Identifiant interne |
| email | string, unique | Adresse e-mail ARS de l'employé |
| token_hash | string | Hash du token (jamais stocké en clair, comme un mot de passe) |
| revoked | boolean, default false | Passe à true pour invalider l'accès d'un employé (ex. départ de l'ARS) |
| registered_at | timestamp | Date de la première inscription (vérification IMAP/OAuth2) |
| last_seen_at | timestamp | Dernier appel reçu de l'agent (utile pour détecter les agents inactifs) |

---

## 11. Authentification agent ↔ backend

- **Type** : token opaque (chaîne aléatoire de 256 bits), pas de JWT — pas de besoin de vérification décentralisée
- **Génération** : une seule fois, à l'inscription (après succès IMAP/OAuth2), renvoyé à l'agent qui le stocke chiffré via DPAPI
- **Durée de vie** : illimitée par défaut — pas d'expiration automatique
- **Envoi** : header `Authorization: Bearer <token>` sur chaque appel à `/api/alerts` et `/api/alerts/{id}/ack`
- **Stockage côté serveur** : seul le hash du token est stocké (table `employee.token_hash`), jamais le token en clair
- **Révocation** : manuelle, via `employee.revoked = true` (ex. départ d'un employé) — aucun mécanisme de refresh nécessaire
- **Si le token est invalide ou révoqué** : le backend répond `401 Unauthorized` → l'agent réaffiche `LoginForm.cs` pour ré-inscrire l'employé

---

## 12. Conformité et protection des données

- **Durée de conservation des logs** : à définir avec l'ARS — non spécifiée actuellement (ex. purge automatique après 6 mois ?)
- **Accès aux données** : à définir — qui peut consulter `email_log` (admin IT uniquement ? managers ? ARS elle-même via un futur reporting ?)
- **Information des employés** : à confirmer si une notice ou clause du règlement intérieur informe les employés que leurs e-mails font l'objet de ce suivi
- **Cadre légal applicable** : loi organique n° 63-2004 (protection des données à caractère personnel, Tunisie) — à valider avec un conseil juridique côté ARS si nécessaire
- **Charte informatique ARS** : à obtenir (déjà demandée dans le document Word) — peut contraindre l'installation de l'agent sur les postes ou le stockage local des données d'authentification
