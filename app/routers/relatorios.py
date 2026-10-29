"""Req. 4: relatórios calculados inteiramente no MongoDB via aggregation pipeline."""
from fastapi import APIRouter, HTTPException

from app.db import eventos, pedidos
from app.utils import serializar, to_object_id

router = APIRouter(prefix="/relatorios", tags=["Relatórios"])


@router.get("/faturamento")
def faturamento_por_evento():
    pipeline = [
        {"$match": {"status": "confirmado"}},
        {
            "$group": {
                "_id": "$eventoId",
                "faturamento": {"$sum": "$valorTotal"},
                "ingressosVendidos": {"$sum": "$quantidade"},
                "pedidos": {"$sum": 1},
            }
        },
        {
            "$lookup": {
                "from": "eventos",
                "localField": "_id",
                "foreignField": "_id",
                "as": "evento",
            }
        },
        # preserveNull... mantém pedidos de eventos que foram removidos
        {"$unwind": {"path": "$evento", "preserveNullAndEmptyArrays": True}},
        {
            "$project": {
                "_id": 0,
                "eventoId": "$_id",
                "nome": {"$ifNull": ["$evento.nome", "(evento removido)"]},
                "faturamento": {"$round": ["$faturamento", 2]},
                "ingressosVendidos": 1,
                "pedidos": 1,
            }
        },
        {"$sort": {"faturamento": -1}},
    ]
    return serializar(list(pedidos.aggregate(pipeline)))


@router.get("/ocupacao/{evento_id}")
def ocupacao_por_setor(evento_id: str):
    pipeline = [
        {"$match": {"_id": to_object_id(evento_id)}},
        {"$unwind": "$setores"},
        {
            "$project": {
                "_id": 0,
                "evento": "$nome",
                "setor": "$setores.nome",
                "capacidade": "$setores.capacidade",
                "vendidos": "$setores.vendidos",
                "disponiveis": {"$subtract": ["$setores.capacidade", "$setores.vendidos"]},
                "percentualVendido": {
                    "$round": [
                        {"$multiply": [{"$divide": ["$setores.vendidos", "$setores.capacidade"]}, 100]},
                        2,
                    ]
                },
            }
        },
        {"$sort": {"percentualVendido": -1}},
    ]
    resultado = list(eventos.aggregate(pipeline))
    if not resultado:
        raise HTTPException(status_code=404, detail="Evento não encontrado")
    return resultado
