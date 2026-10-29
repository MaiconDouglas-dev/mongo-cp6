"""Req. 3: mostra o plano de execução de uma consulta que usa o índice composto categoria + data.

Uso:
    docker compose exec api python explain.py
"""
import json

from app.db import criar_indices, eventos

criar_indices()

consulta = eventos.find({"categoria": "show"}).sort("data", 1)
plano = consulta.explain()

planner = plano["queryPlanner"]
stats = plano["executionStats"]


def estagios(plano_vencedor: dict) -> list[str]:
    """Percorre a árvore do plano (FETCH -> IXSCAN ...) e devolve os estágios."""
    nomes, atual = [], plano_vencedor
    while atual:
        nome = atual.get("stage")
        if atual.get("indexName"):
            nome += f" ({atual['indexName']})"
        nomes.append(nome)
        atual = atual.get("inputStage")
    return nomes


print("Consulta: db.eventos.find({categoria: 'show'}).sort({data: 1})\n")
print("Estágios do plano vencedor:", " -> ".join(estagios(planner["winningPlan"])))
print("Documentos retornados:   ", stats["nReturned"])
print("Chaves de índice lidas:  ", stats["totalKeysExamined"])
print("Documentos examinados:   ", stats["totalDocsExamined"])
print("Tempo de execução (ms):  ", stats["executionTimeMillis"])
print("\nwinningPlan completo:")
print(json.dumps(planner["winningPlan"], indent=2, default=str))
