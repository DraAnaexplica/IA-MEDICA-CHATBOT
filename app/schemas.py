from pydantic import BaseModel, Field
from typing import Optional, List
import datetime
import uuid
from app.models import SenderTypeEnum # Importa o Enum

# --- Schemas para Histórico de Chat ---
class ChatHistoryBase(BaseModel):
    message: str
    sender_type: SenderTypeEnum

class ChatHistorySchema(ChatHistoryBase):
    id: uuid.UUID
    timestamp: datetime.datetime
    user_id: uuid.UUID # Adicionado para referência

    class Config:
        from_attributes = True # Pydantic v2+ (ou orm_mode = True para v1)

# --- Schemas para Z-API Webhook Simplificado ---
class ZapiMessagePayload(BaseModel):
    text: Optional[str] = Field(None, alias="mensagem")

class ZapiWebhookPayload(BaseModel):
    phone: str
    senderName: Optional[str] = Field(None, alias="nome_remetente")
    message: Optional[ZapiMessagePayload] = None
    isGroupMessage: Optional[bool] = False

# --- Schemas para OpenRouter Simplificado ---
class OpenRouterMessage(BaseModel):
    role: str # "system", "user", "assistant"
    content: str

class OpenRouterRequest(BaseModel):
    model: str
    messages: List[OpenRouterMessage]
    max_tokens: int = 1000 # Limite padrão

class OpenRouterChoice(BaseModel):
    message: OpenRouterMessage

class OpenRouterResponse(BaseModel):
    choices: List[OpenRouterChoice]
    # Não precisamos do 'usage' para esta versão mínima