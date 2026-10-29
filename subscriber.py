"""Bônus: assinante do canal Pub/Sub pedidos:confirmados.

Uso (com o ambiente no ar):
    docker compose exec api python subscriber.py
"""
import json
from datetime import datetime

from app.cache import CANAL_PEDIDOS
from app.db import r


def main() -> None:
    pubsub = r.pubsub(ignore_subscribe_messages=True)
    pubsub.subscribe(CANAL_PEDIDOS)
    print(f"Escutando o canal '{CANAL_PEDIDOS}'... (Ctrl+C para sair)", flush=True)

    try:
        for mensagem in pubsub.listen():
            pedido = json.loads(mensagem["data"])
            hora = datetime.now().strftime("%H:%M:%S")
            print(
                f"[{hora}] Pedido confirmado {pedido['id']} | evento {pedido['eventoId']} | "
                f"setor {pedido['setor']} | {pedido['quantidade']} ingresso(s) | R$ {pedido['valorTotal']:.2f}",
                flush=True,
            )
    except KeyboardInterrupt:
        pass
    finally:
        pubsub.close()


if __name__ == "__main__":
    main()
