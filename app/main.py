from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.db import criar_indices, mongo_client, r, usuarios
from app.routers import eventos, pedidos, relatorios, reservas
from app.utils import serializar


@asynccontextmanager
async def lifespan(app: FastAPI):
    criar_indices()
    yield
    mongo_client.close()
    r.close()


app = FastAPI(
    title="TicketFlash API",
    description="Back-end de ingressos com MongoDB (persistência) e Redis (cache, reservas, ranking, rate limit).",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(eventos.router)
app.include_router(reservas.router)
app.include_router(pedidos.router)
app.include_router(relatorios.router)


@app.get("/health", tags=["Infra"])
def health():
    mongo_client.admin.command("ping")
    r.ping()
    return {"mongo": "ok", "redis": "ok"}


@app.get("/usuarios", tags=["Usuários"])
def listar_usuarios(limite: int = 20):
    """Apoio para a demonstração: pegar ids de usuários do seed."""
    return [serializar(u) for u in usuarios.find().limit(limite)]
