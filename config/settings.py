# config/settings.py
import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    # Asterisk (URLs construites depuis ASTERISK_HOST)
    ASTERISK_HOST = os.getenv("ASTERISK_HOST", "localhost")
    ARI_PORT = os.getenv("ASTERISK_ARI_PORT", "8088")
    ARI_URL = os.getenv("ARI_URL", f"http://{ASTERISK_HOST}:{ARI_PORT}/ari")
    ARI_WS_URL = os.getenv("ARI_WS_URL", f"ws://{ASTERISK_HOST}:{ARI_PORT}/ari/events")
    ARI_USER = os.getenv("ARI_USER", "mcp_user")
    ARI_PASSWORD = os.getenv("ARI_PASSWORD", "mcp_secret_password")
    ARI_APP = os.getenv("ARI_APP", "asterisk-vocal-ai")

    # CDR
    CDR_DB_HOST = os.getenv("CDR_DB_HOST", "localhost")
    CDR_DB_PORT = int(os.getenv("CDR_DB_PORT", "3306"))
    CDR_DB_USER = os.getenv("CDR_DB_USER", "asterisk")
    CDR_DB_PASSWORD = os.getenv("CDR_DB_PASSWORD", "asterisk")
    CDR_DB_NAME = os.getenv("CDR_DB_NAME", "asterisk")

    # Keycloak
    KEYCLOAK_URL = os.getenv("KEYCLOAK_URL", "http://localhost:8090")
    KEYCLOAK_REALM = os.getenv("KEYCLOAK_REALM", "mcp-asterisk")
    KEYCLOAK_CLIENT_ID = os.getenv("KEYCLOAK_CLIENT_ID", "mcp-agent")

    # Ollama
    OLLAMA_HOST = os.getenv("OLLAMA_HOST", "http://localhost:11434")
    OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")

    # S2S
    UDP_IP = os.getenv("UDP_IP", "0.0.0.0")
    UDP_PORT = int(os.getenv("UDP_PORT", "5088"))
    PIPER_MODEL = os.getenv("PIPER_MODEL", "./models/fr_FR-siwis-medium.onnx")
    WHISPER_MODEL = os.getenv("WHISPER_MODEL", "small")

    # Compte de service vocal
    VOCAL_USERNAME = os.getenv("VOCAL_USERNAME", "vocal-agent")
    VOCAL_PASSWORD = os.getenv("VOCAL_PASSWORD", "password")

    @property
    def ari_auth(self):
        return (self.ARI_USER, self.ARI_PASSWORD)


settings = Settings()
