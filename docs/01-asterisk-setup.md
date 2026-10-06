# Configuration d'Asterisk pour le projet MCP Asterisk Supervisor

Ce guide explique comment préparer un serveur **Asterisk 22 LTS** pour qu'il puisse être supervisé et piloté via le serveur MCP.

## Prérequis

- **Debian 12 / Ubuntu 22.04+** (ou équivalent)
- **Asterisk 22 LTS** installé
- Accès root (ou sudo)
- Une adresse IP fixe pour le serveur Asterisk

## 1. Configuration ARI (Asterisk REST Interface)

ARI est l'API REST d'Asterisk, utilisée par le serveur MCP pour interroger et piloter le PBX.

Éditez `/etc/asterisk/ari.conf` :

```ini
[general]
enabled = yes
pretty = yes
allowed_origins = *

[mcp_user]
type = user
read_only = no
password = mcp_secret_password
password_format = plain
```

> ⚠️ **Sécurité** : en production, changez le mot de passe et restreignez `allowed_origins` aux IP autorisées.

## 2. Activation du serveur HTTP d'Asterisk

ARI s'appuie sur le serveur web interne d'Asterisk. Éditez `/etc/asterisk/http.conf` :

```ini
[general]
enabled = yes
bindaddr = 0.0.0.0
bindport = 8088
```

> ⚠️ **Important** : `bindaddr = 0.0.0.0` est nécessaire pour que Docker puisse joindre ARI.

## 3. Activation de l'interface AMI (optionnel)

AMI (Asterisk Manager Interface) est utilisée pour certaines fonctions avancées.

Éditez `/etc/asterisk/manager.conf` :

```ini
[general]
enabled = yes
port = 5038
bindaddr = 0.0.0.0

; Compte AMI dédié aux droits restreints (moindre privilège)
[mcp_ami_user]
secret = ami_secret_password
deny = 0.0.0.0/0.0.0.0
permit = 127.0.0.1/255.255.255.255
read = system,call,log,verbose,command,agent,user,config
write = system,call,command,agent,user
```

## 4. Chargement des modules ARI

Éditez `/etc/asterisk/modules.conf` et ajoutez :

```ini
load => res_http_websocket.so
load => res_ari.so
load => res_ari_applications.so
load => res_ari_asterisk.so
load => res_ari_channels.so
load => res_ari_endpoints.so
load => res_ari_events.so
```

## 5. Configuration du dialplan (extensions.conf)

Ajoutez ces 2 extensions dans `/etc/asterisk/extensions.conf` (contexte `default`) :

```ini
; Extension 9000 : test Stasis simple
exten => 9000,1,NoOp(Appel vers application Stasis MCP)
 same => n,Answer()
 same => n,Stasis(app_mcp)
 same => n,Hangup()

; Extension 2000 : superviseur IA vocal
exten => 2000,1,NoOp(Appel vers le Superviseur IA Vocal)
 same => n,Answer()
 same => n,Stasis(asterisk-vocal-ai)
 same => n,Hangup()
```

> ⚠️ Le nom de l'application Stasis `asterisk-vocal-ai` doit correspondre à la variable `ASTERISK_ARI_APP` dans le `.env` du projet.

## 6. Rechargement et vérification

```bash
# Recharger la configuration
sudo asterisk -rx "core reload"

# Vérifier ARI
sudo asterisk -rx "ari show status"

# Vérifier les modules
sudo asterisk -rx "module show like res_ari"

# Vérifier le dialplan
sudo asterisk -rx "dialplan show 2000@default"
```

## 7. Test de l'accès ARI depuis l'extérieur

Depuis une autre machine (ou depuis Docker), testez :

```bash
curl -u mcp_user:mcp_secret_password http://<IP_ASTERISK>:8088/ari/asterisk/info | jq .
```

Vous devez voir un JSON avec les infos d'Asterisk.

## 8. Firewall (si nécessaire)

Ouvrez les ports suivants :

```bash
sudo ufw allow 5060/udp              # SIP
sudo ufw allow 8088/tcp              # ARI (HTTP)
sudo ufw allow 5038/tcp              # AMI (si utilisé)
sudo ufw allow 10000:20000/udp       # RTP
```

## 9. Installation de Piper (voix française)

Pour le pipeline vocal S2S, téléchargez la voix française Piper :

```bash
cd ~/mcp-asterisk-server/models

wget https://huggingface.co/rhasspy/piper-voices/resolve/main/fr/fr_FR/siwis/medium/fr_FR-siwis-medium.onnx
wget https://huggingface.co/rhasspy/piper-voices/resolve/main/fr/fr_FR/siwis/medium/fr_FR-siwis-medium.onnx.json
```

> ⚠️ Piper génère par défaut un WAV à 22050 Hz. Le pipeline vocal le convertit automatiquement en 8000 Hz mono (format Asterisk) via `ffmpeg`.

## 10. Résumé des fichiers modifiés

| Fichier | Modification |
|---|---|
| `/etc/asterisk/http.conf` | Activation du serveur HTTP sur le port 8088 |
| `/etc/asterisk/ari.conf` | Compte `mcp_user` pour ARI |
| `/etc/asterisk/manager.conf` | Compte `mcp_ami_user` pour AMI |
| `/etc/asterisk/modules.conf` | Chargement des modules `res_ari_*.so` |
| `/etc/asterisk/extensions.conf` | Extensions 9000 (test) et 2000 (vocal) |

## Prochaines étapes

Une fois Asterisk configuré, notez son **adresse IP**. Vous en aurez besoin pour configurer le `.env` du projet Docker.

Retournez au [README principal](../README.md) pour installer le projet.
