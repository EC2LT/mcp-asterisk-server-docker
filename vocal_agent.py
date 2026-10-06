# vocal_agent.py
import asyncio
import json
import logging
import os
import subprocess
import time
import numpy as np
import aiohttp
import websockets
import ollama
import requests
import sys
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from config import settings
from config.logging_config import setup_logging
from s2s.stt import transcribe
from s2s.tts import synthesize

setup_logging()
logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """Tu es un assistant vocal d'accueil et de supervision en temps réel pour un serveur VoIP Asterisk.
Tes réponses doivent être TRÈS COURTES (maximum 2 phrases) pour être lues au téléphone.
Utilise les outils MCP pour obtenir les VRAIES données avant de répondre."""

TOKEN_FILE = "/tmp/mcp_asterisk_token.json"

# --- État global ---
active_caller_channel_id = None
snoop_bridge_id = None
is_processing = False
audio_buffer = bytearray()
last_speech_time = 0
SILENCE_THRESHOLD = 500
SILENCE_DURATION = 1.2
MAX_AUDIO_DURATION = 5.0

# --- Session MCP ---
mcp_session = None
mcp_tools_schema = []
_mcp_cm_read = None
_mcp_cm_session = None

# --- Tokens ---
_current_access_token = None
_current_refresh_token = None
_token_expires_at = 0


def _load_tokens():
    global _current_access_token, _current_refresh_token
    _current_access_token = os.getenv("MCP_AUTH_TOKEN")
    _current_refresh_token = os.getenv("MCP_REFRESH_TOKEN")


def _write_token_file():
    """Écrit le token dans le fichier partagé avec le serveur MCP."""
    try:
        with open(TOKEN_FILE, "w") as f:
            json.dump({"access_token": _current_access_token}, f)
    except Exception as e:
        logger.error(f"Impossible d'écrire {TOKEN_FILE}: {e}")


def _refresh_access_token():
    """Rafraîchit l'access token avec le refresh token."""
    global _current_access_token, _current_refresh_token, _token_expires_at

    if not _current_refresh_token:
        logger.error("Pas de refresh token disponible.")
        return False

    try:
        resp = requests.post(
            f"{settings.KEYCLOAK_URL}/realms/{settings.KEYCLOAK_REALM}/protocol/openid-connect/token",
            data={
                "grant_type": "refresh_token",
                "client_id": settings.KEYCLOAK_CLIENT_ID,
                "refresh_token": _current_refresh_token,
            },
            timeout=10,
        )
        if resp.status_code != 200:
            logger.error(f"Échec refresh : {resp.status_code} - {resp.text}")
            return False

        data = resp.json()
        _current_access_token = data["access_token"]
        _current_refresh_token = data["refresh_token"]
        _token_expires_at = time.time() + data.get("expires_in", 300) - 30

        _write_token_file()
        os.environ["MCP_AUTH_TOKEN"] = _current_access_token

        logger.info(f"🔄 Token rafraîchi (expire dans {data.get('expires_in', 300)}s)")
        return True
    except Exception as e:
        logger.error(f"Erreur refresh token : {e}")
        return False


def _ensure_valid_token():
    if time.time() >= _token_expires_at:
        logger.info("⏰ Token expiré ou proche de l'expiration, rafraîchissement...")
        _refresh_access_token()


async def init_mcp_session():
    global mcp_session, mcp_tools_schema, _mcp_cm_read, _mcp_cm_session, _token_expires_at

    _load_tokens()
    _token_expires_at = time.time() + 270
    _write_token_file()

    server_params = StdioServerParameters(
	command=sys.executable,  # ← Python actuel (fonctionne partout)
	args=[os.path.join(os.path.dirname(os.path.abspath(__file__)), "server.py")],
	env={**os.environ},
    )

    _mcp_cm_read = stdio_client(server_params)
    read, write = await _mcp_cm_read.__aenter__()

    _mcp_cm_session = ClientSession(read, write)
    mcp_session = await _mcp_cm_session.__aenter__()

    await mcp_session.initialize()

    tools = await mcp_session.list_tools()
    mcp_tools_schema = [
        {
            "type": "function",
            "function": {
                "name": t.name,
                "description": t.description,
                "parameters": t.inputSchema,
            },
        }
        for t in tools.tools
    ]
    logger.info(f"✅ Session MCP : {len(mcp_tools_schema)} outils chargés.")


async def close_mcp_session():
    global mcp_session, _mcp_cm_read, _mcp_cm_session
    try:
        if _mcp_cm_session:
            await _mcp_cm_session.__aexit__(None, None, None)
        if _mcp_cm_read:
            await _mcp_cm_read.__aexit__(None, None, None)
    except Exception as e:
        logger.warning(f"Erreur fermeture MCP : {e}")
    finally:
        mcp_session = None
        _mcp_cm_read = None
        _mcp_cm_session = None


async def call_mcp_tool(tool_name: str, args: dict) -> str:
    if mcp_session is None:
        return "Erreur : session MCP non initialisée."

    # ✅ Rafraîchit le token si nécessaire
    _ensure_valid_token()

    try:
        res = await mcp_session.call_tool(tool_name, arguments=args)
        if res.content:
            return getattr(res.content[0], "text", str(res.content[0]))
        return "[]"
    except Exception as e:
        logger.error(f"Erreur outil MCP {tool_name}: {e}")
        return f"Erreur : {e}"


# --- Listener UDP ---
class AudioUDPListener(asyncio.DatagramProtocol):
    def datagram_received(self, data, addr):
        global audio_buffer, last_speech_time
        if len(data) > 12:
            pcm = data[12:]
            audio_buffer.extend(pcm)
            samples = np.frombuffer(pcm, dtype=">i2")
            if len(samples):
                rms = np.sqrt(np.mean(samples.astype(np.float32) ** 2))
                if rms > SILENCE_THRESHOLD:
                    last_speech_time = time.time()


async def _ollama_chat(messages, tools=None):
    def _run():
        kw = {"model": settings.OLLAMA_MODEL, "messages": messages}
        if tools:
            kw["tools"] = tools
        return ollama.chat(**kw)
    return await asyncio.to_thread(_run)


async def process_audio_and_respond(audio_data: bytes, channel_id: str):
    global is_processing
    is_processing = True

    pcm_in = f"/tmp/in_{channel_id}.raw"
    wav_in = f"/tmp/in_{channel_id}.wav"
    wav_out = f"/tmp/out_{channel_id}.wav"

    try:
        raw = np.frombuffer(audio_data, dtype=">i2")
        if len(raw) == 0:
            return
        amp = np.clip(raw.astype(np.float32) * 2.5, -32768, 32767).astype(np.int16)
        with open(pcm_in, "wb") as f:
            f.write(amp.astype("<i2").tobytes())

        await asyncio.to_thread(
            subprocess.run,
            f"ffmpeg -y -f s16le -ar 16000 -ac 1 -i {pcm_in} {wav_in}",
            shell=True, capture_output=True,
        )

        user_text = await transcribe(wav_in)
        if not user_text:
            logger.info("Aucun texte reconnu.")
            return
        logger.info(f"🎤 Utilisateur : '{user_text}'")

        if active_caller_channel_id != channel_id:
            return

        messages = [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_text},
        ]
        response = await _ollama_chat(messages, tools=mcp_tools_schema)
        msg = response.get("message", {})

        if msg.get("tool_calls"):
            tool_results = []
            for call in msg["tool_calls"]:
                name = call["function"]["name"]
                args = call["function"].get("arguments", {}) or {}
                if isinstance(args, str):
                    try:
                        args = json.loads(args)
                    except Exception:
                        args = {}
                logger.info(f"🛠️ Outil MCP : {name}({args})")
                output = await call_mcp_tool(name, args)
                tool_results.append({"role": "tool", "content": str(output)})

            final = await _ollama_chat(messages + [msg] + tool_results)
            ai_text = final["message"]["content"]
        else:
            ai_text = msg.get("content", "")

        if not ai_text.strip():
            ai_text = "Je n'ai pas compris."
        logger.info(f"🤖 Réponse : '{ai_text}'")

        ok = await synthesize(ai_text, wav_out)
        if not ok:
            logger.error("Échec synthèse TTS.")
            return

        if active_caller_channel_id == channel_id:
            async with aiohttp.ClientSession(
                auth=aiohttp.BasicAuth(settings.ARI_USER, settings.ARI_PASSWORD)
            ) as http:
                async with http.post(
                    f"{settings.ARI_URL}/channels/{channel_id}/play",
                    params={"media": f"sound:{wav_out.replace('.wav', '')}"},
                ) as resp:
                    await resp.read()
            logger.info(f"🔊 Réponse envoyée au canal {channel_id}")

    except Exception as e:
        logger.error(f"Erreur pipeline : {e}", exc_info=True)
    finally:
        is_processing = False
        for f in (pcm_in, wav_in, wav_out):
            if os.path.exists(f):
                try:
                    os.remove(f)
                except Exception:
                    pass


async def audio_stream_monitor():
    global audio_buffer, active_caller_channel_id, is_processing, last_speech_time
    max_bytes = int(32000 * MAX_AUDIO_DURATION)
    min_bytes = 32000 * 1

    while True:
        await asyncio.sleep(0.2)
        if active_caller_channel_id and not is_processing and len(audio_buffer) >= min_bytes:
            silence = time.time() - last_speech_time
            if (last_speech_time > 0 and silence >= SILENCE_DURATION) or len(audio_buffer) >= max_bytes:
                data = bytes(audio_buffer)
                audio_buffer.clear()
                last_speech_time = 0
                asyncio.create_task(process_audio_and_respond(data, active_caller_channel_id))


async def ari_websocket_loop():
    global active_caller_channel_id, snoop_bridge_id, is_processing, audio_buffer

    ws_url = (
        f"{settings.ARI_WS_URL}?api_key={settings.ARI_USER}:{settings.ARI_PASSWORD}"
        f"&app={settings.ARI_APP}"
    )

    async with websockets.connect(ws_url) as ws:
        logger.info(f"Connecté ARI WebSocket (app: {settings.ARI_APP})")

        loop = asyncio.get_running_loop()
        transport, _ = await loop.create_datagram_endpoint(
            AudioUDPListener, local_addr=(settings.UDP_IP, settings.UDP_PORT)
        )
        asyncio.create_task(audio_stream_monitor())

        async with aiohttp.ClientSession(
            auth=aiohttp.BasicAuth(settings.ARI_USER, settings.ARI_PASSWORD)
        ) as http:

            async def post(path, params=None):
                async with http.post(f"{settings.ARI_URL}{path}", params=params) as r:
                    try:
                        return await r.json()
                    except Exception:
                        return {}

            try:
                async for raw in ws:
                    event = json.loads(raw)
                    etype = event.get("type")

                    if etype == "StasisStart":
                        ch = event.get("channel", {})
                        ch_id = ch.get("id")
                        if "UnicastRTP" in ch.get("name", "") or "Snoop" in ch.get("name", ""):
                            continue

                        active_caller_channel_id = ch_id
                        audio_buffer.clear()
                        is_processing = False
                        logger.info(f"📞 Appel entrant : {ch_id}")

                        bridge = await post("/bridges", {"type": "mixing"})
                        snoop_bridge_id = bridge.get("id")

                        snoop = await post(
                            f"/channels/{ch_id}/snoop",
                            {"app": settings.ARI_APP, "spy": "in", "whisper": "none"},
                        )
                        ext = await post(
                            "/channels/externalMedia",
                            {
                                "app": settings.ARI_APP,
                                "external_host": f"{settings.UDP_IP}:{settings.UDP_PORT}",
                                "format": "slin16",
                            },
                        )

                        if snoop.get("id") and ext.get("id") and snoop_bridge_id:
                            await post(
                                f"/bridges/{snoop_bridge_id}/addChannel",
                                {"channel": f"{snoop['id']},{ext['id']}"},
                            )

                        welcome = "Bonjour, je suis votre superviseur vocal Asterisk. Que puis-je faire pour vous ?"
                        welcome_wav = "/tmp/welcome.wav"
                        if await synthesize(welcome, welcome_wav):
                            await post(
                                f"/channels/{ch_id}/play",
                                {"media": "sound:/tmp/welcome"},
                            )

                    elif etype == "StasisEnd":
                        ch = event.get("channel", {})
                        if ch.get("id") == active_caller_channel_id:
                            logger.info("📴 Fin d'appel. Nettoyage.")
                            if snoop_bridge_id:
                                async with http.delete(
                                    f"{settings.ARI_URL}/bridges/{snoop_bridge_id}"
                                ) as r:
                                    await r.read()
                            active_caller_channel_id = None
                            snoop_bridge_id = None
                            audio_buffer.clear()
                            is_processing = False
            finally:
                transport.close()


async def main():
    token = os.getenv("MCP_AUTH_TOKEN")
    if not token:
        logger.error("MCP_AUTH_TOKEN manquant. Lancez via un wrapper authentifié.")
        return

    await init_mcp_session()
    try:
        await ari_websocket_loop()
    finally:
        await close_mcp_session()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Arrêt de l'agent vocal.")
