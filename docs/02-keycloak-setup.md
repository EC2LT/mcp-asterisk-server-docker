# Configuration de Keycloak

Le projet utilise Keycloak 25 pour l'authentification (OIDC/JWT) et le contrôle d'accès basé sur les rôles (RBAC).

## Démarrage automatique

Le `docker-compose.yml` importe automatiquement le realm `mcp-asterisk` au démarrage via le fichier `keycloak/realm-mcp-asterisk.json`.

## Rôles disponibles

| Rôle | Permissions |
|---|---|
| `admin` | Accès complet à tous les outils (lecture, analyse, pilotage) |
| `supervisor` | Lecture, analyse et écoute (Chanspy) — pas de pilotage |
| `operator` | Lecture seule |

## Utilisateurs par défaut

| Utilisateur | Mot de passe | Rôle |
|---|---|---|
| `admin` | `password` | admin |
| `alice` | `password` | supervisor |
| `bob` | `password` | operator |
| `vocal-agent` | `password` | operator (service) |

> ⚠️ **Changez ces mots de passe en production.**

## Accéder à l'interface d'administration

- URL : http://localhost:8090
- Login : `admin` / `admin`

## Créer un nouvel utilisateur ou modifier le mot de passe des utilisateurs existant

1. Ouvrez http://localhost:8090 → **Administration Console**
2. Sélectionnez le realm **`mcp-asterisk`**
3. **Users** → **Create new user**
4. Renseignez le **Username** → **Create**
5. Onglet **Credentials** → **Set password**
   - Password : (nouveau)
   - **Temporary** : **OFF** ⚠️ (sinon le login échouera)
6. Onglet **Role mapping** → **Assign role** → cocher le rôle
7. **Save**
<img width="554" height="184" alt="image" src="https://github.com/user-attachments/assets/5548502a-f14b-42e1-b527-28e04f988abe" />

Désactiver toutes ses options
<img width="554" height="228" alt="image" src="https://github.com/user-attachments/assets/5c0397e4-55d0-4ed0-93cf-c5bd51a772b6" />


## Récupérer un token JWT

```bash
curl -s -X POST http://localhost:8090/realms/mcp-asterisk/protocol/openid-connect/token \
  -d "grant_type=password" \
  -d "client_id=mcp-agent" \
  -d "username=alice" \
  -d "password=password" | jq -r .access_token
```

## Décoder un token pour voir les rôles

```bash
TOKEN=$(curl -s -X POST http://localhost:8090/realms/mcp-asterisk/protocol/openid-connect/token \
  -d "grant_type=password" -d "client_id=mcp-agent" \
  -d "username=alice" -d "password=password" | jq -r .access_token)

echo "$TOKEN" | cut -d'.' -f2 | base64 -d 2>/dev/null | jq .realm_access.roles
```
