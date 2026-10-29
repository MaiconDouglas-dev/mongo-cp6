from typing import Optional

from fastapi import APIRouter, HTTPException, Query, Response
from pymongo import ASCENDING

from app.cache import RANKING_KEY, gravar_evento_cache, invalidar_evento, ler_evento_cache
from app.db import eventos, r
from app.schemas import EventoIn, EventoUpdate
from app.utils import serializar, to_object_id

router = APIRouter(prefix="/eventos", tags=["Eventos"])


@router.post("", status_code=201)
def criar_evento(evento: EventoIn):
    doc = evento.model_dump()
    resultado = eventos.insert_one(doc)
    doc["_id"] = resultado.inserted_id
    return serializar(doc)


@router.get("")
def listar_eventos(
    categoria: Optional[str] = None,
    cidade: Optional[str] = None,
    limite: int = Query(50, ge=1, le=200),
):
    # Os filtros vão direto para a consulta do MongoDB (usam ix_categoria_data / ix_local_cidade)
    filtro = {}
    if categoria:
        filtro["categoria"] = categoria
    if cidade:
        filtro["local.cidade"] = cidade
    cursor = eventos.find(filtro).sort("data", ASCENDING).limit(limite)
    return [serializar(e) for e in cursor]


# Declarada antes de /{evento_id} para "ranking" não ser interpretado como id
@router.get("/ranking")
def ranking_eventos():
    """Req. 7: top 5 do Sorted Set (maior score primeiro)."""
    top = r.zrevrange(RANKING_KEY, 0, 4, withscores=True)
    ids = [to_object_id(eid) for eid, _ in top]
    nomes = {str(e["_id"]): e["nome"] for e in eventos.find({"_id": {"$in": ids}}, {"nome": 1})}
    return [
        {"posicao": i + 1, "eventoId": eid, "nome": nomes.get(eid), "visualizacoes": int(score)}
        for i, (eid, score) in enumerate(top)
    ]


@router.get("/{evento_id}")
def buscar_evento(evento_id: str):
    """Req. 5 (cache-aside): consulta o Redis primeiro; se não houver, busca no MongoDB
    e grava no cache com TTL de 60 s."""
    oid = to_object_id(evento_id)

    evento = ler_evento_cache(evento_id)
    origem = "cache"
    if evento is None:
        doc = eventos.find_one({"_id": oid})
        if doc is None:
            raise HTTPException(status_code=404, detail="Evento não encontrado")
        evento = serializar(doc)
        gravar_evento_cache(evento_id, evento)
        origem = "banco"

    # Req. 7: cada consulta soma 1 ao score do evento no ranking
    r.zincrby(RANKING_KEY, 1, evento_id)
    return {"origem": origem, "evento": evento}


@router.put("/{evento_id}")
def atualizar_evento(evento_id: str, dados: EventoUpdate):
    oid = to_object_id(evento_id)
    campos = dados.model_dump(exclude_unset=True)
    if not campos:
        raise HTTPException(status_code=400, detail="Nenhum campo para atualizar")

    resultado = eventos.update_one({"_id": oid}, {"$set": campos})
    if resultado.matched_count == 0:
        raise HTTPException(status_code=404, detail="Evento não encontrado")

    invalidar_evento(evento_id)  # Req. 9: invalida o cache no update
    return serializar(eventos.find_one({"_id": oid}))


@router.delete("/{evento_id}", status_code=204)
def remover_evento(evento_id: str):
    oid = to_object_id(evento_id)
    resultado = eventos.delete_one({"_id": oid})
    if resultado.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Evento não encontrado")

    invalidar_evento(evento_id)  # Req. 9: invalida o cache no delete
    r.zrem(RANKING_KEY, evento_id)  # evento removido sai do ranking
    return Response(status_code=204)
