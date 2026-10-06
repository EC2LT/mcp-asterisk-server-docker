# MCP Asterisk Supervisor

Système de supervision et de pilotage intelligent d'un serveur **Asterisk 22 LTS** via le **Model Context Protocol (MCP)**, avec support **texte** et **voix** (Speech-to-Speech).

## 🎯 Fonctionnalités

- **Supervision temps réel** : canaux actifs, extensions, files d'attente, trunks
- **Analyse** : historique CDR, qualité RTP (MOS, jitter, packet loss)
- **Pilotage** : initiation, raccrochage, redirection, écoute (Chanspy)
- **Dialogue naturel** : par texte (CLI) ou par voix (téléphone)
- **Sécurité** : Keycloak (OIDC/JWT) + RBAC (admin, supervisor, operator)
- **LLM 100 % local** : Ollama + Qwen 2.5, Whisper, Piper

## 📋 Prérequis

- **Docker** ≥ 24 et **Docker Compose** ≥ 2.20
- Un serveur **Asterisk 22 LTS** installé et configuré (voir [docs/01-asterisk-setup.md](docs/01-asterisk-setup.md))
- **8 Go de RAM minimum** (16 Go recommandés)

## 🚀 Installation

### 1. Préparer Asterisk

Suivez le guide [docs/01-asterisk-setup.md](docs/01-asterisk-setup.md). Notez son **adresse IP**.

### 2. Cloner le dépôt

```bash
git clone https://github.com/<votre-user>/mcp-asterisk-server.git
cd mcp-asterisk-server
```

### 3. Configurer

```bash
cp .env.example .env
nano .env
```

Éditez au minimum :
- `ASTERISK_HOST` : IP ou hostname de votre serveur Asterisk
- `ASTERISK_ARI_PASSWORD` : mot de passe défini dans `ari.conf`
- `HOST_IP` : IP de la machine qui héberge Docker

### 4. Construire les images

```bash
docker compose build
```

> ⏱️ Une seule fois (5-10 min).

### 5. Démarrer

```bash
docker compose up -d
```

### 6. Vérifier

```bash
docker compose ps
```

Attendu :
```
mcp-keycloak      Up (healthy)
mcp-ollama        Up
mcp-vocal-agent   Up
```

### 7. Utiliser

**Agent texte** :
```bash
docker compose exec vocal-agent python3 agent.py
# Login : alice / password
```

**Agent vocal** : composez le **2000** depuis un softphone (Linphone, Zoiper).

## 🔐 Comptes par défaut

| Utilisateur | Mot de passe | Rôle |
|---|---|---|
| `admin` | `password` | admin |
| `alice` | `password` | supervisor |
| `bob` | `password` | operator |
| `vocal-agent` | `password` | operator (service) |

⚠️ **Changez ces mots de passe en production.**

## 🛠️ Commandes utiles

```bash
# Voir les logs
docker compose logs -f vocal-agent

# Redémarrer
docker compose restart vocal-agent

# Arrêter
docker compose down

# Arrêter + supprimer les volumes
docker compose down -v

# Reconstruire après modification du code
docker compose build --no-cache vocal-agent
docker compose up -d
```

## 📚 Documentation

| Document | Description |
|---|---|
| [docs/01-asterisk-setup.md](docs/01-asterisk-setup.md) | Configuration d'Asterisk |
| [docs/02-keycloak-setup.md](docs/02-keycloak-setup.md) | Configuration de Keycloak |
| [docs/03-mcp-server.md](docs/03-mcp-server.md) | Documentation du serveur MCP |
| [docs/04-vocal-agent.md](docs/04-vocal-agent.md) | Documentation de l'agent vocal |

## 🏗️ Architecture

```
┌──────────────┐
│  Asterisk    │ (externe)
│  VoIP PBX    │
└──────┬───────┘
       │ ARI (HTTP/WS)
       │
┌──────▼───────────────────────────────────┐
│  Docker Compose                          │
│                                          │
│  ┌──────────┐  ┌──────────┐              │
│  │ Keycloak │  │  Ollama  │              │
│  │  (OIDC)  │  │  (LLM)   │              │
│  └──────────┘  └──────────┘              │
│                                          │
│  ┌────────────────────┐                  │
│  │   Vocal Agent      │                  │
│  │  (Whisper+Piper)   │                  │
│  └────────────────────┘                  │
└──────────────────────────────────────────┘
```
et MCP Asterisk Supervisor
