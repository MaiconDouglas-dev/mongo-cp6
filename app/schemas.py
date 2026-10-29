from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field


class Local(BaseModel):
    cidade: str
    endereco: str
    # Locais podem ter campos extras (nome do estádio, UF...), já que o documento é flexível
    model_config = ConfigDict(extra="allow")


class Setor(BaseModel):
    nome: str
    preco: float = Field(gt=0)
    capacidade: int = Field(gt=0)
    vendidos: int = Field(default=0, ge=0)


class EventoIn(BaseModel):
    nome: str
    categoria: str
    data: datetime
    local: Local
    atracoes: list[str] = []
    setores: list[Setor] = Field(min_length=1)
    # Eventos têm estruturas diferentes entre si: aceitamos campos adicionais
    model_config = ConfigDict(extra="allow")


class EventoUpdate(BaseModel):
    nome: Optional[str] = None
    categoria: Optional[str] = None
    data: Optional[datetime] = None
    local: Optional[Local] = None
    atracoes: Optional[list[str]] = None
    setores: Optional[list[Setor]] = None
    model_config = ConfigDict(extra="allow")


class ReservaIn(BaseModel):
    usuarioId: str
    eventoId: str
    setor: str
    quantidade: int = Field(gt=0, le=10)


class ConfirmarIn(BaseModel):
    reservaId: str
