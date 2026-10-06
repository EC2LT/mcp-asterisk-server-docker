# agent.py
import asyncio
import getpass
import json
import os
import logging
import sys
from datetime import datetime

import ollama
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from config import settings
from security.auth import login, verify_token, extract_roles

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Tu es un assistant superviseur VoIP expert Asterisk.
Tu disposes d'outils MCP pour consulter et piloter un serveur Asterisk.
Règles :
1. Réponds toujours en français, de manière claire et concise.
2. Utilise les outils MCP dès qu'une information technique ou une action est requise.
3. Synthétise les résultats JSON de manière lisible pour un opérateur humain."""

# Outils critiques (validation humaine obligatoire)
CRITICAL_TOOLS = {"hangup_channel", "make_call", "originate_call", "redirect_call", "spy_channel"}


def authenticate() -> tuple[str, list[str]]:
    """Login Keycloak et retourne (token, roles)."""
    print("=" * 50)
    print("  Authentification Keycloak")
    print("=" * 50)
    username = input("Utilisateur : ").strip()
    password = getpass.getpass("Mot de passe : ")

    tokens = login(username, password)
    token = tokens["access_token"]
    payload = verify_token(token)
    roles = extract_roles(payload)
    print(f"✅ Connecté : {username} (rôles: {roles})\n")
    return token, roles


async def main():
    token, roles = authenticate()

    server_params = StdioServerParameters(
	command=sys.executable,
	args=[os.path.join(os.path.dirname(os.path.abspath(__file__)), "server.py")],
	env={**os.environ, "MCP_AUTH_TOKEN": token},
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            mcp_tools = await session.list_tools()
            ollama_tools = [
                {
                    "type": "function",
                    "function": {
                        "name": t.name,
                        "description": t.description,
                        "parameters": t.inputSchema,
                    },
                }
                for t in mcp_tools.tools
            ]

            print("=" * 50)
            print(f"  Agent Supervision Asterisk (rôles: {roles})")
            print(f"  Outils disponibles : {len(ollama_tools)}")
            print("=" * 50)
            print("Tapez 'exit' pour quitter.\n")

            while True:
                try:
                    user_input = input("Superviseur > ").strip()
                except (EOFError, KeyboardInterrupt):
                    break

                if user_input.lower() in ("exit", "quit"):
                    break
                if not user_input:
                    continue

                response = ollama.chat(
                    model=settings.OLLAMA_MODEL,
                    messages=[
                        {"role": "system", "content": SYSTEM_PROMPT},
                        {"role": "user", "content": user_input},
                    ],
                    tools=ollama_tools,
                )

                msg = response["message"]

                if msg.get("tool_calls"):
                    tool_results = []
                    for call in msg["tool_calls"]:
                        fn_name = call["function"]["name"]
                        fn_args = call["function"].get("arguments", {}) or {}
                        if isinstance(fn_args, str):
                            try:
                                fn_args = json.loads(fn_args)
                            except Exception:
                                fn_args = {}

                        # Validation humaine
                        if fn_name in CRITICAL_TOOLS:
                            confirm = input(
                                f"⚠️  [SÉCURITÉ] Exécuter {fn_name}({fn_args}) ? (o/n) : "
                            )
                            if confirm.lower() not in ("o", "oui", "y"):
                                print("Action annulée.\n")
                                continue

                        print(f"\n[LLM] → {fn_name}({fn_args})")
                        try:
                            res = await session.call_tool(fn_name, arguments=fn_args)
                            if res.content:
                                result_text = getattr(res.content[0], "text", str(res.content[0]))
                            else:
                                result_text = "[]"
                        except Exception as e:
                            result_text = f"Erreur : {e}"

                        print(f"[Résultat] {result_text[:500]}\n")
                        tool_results.append({"role": "tool", "content": result_text})

                    if tool_results:
                        second = ollama.chat(
                            model=settings.OLLAMA_MODEL,
                            messages=[
                                {"role": "system", "content": SYSTEM_PROMPT},
                                {"role": "user", "content": user_input},
                                msg,
                                *tool_results,
                            ],
                        )
                        print(f"Assistant > {second['message']['content']}\n")
                else:
                    print(f"\nAssistant > {msg.get('content', '')}\n")


if __name__ == "__main__":
    asyncio.run(main())
