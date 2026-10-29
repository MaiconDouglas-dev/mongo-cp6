# TicketFlash — MongoDB + Redis com Python

Checkpoint 3 — Mastering Relational and Non-Relational Database (FIAP, 2TDSPW).

API REST em **Python 3.12 + FastAPI** para uma plataforma de ingressos. O **MongoDB** é a fonte da verdade
(eventos, usuários, pedidos) e o **Redis** cuida do que precisa ser rápido ou temporário (cache, reservas,
ranking, limite de requisições e Pub/Sub).

## Integrantes

| RM | Nome |
|----|------|
| RM561279 | Maicon |
| RM564508 | Lucas |
| RM560907 | João |

## Como executar

Pré-requisito: Docker Desktop.

```bash
docker compose up --build
```

Sobem três serviços: `api` (porta 8000), `mongo` (27017) e `redis` (6379). Ao iniciar, a API roda o
`seed.py` (só popula se o banco estiver vazio: 12 eventos, 20 usuários, 60 pedidos) e cria os índices.

- Documentação interativa (Swagger): http://localhost:8000/docs
- Requisições prontas: [`requests.http`](requests.http)

Comandos úteis:

```bash
docker compose exec api python seed.py --reset   # recria os dados do zero (Mongo + Redis)
docker compose exec api python explain.py         # plano de execução do índice composto
docker compose exec api python subscriber.py      # assinante do Pub/Sub (bônus)
docker compose exec redis redis-cli               # inspecionar chaves no Redis
```

## Estrutura

```
app/
  main.py              # FastAPI, lifespan (cria índices), /health, /usuarios
  db.py                # conexões pymongo + redis-py e criação dos índices
  cache.py             # chaves/TTL do cache, ranking e canal Pub/Sub
  schemas.py           # modelos Pydantic de entrada
  utils.py             # ObjectId/datetime -> JSON
  routers/
    eventos.py         # CRUD, cache-aside, ranking
    reservas.py        # reserva temporária + rate limit
    pedidos.py         # confirmação do pedido (fluxo de compra)
    relatorios.py      # agregações
seed.py                # popula o MongoDB
explain.py             # explain() da consulta com índice composto
subscriber.py          # assinante do canal pedidos:confirmados
requests.http          # coleção de requisições
```

## Endpoints

| Método | Rota | Descrição | Req. |
|--------|------|-----------|------|
| POST | `/eventos` | Cria evento | 2 |
| GET | `/eventos?categoria=&cidade=` | Lista com filtros aplicados na consulta ao Mongo | 2 |
| GET | `/eventos/{id}` | Busca evento (cache-aside, retorna `origem`) + `ZINCRBY` no ranking | 2, 5, 7 |
| PUT | `/eventos/{id}` | Atualiza e invalida `evento:{id}` | 2, 9 |
| DELETE | `/eventos/{id}` | Remove e invalida `evento:{id}` | 2, 9 |
| GET | `/eventos/ranking` | Top 5 mais vistos (Sorted Set) | 7 |
| POST | `/reservas` | Rate limit → checa vagas no Mongo → `SET NX EX 600` | 6, 8, 10 |
| GET | `/reservas/{reservaId}` | Mostra a reserva e o TTL restante | 6 |
| POST | `/pedidos/confirmar` | Confirma reserva: `$inc` condicional + pedido; 410 se expirou | 10 |
| GET | `/pedidos?usuarioId=&status=` | Lista pedidos (usa índice em `usuarioId`) | 3 |
| GET | `/relatorios/faturamento` | Faturamento por evento | 4 |
| GET | `/relatorios/ocupacao/{eventoId}` | % vendido por setor | 4 |
| GET | `/usuarios` | Lista usuários (apoio à demonstração) | — |
| GET | `/health` | Ping no Mongo e no Redis | — |

## Parte 1 — MongoDB

### Req. 1 — Modelagem e justificativa

**`eventos`**
```json
{
  "_id": ObjectId,
  "nome": "Final Copa do Brasil",
  "categoria": "esporte",
  "data": ISODate,
  "local": { "cidade": "São Paulo", "endereco": "Av. Miguel Ignácio Curi, 111", "nome": "Neo Química Arena" },
  "atracoes": ["Corinthians", "Flamengo"],
  "setores": [ { "nome": "Norte", "preco": 180.0, "capacidade": 9000, "vendidos": 4210 } ],
  "times": { "mandante": "Corinthians", "visitante": "Flamengo" }
}
```

- **`local` é subdocumento embutido**: pertence a um único evento, é sempre exibido junto com ele e não é
  consultado sozinho. Embutir evita um `$lookup` em toda leitura.
- **`atracoes` é array embutido**: lista pequena, lida sempre junto com o evento.
- **`setores` é array de subdocumentos embutido**: cada setor só existe dentro do seu evento, o número de
  setores é pequeno e limitado (não cresce sem fim) e, principalmente, o controle de vagas precisa ser
  **atômico**. Como o setor está no mesmo documento do evento, o `update_one` com `$inc` em
  `setores.$.vendidos` e a condição de capacidade no filtro é uma operação atômica de documento único,
  sem precisar de transação.
- **Documento flexível**: cada categoria tem campos próprios (`times` no esporte, `trilhas` em
  conferências, `classificacaoIndicativa` no teatro, `duracaoDias` em festivais) sem alterar esquema.

**`usuarios`**: `nome`, `email` (índice único), `cidade`, `dataCadastro`. Coleção própria porque o
usuário existe independentemente dos eventos e é referenciado por muitos pedidos.

**`pedidos`**
```json
{ "_id": ObjectId, "usuarioId": ObjectId, "eventoId": ObjectId, "setor": "Norte",
  "quantidade": 2, "valorTotal": 360.0, "status": "confirmado", "criadoEm": ISODate }
```

- **Referencia `usuarioId` e `eventoId`** em vez de embutir: pedidos crescem sem limite (embutir no
  usuário ou no evento estouraria o limite de 16 MB e geraria documentos enormes), têm ciclo de vida
  próprio e são consultados isoladamente (histórico do usuário, relatórios). Quando é preciso o nome do
  evento, o relatório usa `$lookup`.
- **`valorTotal` é gravado no pedido** (e não recalculado): o preço do setor pode mudar depois, mas o
  pedido precisa manter o valor efetivamente pago.
- `setor` é guardado pelo nome, pois identifica o subdocumento dentro do evento.

### Req. 2 — CRUD

`insert_one`, `find` (com filtro `categoria` e `local.cidade` montado na própria query), `find_one`,
`update_one` com `$set` parcial e `delete_one` em [`app/routers/eventos.py`](app/routers/eventos.py).

### Req. 3 — Índices

Criados em código por `criar_indices()` ([`app/db.py`](app/db.py)), chamado na inicialização da API e no seed:

| Coleção | Índice | Tipo | Uso |
|---------|--------|------|-----|
| usuarios | `{email: 1}` | único | impede e-mail duplicado |
| eventos | `{categoria: 1, data: 1}` | composto | listagem por categoria ordenada por data |
| eventos | `{"local.cidade": 1}` | simples | filtro por cidade |
| pedidos | `{usuarioId: 1, criadoEm: -1}` | composto | histórico de pedidos do usuário |
| pedidos | `{status: 1, eventoId: 1}` | composto | `$match` do relatório de faturamento |

**Saída do `explain()`** (`docker compose exec api python explain.py`):

```
Consulta: db.eventos.find({categoria: 'show'}).sort({data: 1})

Estágios do plano vencedor: FETCH -> IXSCAN (ix_categoria_data)
Documentos retornados:    3
Chaves de índice lidas:   3
Documentos examinados:    3
Tempo de execução (ms):   0

winningPlan completo:
{
  "stage": "FETCH",
  "inputStage": {
    "stage": "IXSCAN",
    "keyPattern": { "categoria": 1, "data": 1 },
    "indexName": "ix_categoria_data",
    "isMultiKey": false,
    "isUnique": false,
    "direction": "forward",
    "indexBounds": {
      "categoria": [ "[\"show\", \"show\"]" ],
      "data": [ "[MinKey, MaxKey]" ]
    }
  }
}
```

**Leitura do plano:** o estágio é **IXSCAN** (e não COLLSCAN), ou seja, o Mongo percorreu o índice
`ix_categoria_data` só no intervalo `categoria = "show"`. Foram lidas 3 chaves e examinados 3 documentos
para retornar 3 — nenhum documento desnecessário. Como o índice já está ordenado por `data`, **não há
estágio SORT** (ordenação em memória): o resultado sai na ordem certa direto do índice.

### Req. 4 — Agregações ([`app/routers/relatorios.py`](app/routers/relatorios.py))

- **Faturamento por evento** (`GET /relatorios/faturamento`):
  `$match {status: "confirmado"}` → `$group` por `eventoId` somando `valorTotal` → `$lookup` em
  `eventos` → `$unwind` → `$project` com o nome → `$sort {faturamento: -1}`.
- **Ocupação por setor** (`GET /relatorios/ocupacao/{id}`):
  `$match` no evento → `$unwind "$setores"` → `$project` calculando
  `vendidos / capacidade * 100` e vagas disponíveis → `$sort`.

Todo o cálculo é feito no banco; o Python só repassa o resultado.

## Parte 2 — Redis

| Req. | Chave | Estrutura / comandos | Onde |
|------|-------|----------------------|------|
| 5 | `evento:{id}` | String JSON, `GET` / `SET ... EX 60` | `eventos.buscar_evento` |
| 6 | `reserva:{reservaId}` | String JSON, `SET ... NX EX 600` | `reservas.criar_reserva` |
| 7 | `ranking:eventos` | Sorted Set, `ZINCRBY` / `ZREVRANGE 0 4 WITHSCORES` | `eventos.buscar_evento` / `ranking_eventos` |
| 8 | `limite:reservas:{usuarioId}` | String, `INCR` + `EXPIRE 60 NX` | `reservas.verificar_limite` |
| Bônus | `pedidos:confirmados` | Pub/Sub, `PUBLISH` / `SUBSCRIBE` | `pedidos.confirmar_pedido` / `subscriber.py` |

- **Cache (Req. 5)**: o `GET /eventos/{id}` lê o Redis primeiro. Se não houver a chave, busca no Mongo,
  grava com TTL de 60 s e responde `"origem": "banco"`; nas leituras seguintes, `"origem": "cache"`.
- **Reserva (Req. 6)**: `NX` garante que uma reserva existente nunca é sobrescrita; `EX 600` faz a chave
  sumir sozinha em 10 minutos se não for confirmada.
- **Rate limit (Req. 8)**: `INCR` e `EXPIRE NX` vão no mesmo pipeline. O `NX` só define o TTL na primeira
  requisição da janela, então a janela é de 60 s fixos e não é “empurrada” a cada nova chamada. Na 11ª
  reserva no mesmo minuto a API responde **429** com o cabeçalho `Retry-After`.

## Parte 3 — Integração

### Req. 9 — Cache-aside com invalidação
`PUT` e `DELETE /eventos/{id}` gravam no Mongo e em seguida fazem `DEL evento:{id}`. A próxima leitura não
encontra a chave, vai ao banco e repopula o cache. A confirmação de um pedido também invalida o cache do
evento, pois `vendidos` mudou — assim o usuário nunca vê vagas desatualizadas.

### Req. 10 — Fluxo de compra
1. `POST /reservas`: verifica o limite (Redis) → confere no Mongo se usuário, evento e setor existem e se há
   vagas → cria `reserva:{id}` com `SET NX EX 600`.
2. `POST /pedidos/confirmar`: lê **e apaga** a reserva com `GETDEL` (atômico — duas confirmações
   simultâneas da mesma reserva não geram dois pedidos). Se não existir, responde **410 Gone** e nada é
   gravado.
3. Incrementa `vendidos` com um `$inc` **condicional e atômico**:

   ```python
   eventos.update_one(
       {"_id": evento_id,
        "setores": {"$elemMatch": {"nome": setor, "vendidos": {"$lte": capacidade - quantidade}}}},
       {"$inc": {"setores.$.vendidos": quantidade}},
   )
   ```
   A condição de capacidade está no filtro: se não houver vagas, nenhum documento casa, nada é alterado e
   a API responde **409**. Como é uma operação de documento único, não há condição de corrida.
4. Grava o pedido com `status: "confirmado"` e publica no canal `pedidos:confirmados`.

## Demonstração

```bash
# 1. Subir o ambiente
docker compose up --build

# Pegar ids
curl -s localhost:8000/eventos | python3 -m json.tool | head -30
curl -s localhost:8000/usuarios | python3 -m json.tool | head -10

# 2. Cache: 1ª chamada "banco", 2ª "cache"
curl -s localhost:8000/eventos/<EVENTO_ID>
curl -s localhost:8000/eventos/<EVENTO_ID>
docker compose exec redis redis-cli TTL evento:<EVENTO_ID>

# 3. Atualizar e ver a leitura voltar ao banco
curl -s -X PUT localhost:8000/eventos/<EVENTO_ID> -H 'Content-Type: application/json' -d '{"nome":"Novo nome"}'
curl -s localhost:8000/eventos/<EVENTO_ID>

# 4. Reserva com TTL e confirmação
curl -s -X POST localhost:8000/reservas -H 'Content-Type: application/json' \
  -d '{"usuarioId":"<USUARIO_ID>","eventoId":"<EVENTO_ID>","setor":"Pista","quantidade":2}'
docker compose exec redis redis-cli TTL reserva:<RESERVA_ID>
curl -s -X POST localhost:8000/pedidos/confirmar -H 'Content-Type: application/json' -d '{"reservaId":"<RESERVA_ID>"}'

# 5. Reserva expirada -> 410 (para não esperar 10 min, encurtamos o TTL de uma reserva nova)
docker compose exec redis redis-cli EXPIRE reserva:<OUTRA_RESERVA_ID> 1
curl -s -i -X POST localhost:8000/pedidos/confirmar -H 'Content-Type: application/json' -d '{"reservaId":"<OUTRA_RESERVA_ID>"}'

# 6. 11 reservas seguidas -> a 11ª retorna 429
for i in $(seq 1 11); do
  curl -s -o /dev/null -w "%{http_code}\n" -X POST localhost:8000/reservas -H 'Content-Type: application/json' \
    -d '{"usuarioId":"<USUARIO_ID>","eventoId":"<EVENTO_ID>","setor":"Pista","quantidade":1}'
done

# 7. Ranking e relatórios
curl -s localhost:8000/eventos/ranking
curl -s localhost:8000/relatorios/faturamento
curl -s localhost:8000/relatorios/ocupacao/<EVENTO_ID>
```

> Dica: também é possível subir com `RESERVA_TTL=30` no `environment` da `api` para ver a reserva expirar
> naturalmente durante a demonstração.

## Tecnologias

Python 3.12 · FastAPI · Uvicorn · pymongo 4 · redis-py 5 · MongoDB 7 · Redis 7 · Docker Compose
