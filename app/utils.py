from datetime import datetime

from bson import ObjectId
from bson.errors import InvalidId
from fastapi import HTTPException


def to_object_id(valor: str, campo: str = "id") -> ObjectId:
    try:
        return ObjectId(valor)
    except (InvalidId, TypeError):
        raise HTTPException(status_code=400, detail=f"{campo} inválido: {valor}")


def serializar(valor):
    """Converte ObjectId/datetime em tipos JSON. Usado tanto na resposta quanto no cache,
    para que o dado vindo do Redis e do MongoDB tenha exatamente o mesmo formato."""
    if isinstance(valor, ObjectId):
        return str(valor)
    if isinstance(valor, datetime):
        return valor.isoformat()
    if isinstance(valor, list):
        return [serializar(v) for v in valor]
    if isinstance(valor, dict):
        return {("id" if k == "_id" else k): serializar(v) for k, v in valor.items()}
    return valor
