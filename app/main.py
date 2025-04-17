from fastapi import FastAPI, Depends, HTTPException, Request, BackgroundTasks, Response
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy import desc
from contextlib import asynccontextmanager
import httpx
import uuid

from app import db, models, schemas
from app.config import settings, logger

# --- Ciclo de Vida da Aplicação ---
@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Iniciando aplicação...")
    await db.init_db() # Cria tabelas se não existirem
    yield
    logger.info("Encerrando aplicação...")
    if db.engine:
        await db.engine.dispose()

app = FastAPI(
    title="Dra. Ana IA - Minimal",
    description="Versão simplificada para testes de integração.",
    version="0.1.0",
    lifespan=lifespan
)

# --- Funções Auxiliares (Podem ficar aqui ou em crud.py simplificado) ---

async def get_or_create_user(session: AsyncSession, phone: str, name: Optional[str] = None) -> models.User:
    """Busca usuário pelo telefone ou cria um novo."""
    result = await session.execute(select(models.User).filter(models.User.phone_number == phone))
    user = result.scalars().first()

    if user:
        # Atualiza o nome se veio diferente ou se estava vazio
        if name and (not user.name or user.name != name):
            user.name = name
            session.add(user)
            await session.flush()
            await session.refresh(user)
            logger.info(f"Nome do usuário {phone} atualizado para '{name}'.")
        return user
    else:
        logger.info(f"Criando novo usuário para {phone}.")
        new_user = models.User(phone_number=phone, name=name)
        session.add(new_user)
        await session.flush() # Garante que o ID seja gerado
        await session.refresh(new_user)
        return new_user

async def save_chat_message(session: AsyncSession, user_id: uuid.UUID, message: str, sender: models.SenderTypeEnum):
    """Salva uma mensagem no histórico."""
    chat_entry = models.ChatHistory(
        user_id=user_id,
        message=message,
        sender_type=sender
    )
    session.add(chat_entry)
    await session.flush()
    logger.debug(f"Mensagem de '{sender.value}' salva para usuário ID {user_id}")

async def get_chat_history(session: AsyncSession, user_id: uuid.UUID, limit: int) -> list[models.ChatHistory]:
    """Recupera as últimas N mensagens em ordem cronológica."""
    result = await session.execute(
        select(models.ChatHistory)
        .filter(models.ChatHistory.user_id == user_id)
        .order_by(desc(models.ChatHistory.timestamp))
        .limit(limit)
    )
    messages = result.scalars().all()
    return messages[::-1] # Inverte para ordem cronológica (antigo -> novo)

async def call_openrouter(history: list[schemas.OpenRouterMessage]) -> Optional[str]:
    """Chama a API OpenRouter para gerar resposta."""
    payload = schemas.OpenRouterRequest(
        model=settings.OPENROUTER_MODEL,
        messages=[schemas.OpenRouterMessage(role="system", content=settings.system_prompt)] + history
    )
    headers = {
        "Authorization": f"Bearer {settings.OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    url = "https://openrouter.ai/api/v1/chat/completions"

    logger.debug(f"Enviando para OpenRouter: Model={payload.model}, Mensagens={len(payload.messages)}")
    async with httpx.AsyncClient(timeout=60.0) as client:
        try:
            response = await client.post(url, json=payload.model_dump(), headers=headers)
            response.raise_for_status()
            data = response.json()
            parsed_response = schemas.OpenRouterResponse.model_validate(data) # Pydantic v2
            # parsed_response = schemas.OpenRouterResponse.parse_obj(data) # Pydantic v1

            if parsed_response.choices:
                ai_message = parsed_response.choices[0].message.content
                logger.info("Resposta da IA recebida do OpenRouter.")
                return ai_message.strip()
            else:
                logger.warning("OpenRouter respondeu sem 'choices'.")
                return None
        except httpx.HTTPStatusError as e:
            logger.error(f"Erro HTTP OpenRouter: Status {e.response.status_code}, Response: {e.response.text}", exc_info=True)
            return None
        except Exception as e:
            logger.error(f"Erro ao chamar ou processar OpenRouter: {e}", exc_info=True)
            return None

async def send_zapi_message(phone: str, message: str):
    """Envia mensagem via Z-API."""
    if not message:
        logger.warning(f"Tentativa de enviar mensagem vazia para {phone}.")
        return
    # Limpeza básica do número (remover não dígitos, garantir 55 se for número BR curto)
    clean_phone = "".join(filter(str.isdigit, phone))
    if len(clean_phone) <= 11 and not clean_phone.startswith("55"):
        clean_phone = "55" + clean_phone

    payload = {"phone": clean_phone, "message": message}
    url = settings.zapi_send_message_url
    headers = {"Content-Type": "application/json"}

    logger.info(f"Enviando mensagem Z-API para {clean_phone}")
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            logger.info(f"Mensagem enviada com sucesso para {clean_phone}")
            logger.debug(f"Z-API Response: {response.json()}")
        except httpx.HTTPStatusError as e:
            logger.error(f"Erro HTTP Z-API: Status {e.response.status_code}, Response: {e.response.text}", exc_info=True)
        except Exception as e:
            logger.error(f"Erro ao enviar mensagem Z-API: {e}", exc_info=True)


# --- Processamento da Mensagem (Tarefa de Fundo) ---
async def process_incoming_message(db_session: AsyncSession, phone: str, name: Optional[str], user_message: str):
    """Orquestra o fluxo de processamento."""
    try:
        logger.info(f"[BG Task] Iniciando processamento para {phone}")
        user = await get_or_create_user(db_session, phone, name)

        await save_chat_message(db_session, user.id, user_message, models.SenderTypeEnum.USER)

        # Recuperar histórico recente
        history_db = await get_chat_history(db_session, user.id, settings.CONTEXT_MESSAGE_COUNT)
        history_for_ai = [
            schemas.OpenRouterMessage(
                role="assistant" if msg.sender_type == models.SenderTypeEnum.AI else "user",
                content=msg.message
            )
            for msg in history_db # Inclui a mensagem atual do usuário que acabamos de salvar
        ]

        # Chamar IA
        ai_response = await call_openrouter(history_for_ai)

        if ai_response:
            await save_chat_message(db_session, user.id, ai_response, models.SenderTypeEnum.AI)
            await send_zapi_message(phone, ai_response)
        else:
            logger.error(f"[BG Task] Falha ao obter resposta da IA para {phone}. Enviando msg de erro.")
            await send_zapi_message(phone, "Desculpe, não consegui processar sua solicitação no momento. 🥺 Tente novamente mais tarde.")

        # Commit explícito aqui, pois get_db fará commit/rollback fora desta função
        # Na verdade, o commit é feito pelo context manager do get_db ao final do request
        # await db_session.commit() # Não é necessário aqui se get_db gerencia

        logger.info(f"[BG Task] Processamento concluído para {phone}")

    except Exception as e:
        logger.error(f"[BG Task] Erro fatal no processamento para {phone}: {e}", exc_info=True)
        # Tentar enviar mensagem de erro genérica
        try:
            await send_zapi_message(phone, "Ocorreu um erro interno. Por favor, tente novamente mais tarde.")
        except Exception as send_err:
             logger.error(f"[BG Task] Falha ao enviar mensagem de erro final para {phone}: {send_err}")
        # O rollback será feito pelo context manager do get_db

# --- Endpoint Webhook Z-API ---
@app.post("/webhook/zapi", status_code=200)
async def handle_zapi_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    db_session: AsyncSession = Depends(db.get_db) # Obtém sessão do DB
):
    """Recebe webhook da Z-API e dispara processamento em background."""
    try:
        payload = await request.json()
        logger.debug(f"Webhook Z-API recebido: {payload}")
    except Exception as e:
        logger.error(f"Erro ao ler JSON do webhook: {e}", exc_info=True)
        raise HTTPException(status_code=400, detail="Payload inválido.")

    try:
        # Validação básica com Pydantic
        webhook_data = schemas.ZapiWebhookPayload.model_validate(payload) # Pydantic v2
        # webhook_data = schemas.ZapiWebhookPayload.parse_obj(payload) # Pydantic v1

        if webhook_data.isGroupMessage:
            logger.info("Mensagem de grupo ignorada.")
            return {"status": "ignored_group_message"}

        if not webhook_data.message or not webhook_data.message.text:
            logger.info("Webhook sem mensagem de texto ignorado.")
            return {"status": "ignored_no_text"}

        phone = webhook_data.phone
        name = webhook_data.senderName
        user_message = webhook_data.message.text.strip()

        if not user_message:
             logger.info("Mensagem de texto vazia ignorada.")
             return {"status": "ignored_empty_text"}


        # Adiciona tarefa de fundo para processar
        background_tasks.add_task(process_incoming_message, db_session, phone, name, user_message)

        logger.info(f"Mensagem de {phone} adicionada à fila de processamento.")
        return {"status": "received"} # Resposta rápida para Z-API

    except Exception as e: # Erro na validação Pydantic ou outra lógica aqui
        logger.error(f"Erro ao processar payload do webhook: {e}", exc_info=True)
        # Não levanta HTTPException aqui para evitar que Z-API tente reenviar indefinidamente
        # Apenas loga o erro e retorna OK.
        return {"status": "processing_error"}


# --- Endpoint de Health Check ---
@app.get("/health", status_code=200)
async def health_check():
    """Verifica se a aplicação está rodando."""
    return {"status": "ok"}

# --- Para rodar localmente ---
# if __name__ == "__main__":
#     import uvicorn
#     uvicorn.run("app.main:app", host="0.0.0.0", port=8000, reload=True)
# Comentado pois Gunicorn/Render usará o comando no Procfile