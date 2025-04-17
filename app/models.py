import enum
import uuid
from sqlalchemy import (
    Column, Integer, String, DateTime, Text, Enum as SQLEnum, ForeignKey
)
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship

from app.db import Base

class User(Base):
    __tablename__ = "users"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    phone_number = Column(String, unique=True, index=True, nullable=False)
    name = Column(String, nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), default=func.now(), onupdate=func.now())

    chat_history = relationship("ChatHistory", back_populates="user", cascade="all, delete-orphan")

class SenderTypeEnum(str, enum.Enum): # Herdando de str para facilitar serialização JSON
    USER = "user"
    AI = "ai"

class ChatHistory(Base):
    __tablename__ = "chat_history"

    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    # Usando ForeignKey para ID do usuário em vez de telefone diretamente
    # Isso é geralmente melhor para integridade referencial
    user_id = Column(PG_UUID(as_uuid=True), ForeignKey("users.id"), nullable=False, index=True)
    message = Column(Text, nullable=False)
    sender_type = Column(SQLEnum(SenderTypeEnum, name="sender_type_enum"), nullable=False) # Adiciona nome ao Enum
    timestamp = Column(DateTime(timezone=True), server_default=func.now(), index=True)

    user = relationship("User", back_populates="chat_history")