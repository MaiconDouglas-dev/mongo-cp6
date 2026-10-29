import json
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, HTTPException, Query

from app.cache import CANAL_PEDIDOS, invalidar_evento
from app.db import eventos, pedidos, r
from app.routers.reservas import chave_reserva
from app.schemas import ConfirmarIn
from app.utils import serializar, to_object_id

router = APIRouter(prefix="/pedidos", tags=["Pedidos"])


@router.post("/confirmar", status_code=201)
def confirmar_pedido(dados: ConfirmarIn):
    """Req. 10: fluxo de compra."""
    chave = chave_reserva(dados.reservaId)

    # 1) A reserva ainda existe no Redis? GETDEL lê e apaga numa única operação atômica,
    #    então duas confirmações simultâneas da mesma reserva não geram dois pedidos.
    dado = r.getdel(chave)
    if dado is None:
        # Reserva expirou (ou já foi usada): nada é gravado no MongoDB
        raise HTTPException(status_code=410, detail="Reserva expirada ou inexistente")
    reserva = json.loads(dado)

    evento_oid = to_object_id(reserva["eventoId"], "eventoId")
    evento = eventos.find_one({"_id": evento_oid}, {"setores": 1})
    setor = next((s for s in (evento or {}).get("setores", []) if s["nome"] == reserva["setor"]), None)
    if setor is None:
        raise HTTPException(status_code=404, detail="Evento ou setor não existe mais")

    # 2) $inc atômico e condicional: a condição está no próprio filtro do update_one.
    #    Só incrementa se vendidos + quantidade <= capacidade; caso contrário não casa nenhum documento.
    quantidade = reserva["quantidade"]
    resultado = eventos.update_one(
        {
            "_id": evento_oid,
            "setores": {
                "$elemMatch": {
                    "nome": reserva["setor"],
                    "vendidos": {"$lte": setor["capacidade"] - quantidade},
                }
            },
        },
        {"$inc": {"setores.$.vendidos": quantidade}},
    )
    if resultado.modified_count == 0:
        raise HTTPException(status_code=409, detail="Setor esgotado: capacidade atingida")

    # 3) Grava o pedido (dado permanente) no MongoDB
    pedido = {
        "usuarioId": to_object_id(reserva["usuarioId"], "usuarioId"),
        "eventoId": evento_oid,
        "setor": reserva["setor"],
        "quantidade": quantidade,
        "valorTotal": round(setor["preco"] * quantidade, 2),
        "status": "confirmado",
        "criadoEm": datetime.now(timezone.utc),
    }
    pedido["_id"] = pedidos.insert_one(pedido).inserted_id

    # vendidos mudou: o cache do evento ficaria desatualizado
    invalidar_evento(reserva["eventoId"])

    # Bônus: avisa os assinantes do canal pedidos:confirmados
    resposta = serializar(pedido)
    r.publish(CANAL_PEDIDOS, json.dumps(resposta))
    return resposta


@router.get("")
def listar_pedidos(
    usuarioId: Optional[str] = None,
    status: Optional[str] = None,
    limite: int = Query(50, ge=1, le=200),
):
    filtro = {}
    if usuarioId:
        filtro["usuarioId"] = to_object_id(usuarioId, "usuarioId")  # usa ix_usuario_criadoEm
    if status:
        filtro["status"] = status
    cursor = pedidos.find(filtro).sort("criadoEm", -1).limit(limite)
    return [serializar(p) for p in cursor]
