import json
import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, HTTPException

from app.db import eventos, r, usuarios
from app.schemas import ReservaIn
from app.utils import to_object_id

router = APIRouter(prefix="/reservas", tags=["Reservas"])

# Req. 6: reserva bloqueada por 10 minutos (pode ser reduzido por variável de ambiente para testes)
RESERVA_TTL = int(os.getenv("RESERVA_TTL", "600"))
# Req. 8: máximo de 10 reservas por usuário por minuto
LIMITE_RESERVAS = 10
JANELA_LIMITE = 60


def chave_reserva(reserva_id: str) -> str:
    return f"reserva:{reserva_id}"


def verificar_limite(usuario_id: str) -> int:
    """Req. 8: INCR + EXPIRE. O contador nasce no 1º pedido da janela e expira em 60 s."""
    chave = f"limite:reservas:{usuario_id}"
    pipe = r.pipeline()
    pipe.incr(chave)
    pipe.expire(chave, JANELA_LIMITE, nx=True)  # só define o TTL se a chave ainda não tiver um
    total, _ = pipe.execute()
    if total > LIMITE_RESERVAS:
        ttl = r.ttl(chave)
        raise HTTPException(
            status_code=429,
            detail=f"Limite de {LIMITE_RESERVAS} reservas por minuto atingido. Tente em {ttl}s.",
            headers={"Retry-After": str(max(ttl, 1))},
        )
    return total


@router.post("", status_code=201)
def criar_reserva(dados: ReservaIn):
    # 1) Limite de requisições (Redis)
    tentativas = verificar_limite(dados.usuarioId)

    # 2) Confere no MongoDB se usuário e evento existem e se o setor tem vagas
    if not usuarios.find_one({"_id": to_object_id(dados.usuarioId, "usuarioId")}, {"_id": 1}):
        raise HTTPException(status_code=404, detail="Usuário não encontrado")

    evento = eventos.find_one(
        {"_id": to_object_id(dados.eventoId, "eventoId")}, {"nome": 1, "setores": 1}
    )
    if not evento:
        raise HTTPException(status_code=404, detail="Evento não encontrado")

    setor = next((s for s in evento["setores"] if s["nome"] == dados.setor), None)
    if not setor:
        raise HTTPException(status_code=404, detail="Setor não encontrado")

    disponiveis = setor["capacidade"] - setor["vendidos"]
    if disponiveis < dados.quantidade:
        raise HTTPException(status_code=409, detail=f"Setor sem vagas suficientes (disponíveis: {disponiveis})")

    # 3) Cria a reserva no Redis com SET NX EX: só grava se a chave não existir
    #    e ela expira sozinha após RESERVA_TTL segundos
    reserva_id = uuid.uuid4().hex
    reserva = {
        "reservaId": reserva_id,
        "usuarioId": dados.usuarioId,
        "eventoId": dados.eventoId,
        "setor": dados.setor,
        "quantidade": dados.quantidade,
        "precoUnitario": setor["preco"],
        "criadaEm": datetime.now(timezone.utc).isoformat(),
    }
    criada = r.set(chave_reserva(reserva_id), json.dumps(reserva), nx=True, ex=RESERVA_TTL)
    if not criada:
        raise HTTPException(status_code=409, detail="Reserva já existente")

    return {
        **reserva,
        "chaveRedis": chave_reserva(reserva_id),
        "expiraEmSegundos": RESERVA_TTL,
        "reservasNoUltimoMinuto": tentativas,
    }


@router.get("/{reserva_id}")
def consultar_reserva(reserva_id: str):
    """Mostra a reserva e quanto tempo falta para expirar (útil na demonstração)."""
    chave = chave_reserva(reserva_id)
    dado = r.get(chave)
    if dado is None:
        raise HTTPException(status_code=410, detail="Reserva expirada ou inexistente")
    return {**json.loads(dado), "ttl": r.ttl(chave)}
