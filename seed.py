"""Popula o MongoDB com 12 eventos, 20 usuários e 60 pedidos.

Uso:
    python seed.py           # só popula se o banco estiver vazio
    python seed.py --reset   # apaga tudo (Mongo + Redis) e popula de novo
"""
import random
import sys
import unicodedata
from datetime import datetime, timedelta, timezone

from app.db import criar_indices, eventos, pedidos, r, usuarios

random.seed(42)  # dados reproduzíveis
agora = datetime.now(timezone.utc).replace(microsecond=0)

EVENTOS = [
    {
        "nome": "Rock in Rio Warm-Up",
        "categoria": "show",
        "local": {"cidade": "Rio de Janeiro", "endereco": "Av. Salvador Allende, 6555", "nome": "Cidade do Rock"},
        "atracoes": ["Foo Fighters", "Capital Inicial"],
        "setores": [("Pista", 350.0, 5000), ("Pista Premium", 690.0, 1500), ("Camarote", 1200.0, 300)],
    },
    {
        "nome": "Turnê Coldplay Brasil",
        "categoria": "show",
        "local": {"cidade": "São Paulo", "endereco": "Av. Francisco Matarazzo, 1705", "nome": "Allianz Parque"},
        "atracoes": ["Coldplay", "Emicida"],
        "setores": [("Pista", 420.0, 8000), ("Cadeira Inferior", 580.0, 4000), ("Cadeira Superior", 290.0, 6000)],
    },
    {
        "nome": "Final Copa do Brasil",
        "categoria": "esporte",
        "local": {"cidade": "São Paulo", "endereco": "Av. Miguel Ignácio Curi, 111", "nome": "Neo Química Arena"},
        "atracoes": ["Corinthians", "Flamengo"],
        "times": {"mandante": "Corinthians", "visitante": "Flamengo"},
        "setores": [("Norte", 180.0, 9000), ("Sul", 180.0, 9000), ("Leste", 320.0, 7000), ("Oeste", 450.0, 7000)],
    },
    {
        "nome": "O Fantasma da Ópera",
        "categoria": "teatro",
        "local": {"cidade": "São Paulo", "endereco": "Av. Brigadeiro Luís Antônio, 411", "nome": "Teatro Renault"},
        "atracoes": ["Elenco Broadway Brasil"],
        "classificacaoIndicativa": 10,
        "setores": [("Plateia", 280.0, 800), ("Balcão", 160.0, 400)],
    },
    {
        "nome": "Stand-up Comedy Night",
        "categoria": "comedia",
        "local": {"cidade": "Curitiba", "endereco": "R. Prof. Pedro Viriato Parigot de Souza, 1000"},
        "atracoes": ["Fábio Porchat", "Thiago Ventura"],
        "setores": [("Plateia", 120.0, 600), ("VIP", 220.0, 100)],
    },
    {
        "nome": "Festival de Jazz de Inverno",
        "categoria": "festival",
        "local": {"cidade": "Campos do Jordão", "endereco": "Av. Dr. Januário Miráglia, 1000"},
        "atracoes": ["Hamilton de Holanda", "Diana Krall", "Seu Jorge"],
        "duracaoDias": 3,
        "setores": [("Passaporte 3 dias", 900.0, 2000), ("Diária", 350.0, 3000)],
    },
    {
        "nome": "Tech Summit 2026",
        "categoria": "conferencia",
        "local": {"cidade": "São Paulo", "endereco": "Rod. dos Imigrantes, km 1,5", "nome": "São Paulo Expo"},
        "atracoes": ["Keynote IA Generativa", "Painel Cloud Native"],
        "trilhas": ["IA", "Cloud", "Segurança"],
        "setores": [("Standard", 499.0, 3000), ("Full Pass", 1290.0, 800)],
    },
    {
        "nome": "Anitta - Funk Generation",
        "categoria": "show",
        "local": {"cidade": "Belo Horizonte", "endereco": "Av. Antônio Abrahão Caram, 1001", "nome": "Mineirão"},
        "atracoes": ["Anitta", "Ludmilla"],
        "setores": [("Pista", 250.0, 15000), ("Front Stage", 520.0, 3000), ("Camarote", 980.0, 500)],
    },
    {
        "nome": "NBB - Final",
        "categoria": "esporte",
        "local": {"cidade": "Brasília", "endereco": "SRPN Eixo Monumental", "nome": "Arena BRB"},
        "atracoes": ["Flamengo Basquete", "Franca"],
        "times": {"mandante": "Franca", "visitante": "Flamengo Basquete"},
        "setores": [("Arquibancada", 90.0, 8000), ("Quadra", 400.0, 300)],
    },
    {
        "nome": "Orquestra Sinfônica - Beethoven 9",
        "categoria": "teatro",
        "local": {"cidade": "Porto Alegre", "endereco": "Av. Borges de Medeiros, 1501", "nome": "Teatro da OSPA"},
        "atracoes": ["OSPA", "Coral Sinfônico"],
        "setores": [("Plateia A", 150.0, 500), ("Plateia B", 100.0, 700), ("Mezanino", 70.0, 300)],
    },
    {
        "nome": "Lollapalooza Sideshow",
        "categoria": "festival",
        "local": {"cidade": "São Paulo", "endereco": "Av. Sen. Teotônio Vilela, 261", "nome": "Autódromo de Interlagos"},
        "atracoes": ["Arctic Monkeys", "Marina Sena", "Jão"],
        "setores": [("Pista", 750.0, 30000), ("Lolla Lounge", 2100.0, 2000)],
    },
    {
        "nome": "Workshop MongoDB + Redis",
        "categoria": "conferencia",
        "local": {"cidade": "Recife", "endereco": "R. do Apolo, 181", "nome": "Porto Digital"},
        "atracoes": ["Hands-on NoSQL"],
        "trilhas": ["Banco de Dados"],
        "setores": [("Presencial", 80.0, 50)],  # setor pequeno para testar esgotamento
    },
]

NOMES = [
    "Ana Souza", "Bruno Lima", "Carla Mendes", "Diego Rocha", "Eduarda Alves", "Felipe Costa",
    "Gabriela Nunes", "Henrique Dias", "Isabela Martins", "João Pereira", "Karina Gomes", "Lucas Ribeiro",
    "Mariana Castro", "Nicolas Ferreira", "Olívia Barros", "Pedro Henrique", "Rafaela Teixeira",
    "Samuel Araújo", "Tatiane Moreira", "Vinícius Cardoso",
]
CIDADES = ["São Paulo", "Rio de Janeiro", "Belo Horizonte", "Curitiba", "Porto Alegre", "Recife", "Brasília"]
STATUS = ["confirmado"] * 7 + ["cancelado"] * 2 + ["pendente"]  # maioria confirmada


def popular() -> None:
    # ---- eventos (setores embutidos) ----
    docs_eventos = []
    for i, base in enumerate(EVENTOS):
        doc = {k: v for k, v in base.items() if k != "setores"}
        doc["data"] = agora + timedelta(days=15 + i * 9, hours=random.choice([0, 2, 4]))
        doc["setores"] = [{"nome": n, "preco": p, "capacidade": c, "vendidos": 0} for n, p, c in base["setores"]]
        docs_eventos.append(doc)
    ids_eventos = eventos.insert_many(docs_eventos).inserted_ids
    for doc, _id in zip(docs_eventos, ids_eventos):
        doc["_id"] = _id

    # ---- usuários ----
    docs_usuarios = []
    for nome in NOMES:
        sem_acento = unicodedata.normalize("NFKD", nome.lower()).encode("ascii", "ignore").decode()
        partes = sem_acento.split()
        email = f"{partes[0]}.{partes[-1]}@email.com"
        docs_usuarios.append({
            "nome": nome,
            "email": email,
            "cidade": random.choice(CIDADES),
            "dataCadastro": agora - timedelta(days=random.randint(1, 700)),
        })
    ids_usuarios = usuarios.insert_many(docs_usuarios).inserted_ids

    # ---- pedidos (referenciam usuário e evento) ----
    docs_pedidos = []
    while len(docs_pedidos) < 60:
        evento = random.choice(docs_eventos)
        setor = random.choice(evento["setores"])
        quantidade = random.randint(1, 4)
        status = random.choice(STATUS)
        if status == "confirmado":
            if setor["vendidos"] + quantidade > setor["capacidade"]:
                continue
            setor["vendidos"] += quantidade  # mantém vendidos coerente com os pedidos confirmados
        docs_pedidos.append({
            "usuarioId": random.choice(ids_usuarios),
            "eventoId": evento["_id"],
            "setor": setor["nome"],
            "quantidade": quantidade,
            "valorTotal": round(setor["preco"] * quantidade, 2),
            "status": status,
            "criadoEm": agora - timedelta(days=random.randint(0, 30), minutes=random.randint(0, 1440)),
        })
    pedidos.insert_many(docs_pedidos)

    # Simula vendas anteriores à plataforma para os relatórios de ocupação ficarem interessantes
    for doc in docs_eventos:
        for setor in doc["setores"]:
            setor["vendidos"] = min(setor["capacidade"], setor["vendidos"] + int(setor["capacidade"] * random.uniform(0, 0.85)))
        eventos.update_one({"_id": doc["_id"]}, {"$set": {"setores": doc["setores"]}})

    print(f"Seed concluído: {len(docs_eventos)} eventos, {len(ids_usuarios)} usuários, {len(docs_pedidos)} pedidos.")


if __name__ == "__main__":
    reset = "--reset" in sys.argv
    if reset:
        eventos.drop()
        usuarios.drop()
        pedidos.drop()
        r.flushdb()
        print("Banco limpo.")

    criar_indices()
    if eventos.estimated_document_count() > 0:
        print("Banco já populado; seed ignorado (use --reset para recriar).")
    else:
        popular()
