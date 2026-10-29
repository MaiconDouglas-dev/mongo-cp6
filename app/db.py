"""Conexões com MongoDB (fonte da verdade) e Redis (dados rápidos/temporários)."""
import os

import redis
from pymongo import ASCENDING, DESCENDING, MongoClient

MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")
MONGO_DB = os.getenv("MONGO_DB", "ticketflash")
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")

mongo_client = MongoClient(MONGO_URL)
db = mongo_client[MONGO_DB]

eventos = db["eventos"]
usuarios = db["usuarios"]
pedidos = db["pedidos"]

# decode_responses=True -> o redis-py devolve str em vez de bytes
r = redis.Redis.from_url(REDIS_URL, decode_responses=True)


def criar_indices() -> None:
    """Requisito 3: índices criados pelo próprio código (idempotente)."""
    # Índice único: não permite dois usuários com o mesmo e-mail
    usuarios.create_index([("email", ASCENDING)], unique=True, name="ux_email")
    # Índice composto: listagem por categoria ordenada por data
    eventos.create_index([("categoria", ASCENDING), ("data", ASCENDING)], name="ix_categoria_data")
    # Filtro por cidade na listagem de eventos
    eventos.create_index([("local.cidade", ASCENDING)], name="ix_local_cidade")
    # Pedidos de um usuário (histórico)
    pedidos.create_index([("usuarioId", ASCENDING), ("criadoEm", DESCENDING)], name="ix_usuario_criadoEm")
    # Relatório de faturamento filtra por status e agrupa por evento
    pedidos.create_index([("status", ASCENDING), ("eventoId", ASCENDING)], name="ix_status_evento")
