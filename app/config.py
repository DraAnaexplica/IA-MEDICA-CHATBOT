import os
import logging
from pydantic_settings import BaseSettings
from pathlib import Path
from dotenv import load_dotenv

# Carrega variáveis do .env se existir
env_path = Path('.') / '.env'
load_dotenv(dotenv_path=env_path)

class Settings(BaseSettings):
    DATABASE_URL: str
    OPENROUTER_API_KEY: str
    ZAPI_INSTANCE_ID: str
    ZAPI_TOKEN: str
    ZAPI_API_URL: str = "https://api.z-api.io/instances"
    SYSTEM_PROMPT_PATH: str = "prompt/system_prompt.txt"
    OPENROUTER_MODEL: str = "google/gemini-flash-1.5"
    CONTEXT_MESSAGE_COUNT: int = 6
    LOG_LEVEL: str = "INFO"

    _system_prompt_cache: str | None = None

    @property
    def system_prompt(self) -> str:
        if self._system_prompt_cache is None:
            try:
                with open(self.SYSTEM_PROMPT_PATH, 'r', encoding='utf-8') as f:
                    self._system_prompt_cache = f.read().strip()
            except Exception as e:
                logging.error(f"ERRO ao ler o arquivo de prompt: {e}. Usando prompt padrão.", exc_info=True)
                self._system_prompt_cache = "Você é uma assistente virtual."
        return self._system_prompt_cache

    @property
    def zapi_send_message_url(self) -> str:
        # Garante que não haja barras duplicadas se ZAPI_API_URL já tiver / no final
        base_url = self.ZAPI_API_URL.rstrip('/')
        return f"{base_url}/instances/{self.ZAPI_INSTANCE_ID}/token/{self.ZAPI_TOKEN}/send-text"

    class Config:
        env_file = '.env'
        env_file_encoding = 'utf-8'
        extra = 'ignore'

settings = Settings()

# Configuração básica de Logging
logging.basicConfig(
    level=settings.LOG_LEVEL.upper(),
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger("DraAnaIA_Minimal")

logger.info("Configurações carregadas.")
logger.debug(f"DB URL Configurada: {'Sim' if settings.DATABASE_URL else 'Não'}")
logger.debug(f"OpenRouter Model: {settings.OPENROUTER_MODEL}")
logger.debug(f"Z-API Instance: {settings.ZAPI_INSTANCE_ID}")