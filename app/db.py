from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from app.config import settings, logger

DATABASE_URL = settings.DATABASE_URL
Base = declarative_base()
engine = None
AsyncSessionFactory = None

try:
    if DATABASE_URL:
        engine = create_async_engine(DATABASE_URL, echo=False, future=True)
        AsyncSessionFactory = sessionmaker(
            engine, class_=AsyncSession, expire_on_commit=False
        )
        logger.info("Motor SQLAlchemy e Fábrica de Sessão Async criados.")
    else:
        logger.error("DATABASE_URL não definida nas configurações!")

except Exception as e:
    logger.error(f"Falha ao inicializar conexão com o banco de dados: {e}", exc_info=True)
    engine = None
    AsyncSessionFactory = None

async def get_db() -> AsyncSession:
    """Dependência FastAPI para obter uma sessão de banco de dados."""
    if AsyncSessionFactory is None:
        logger.error("Fábrica de Sessão não inicializada.")
        raise RuntimeError("Conexão com DB não estabelecida.")

    async with AsyncSessionFactory() as session:
        try:
            yield session
            await session.commit()
        except Exception as e:
            logger.error(f"Erro durante transação da sessão: {e}", exc_info=True)
            await session.rollback()
            raise
        finally:
            await session.close()

async def init_db():
    """Cria as tabelas (se não existirem)."""
    if engine:
        async with engine.begin() as conn:
            try:
                # await conn.run_sync(Base.metadata.drop_all) # CUIDADO!
                await conn.run_sync(Base.metadata.create_all)
                logger.info("Tabelas do banco de dados verificadas/criadas.")
            except Exception as e:
                logger.error(f"Falha ao inicializar tabelas do DB: {e}", exc_info=True)
    else:
        logger.error("Motor do DB não inicializado, impossível criar tabelas.")