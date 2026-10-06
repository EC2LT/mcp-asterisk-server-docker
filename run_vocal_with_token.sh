#!/bin/bash
# run_vocal_with_token.sh
set -e

USERNAME="${1:-alice}"
PASSWORD="${2:-password}"

echo "🔐 Récupération du token pour $USERNAME..."

RESPONSE=$(curl -s -X POST http://keycloak:8090/realms/mcp-asterisk/protocol/openid-connect/token \
  -d "grant_type=password" \
  -d "client_id=mcp-agent" \
  -d "username=$USERNAME" \
  -d "password=$PASSWORD")

ACCESS_TOKEN=$(echo "$RESPONSE" | jq -r .access_token)
REFRESH_TOKEN=$(echo "$RESPONSE" | jq -r .refresh_token)

if [ "$ACCESS_TOKEN" = "null" ] || [ -z "$ACCESS_TOKEN" ]; then
    echo "❌ Échec de récupération du token pour $USERNAME"
    echo "$RESPONSE" | jq .
    exit 1
fi

echo "✅ Access token récupéré (${ACCESS_TOKEN:0:30}...)"
echo "✅ Refresh token récupéré (${REFRESH_TOKEN:0:30}...)"
echo "🎙️  Lancement de l'agent vocal..."

export MCP_AUTH_TOKEN="$ACCESS_TOKEN"
export MCP_REFRESH_TOKEN="$REFRESH_TOKEN"
export MCP_USERNAME="$USERNAME"
export MCP_PASSWORD="$PASSWORD"

exec python3 vocal_agent.py
