"""Chaves e helpers do Redis usados pela API."""
import json

from app.db import r

CACHE_TTL = 60  # Req. 5: cache de evento por 60 s
RANKING_KEY = "ranking:eventos"  # Req. 7: Sorted Set
CANAL_PEDIDOS = "pedidos:confirmados"  # Bônus: Pub/Sub


def chave_evento(evento_id: str) -> str:
    return f"evento:{evento_id}"


def ler_evento_cache(evento_id: str):
    dado = r.get(chave_evento(evento_id))
    return json.loads(dado) if dado else None


def gravar_evento_cache(evento_id: str, evento: dict) -> None:
    # SET com EX: a chave expira sozinha após CACHE_TTL segundos
    r.set(chave_evento(evento_id), json.dumps(evento), ex=CACHE_TTL)


def invalidar_evento(evento_id: str) -> None:
    """Req. 9: apaga a chave para a próxima leitura buscar no MongoDB."""
    r.delete(chave_evento(evento_id))
