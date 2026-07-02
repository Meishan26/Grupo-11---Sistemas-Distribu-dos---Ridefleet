# RideFleet — grupo-11

Serviço distribuído de solicitação de corridas (estilo ride-hailing), desenvolvido para a disciplina SIN 142 (Sistemas Distribuídos). Integra-se ao **RideFleet Core** — um orquestrador central (mantido pelo professor) que faz o _matching_ de corridas entre grupos via leilão, quando o grupo não tem motorista disponível.

## Sumário

- [Arquitetura](#arquitetura)
- [Decisões de projeto](#decisões-de-projeto)
- [Cobertura dos requisitos do roteiro](#cobertura-dos-requisitos-do-roteiro)
- [Como rodar](#como-rodar)
- [Configuração (variáveis de ambiente)](#configuração-variáveis-de-ambiente)
- [Portas](#portas)
- [Testando a API](#testando-a-api)
- [Observabilidade](#observabilidade)
- [Estrutura do repositório](#estrutura-do-repositório)
- [Contribuições e peer review intra-grupo](#contribuições-e-peer-review-intra-grupo)

## Arquitetura

```
                                   |---------------------|
                                   |  RideFleet Core     |  (externo — core)
                                   |  FastAPI · leilão · |
                                   |  locks · saga       |
                                   |---------------------|
                                   webhooks   |   HTTP client
                          (incoming/assigned) | (register/rides/locks/status)
                                              │
                                             ↑|↓
|--------------|         |----------------------------------------|
|   Frontend   |-------> |  nginx (load balancer, least_conn)     |
|  React/Vite  | HTTP    |  porta 5000                            |
|--------------|         |----------------------------------------|
                                |                     |
                                ↓                     ↓
                         |--------------|      |--------------|
                         |  backend1    |      |  backend2    |   Flask, stateless
                         | (INSTANCE_ID)|      | (INSTANCE_ID)|
                         |--------------|      |--------------|
                                ↓                     ↓
                    |=--------------------------------------------|
                    ↓                      ↓                      ↓
             |-------------|       |--------------|       |--------------|
             |  Postgres   |       |  RabbitMQ    |       |  Prometheus  |
             | (corridas,  |       | (fila entrada|       |  + Grafana   |
             | motoristas) |       |  / saída)    |       |  (métricas)  |
             |-------------|       |--------------|       |--------------|
```

**Componentes:**

| Componente                  | Papel                                                                                                                          |
| --------------------------- | ------------------------------------------------------------------------------------------------------------------------------ |
| `backend/app.py`            | Factory Flask, rotas de sistema (`/health`, `/metrics`, `/debug/core`), middleware de latência/log                             |
| `backend/routes/rides.py`   | Ciclo de vida da corrida (solicitar, avançar saga, auditoria) + webhooks do Core (`/rides/incoming`, `/rides/{uuid}/assigned`) |
| `backend/routes/drivers.py` | CRUD de motoristas                                                                                                             |
| `backend/routes/admin.py`   | Painel administrativo (restrito)                                                                                               |
| `backend/core_client.py`    | Cliente HTTP para o Core: registro do grupo, criação de leilão, locks distribuídos, avanço de saga, relógio de Lamport         |
| `backend/fila.py`           | Fila de entrada/saída via RabbitMQ + política de congestionamento                                                              |
| `backend/logger.py`         | Log estruturado em JSON (auditoria causal)                                                                                     |
| `backend/metrics.py`        | Contadores/gauges expostos em `/metrics`                                                                                       |
| `nginx.conf`                | Load balancer entre `backend1`/`backend2` (`least_conn`, retry automático em caso de falha)                                    |
| `ridefleet-frontend/`       | SPA React — solicitação de corrida, acompanhamento, painel admin                                                               |

O serviço roda **duas instâncias de backend** (`backend1`, `backend2`) atrás do nginx, cada uma identificada por `INSTANCE_ID` — isso permite distribuir carga e observar a distribuição via métricas (`label instance_id`), além de dar tolerância a falha de uma instância (nginx tenta a outra automaticamente).

## Decisões de projeto

- **Webhooks nunca respondem 5xx.** Erros internos em `/rides/incoming` e `/rides/{uuid}/assigned` viram recusa silenciosa (204) ou compensação, nunca um erro de servidor — porque o Core tem um circuit breaker por grupo (abre com 2 falhas consecutivas, recovery em 20s) e um 5xx nosso tiraria o grupo dos próximos leilões.
- **Compensação sem liberar o lock.** Quando a confirmação de uma corrida atribuída falha, o backend libera o motorista e cancela a corrida localmente, mas responde `409` **sem** liberar o lock distribuído — deixá-lo expirar naturalmente é o gatilho que faz o Core compensar e re-leiloar a corrida excluindo o grupo, evitando double-booking.
- **Vigia de corridas delegadas.** O Core não envia webhooks de volta para corridas que o próprio grupo delegou (o grupo é excluído do seu próprio leilão). Por isso, uma thread em background (`_vigiar_delegada`) consulta `GET /rides/{uuid}/status` a cada 20s, espelha o estado local e cancela (local + Core) se a corrida não for concluída dentro de `DELEGACAO_TIMEOUT_SEGUNDOS`.
- **Proposta de leilão dinâmica.** ETA cai 30s por motorista livre extra disponível (piso de 120s); preço = bandeirada R$ 5,00 + R$ 2,50/km (distância via fórmula de haversine).
- **Relógio de Lamport** em todo webhook/chamada ao Core, para reconstruir a ordem causal entre eventos de serviços distintos — aplicado de forma tolerante a payload malformado.
- **Painel admin restrito no backend, não só no frontend.** O guard de autorização fica em `routes/admin.py` (`before_request`), então acesso direto à API sem ser a conta administradora recebe 403 mesmo contornando a UI.
- **Rede Docker `ridefleet-net` removida do compose do grupo.** O Core roda na máquina do professor na rede da universidade, não localmente — então o serviço não depende de uma rede Docker compartilhada; a comunicação é via IP real da máquina (`SERVICO_URL`), não nome de container.

## Cobertura dos requisitos do roteiro

Mapeamento de cada frente exigida pelo roteiro da disciplina para onde/como está implementada neste repositório.

### Lógica de negócio central (corridas, motoristas, passageiros)

- **Máquina de estados da corrida** (`request → match → confirm → in_transit → complete`): implementada em [`routes/rides.py`](backend/routes/rides.py). Duas origens alimentam a mesma máquina — corrida local (`/rides/solicitar`) e corrida vencida em leilão (`/rides/{uuid}/assigned`) — ambas chegam em `match` e seguem o mesmo caminho daí em diante. A progressão `match → confirm → in_transit → complete` é automática (thread `_simular_progresso`, com tempos configuráveis por etapa) e também existe uma rota manual (`POST /rides/avancar/{id}`) que só aceita a transição válida seguinte, rejeitando qualquer pulo de estado.
- **Gestão de motoristas**: CRUD completo em [`routes/drivers.py`](backend/routes/drivers.py) (`GET /drivers/`, `GET /drivers/disponiveis`, `POST /drivers/cadastrar`, `PUT /drivers/{id}/status`). Atribuição de corrida usa o primeiro motorista com `status == "disponivel"`, tanto para corrida local quanto para corrida ganha no leilão; ao concluir ou cancelar, o motorista volta a `disponivel`.
- **Gestão de passageiros**: cadastro/login em [`routes/auth.py`](backend/routes/auth.py) (JWT); solicitação de corrida em `POST /rides/solicitar` exige `origem` e `destino`, associados ao passageiro autenticado via token.
- **Pool de corridas / fila local**: [`fila.py`](backend/fila.py) declara duas filas no RabbitMQ (`fila_corridas_entrada`, `fila_corridas_saida`), duráveis e com mensagens persistentes (sobrevivem a restart do serviço) e TTL de 10 min (`x-message-ttl`) como política de descarte de mensagens presas. Toda corrida delegada **ao** Core entra na fila de saída (`_delegar_via_core`); toda corrida recebida **do** Core via `/rides/{uuid}/assigned` entra na fila de entrada — ambas registradas como pool durável assim que a decisão é tomada, sobrevivendo a um restart do serviço no meio do processo. A atribuição de motorista em si continua síncrona dentro do próprio webhook (o contrato com o Core exige resposta imediata, dentro da janela do lock — não dá pra responder de forma assíncrona sem violar esse acordo).
- **Política de overflow**: `esta_congestionado()` em `fila.py` — o serviço se considera congestionado (e delega ao Core) quando **não há motorista livre** (`livres <= 0`) **ou** a fila de saída tem **mais de 5 mensagens pendentes** (`fila_saida > 5`). Critério simples e explícito, versus o par (motoristas livres, tamanho da fila).
- **Testes unitários no CI**: suíte em [`backend/tests/`](backend/tests/) (`test_auth.py`, `test_motoristas.py`, `test_corridas.py`, `test_admin.py`, `test_health.py`, `test_vigia.py`) roda no job `testes-unitarios` do pipeline a cada push/PR (detalhes na seção "Observabilidade + CI/CD" abaixo).

### Logging, monitoramento, fila e load balancer

- **Logging estruturado (JSON)**: [`logger.py`](backend/logger.py) — todo evento de domínio sai como JSON com `timestamp`, `evento`, `corrida_id`, `ride_uuid`, `servico_origem`, `estado_anterior`, `estado_novo`, `lamport_clock`, e requisições HTTP levam `metodo`/`rota`/`status_http`/`duracao_ms`. Três níveis: `INFO` (fluxo normal), `WARN` (degradação — recusa de leilão, deadline expirado, fila cheia), `ERROR` (falha — erro de webhook, erro ao publicar/consumir fila). Por serem JSON linha-a-linha, são consultáveis via `docker logs` + `jq` ou qualquer coletor de log; o campo `lamport_clock` permite correlacionar com o relógio lógico do Core.
- **Health check**: `GET /health` retorna `status` (`UP`/`DEGRADED`/`DOWN` — mesma régua de `_estado_servico()` em `app.py`), `motoristas_disponiveis`, `fila_entrada`, `fila_saida`, `latencia_media_ms`/`latencia_p95_ms`, `uptime_segundos` e `lamport_clock`. Está plugado ao `healthcheck` de cada instância de backend no [`docker-compose.yml`](docker-compose.yml) (`interval: 10s`, `retries: 3`), então o Docker reinicia automaticamente uma instância que pare de responder.
- **Fila de corridas**: RabbitMQ (`fila.py`) — ver detalhes na seção de lógica de negócio acima. Persistência via `durable=True` + `delivery_mode=2`; descarte automático de mensagens presas via TTL de 10 min (não há reprocessamento manual — a mensagem simplesmente expira e some da fila).
- **Load balancer**: nginx ([`nginx.conf`](nginx.conf)) na frente de **duas instâncias** de backend (`backend1`, `backend2`), estratégia `least_conn` (menos conexões ativas primeiro) com `proxy_next_upstream` — se uma instância falhar (erro/timeout/5xx), a requisição é automaticamente reencaminhada para a outra. O Core enxerga só o nginx (porta 5000, `SERVICO_URL`), nunca as instâncias diretamente.

### Integração com o Core + delegação

- **Cliente HTTP do contrato completo**: [`core_client.py`](backend/core_client.py) implementa registro do grupo (`POST /groups/register`), abertura de leilão (`POST /rides`), consulta de status (`GET /rides/{uuid}/status`), consulta de auditoria/log causal (`GET /rides/{uuid}/audit`), locks distribuídos (`POST`/`DELETE /locks/{uuid}`) e avanço de saga (`PATCH /rides/{uuid}/status`) — todos com relógio de Lamport (`_tick`) aplicado a cada chamada.
- **Delegação de saída**: quando `esta_congestionado()` é `True` (ou não há motorista livre), a corrida entra na fila de saída e `_delegar_via_core()` chama `POST /rides` no Core, abrindo o leilão; a corrida guarda o `core_ride_uuid` retornado.
- **Delegação de entrada**: o Core chama `POST /rides/incoming` (o grupo responde com proposta de ETA/preço ou `204` se recusar) e, se vencer, `POST /rides/{uuid}/assigned` — que atribui a corrida a um motorista disponível localmente e confirma a transição `match → confirm` no Core.
- **Testes de contrato**: [`tests/test_contrato.py`](backend/tests/test_contrato.py) simula exatamente as chamadas que o Core faz (`/rides/incoming`, `/rides/{uuid}/assigned`) e valida o formato de `/metrics`, rodando isolado no pipeline antes de qualquer integração real.
- **Containerização**: o serviço sobe com um único `docker compose up -d --build` (dentro de `ridefleet2/`), sem passos manuais — nginx expõe a porta 5000 que é o único ponto de contato esperado pelo Core.
- Nenhuma mensagem de delegação é trocada diretamente entre grupos — toda comunicação de leilão/atribuição passa pelos webhooks e endpoints do Core.

### Front-end

Todas as telas obrigatórias estão implementadas em `ridefleet-frontend/src/pages/`:

| Tela                        | Arquivo           | Observação                                                                                                                      |
| --------------------------- | ----------------- | ------------------------------------------------------------------------------------------------------------------------------- |
| Solicitar corrida           | `RequestRide.jsx` | Formulário com origem/destino                                                                                                   |
| Status em tempo real        | `RideStatus.jsx`  | Polling a cada 3s (`setInterval`); barra de progresso + linha do tempo dos 5 estados; para de atualizar ao chegar em `complete` |
| Indicação de delegação      | `RideStatus.jsx`  | Banner dedicado quando `ride.delegada`, mostrando `servico_origem` e `core_ride_uuid`                                           |
| Acompanhamento do motorista | `RideStatus.jsx`  | Cartão com nome/veículo/placa/ETA; **a área de mapa é um placeholder visual** (`map-placeholder`), não há mapa real integrado   |
| Histórico de corridas       | `RideHistory.jsx` | Lista `GET /rides/minhas` com status e data formatada                                                                           |

### Observabilidade + CI/CD

**Observabilidade** — `GET /metrics` (formato Prometheus/OpenMetrics, [`app.py`](backend/app.py)) expõe todas as métricas exigidas: `ridefleet_rides_local_total`/`_delegated_total`/`_received_total{service}`, `ridefleet_rides_latencia_media_ms`/`_p95_ms` (geral e recortado por `/rides/*`), `ridefleet_throughput_rps` (janela móvel de 60s), `ridefleet_service_state` (0/1/2 — mesma régua do `/health`), `ridefleet_fila_entrada`/`_fila_saida`, e `label instance_id` (`backend1`/`backend2`) para ver a distribuição de carga do load balancer. Grafana próprio provisionado em `grafana/` (porta 3001); quando o Prometheus do Core ganha um job apontando para este serviço, as mesmas métricas aparecem no Grafana do Core rotuladas `service="grupo-11"`.

**CI/CD** — pipeline em 5 estágios encadeados (`needs:`) em [`.github/workflows/ci.yml`](.github/workflows/ci.yml):

1. `build` — build da imagem Docker do backend
2. `testes-unitarios` — pytest (exceto contrato) com cobertura
3. `testes-contrato` — `tests/test_contrato.py`, isolado
4. `teste-integracao` — sobe a stack completa via `docker compose up`, aguarda `/health` ficar saudável, valida presença de todas as métricas obrigatórias em `/metrics`, e faz smoke test dos dois webhooks (`/rides/incoming` retorna proposta; `/assigned` sem Core acessível compensa com `409`)
5. `deploy` — só em push na `main`: publica a imagem no GHCR (`:latest` + `:sha`)

Pull request roda tudo, exceto o deploy.

### Integração entre grupos + resiliência

| Item do checklist                                           | Status                                                                                                                                               |
| ----------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| Sobe via Docker Compose sem intervenção manual              | `docker compose up -d --build`                                                                                                                       |
| Load balancer                                               | nginx + 2 instâncias                                                                                                                                 |
| Delegação de saída (corrida vai pra outro grupo)            | `_delegar_via_core`                                                                                                                                  |
| Delegação de entrada (corrida de outro grupo é aceita)      | webhook `/assigned`                                                                                                                                  |
| Fila de entrada processa corridas delegadas sem perda       | toda corrida recebida por delegação é publicada na fila de entrada (durable + delivery_mode=2) logo após ser aceita — sobrevive a restart do serviço |
| Front-end exibe de qual grupo o motorista veio              | banner de delegação (`servico_origem`) em `RideStatus.jsx`                                                                                           |
| Logs estruturados correlacionáveis com o log causal do Core | JSON com `lamport_clock` em todo evento                                                                                                              |
| Métricas visíveis no Prometheus/Grafana do Core             | (depende do job configurado do lado do Core)                                                                                                         |
| Testes de contrato passando no pipeline                     | estágio dedicado no CI                                                                                                                               |

**Resiliência:**

- Toda chamada ao Core em `core_client.py` está isolada em `try/except`, retornando `None`/`False` em vez de propagar exceção — uma falha de rede com o Core nunca derruba um endpoint do grupo.
- Webhooks (`/rides/incoming`, `/rides/{uuid}/assigned`) nunca respondem `5xx`: erro interno vira recusa silenciosa (`204`) ou compensação (`409`), protegendo o grupo do circuit breaker do Core (evita ser isolado por um erro transitório nosso).
- Se o Core está inacessível durante uma delegação de saída, a corrida não trava indefinidamente: o vigia (`_verificar_corrida_delegada`) cancela a corrida localmente após `DELEGACAO_TIMEOUT_SEGUNDOS` (default 500s), mesmo sem nunca ter recebido `core_ride_uuid`.
- Sob falta de motoristas (`esta_congestionado`), o serviço não recusa a requisição — apenas muda de estratégia (delega ao Core) e mantém `/health` respondendo com `DEGRADED` em vez de cair.
- **Compensação da saga do lado do cliente**: quando uma delegação de saída não conclui dentro do prazo (`_verificar_corrida_delegada`), o vigia primeiro tenta recuperá-la localmente — se surgiu motorista livre nesse meio-tempo, a corrida volta ao pool local (`status = "match"`, motorista atribuído, progresso automático retomado) e o Core é avisado (best-effort) que a delegação foi abandonada. Só cancela de fato quando não há motorista disponível nem no Core, nem localmente.

## Como rodar

Pré-requisitos: Docker + Docker Compose. Para o frontend em modo dev: Node 18+.

```bash
# 1. Configure CORE_URL e SERVICO_URL antes de subir (ver seção abaixo)
cd ridefleet2
docker compose up -d --build
```

Isso sobe: RabbitMQ, Postgres, `backend1`, `backend2`, nginx (load balancer), Prometheus e Grafana. O banco é populado automaticamente no boot (passageiro externo para corridas delegadas, conta admin, 3 motoristas de exemplo).

**Frontend** (fora do Docker, roda em modo dev):

```bash
cd ridefleet-frontend
npm install
npm run dev
```

Usa `VITE_API_URL` (arquivo `.env`) apontando para o nginx (`http://localhost:5000`).

## Configuração (variáveis de ambiente)

Definidas em [`docker-compose.yml`](docker-compose.yml), sobrescrevíveis via variáveis de ambiente do host antes do `docker compose up`:

| Variável                     | Default                          | Descrição                                                                                                                                             |
| ---------------------------- | -------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------------------------- |
| `CORE_URL`                   | `http://10.226.0.45:8080/api/v1` | Endereço do Core (rede da universidade)                                                                                                               |
| `SERVICO_URL`                | `http://10.226.0.87:5000`        | Como o Core alcança este grupo — precisa ser o IP real da máquina na rede da universidade, não `localhost`                                            |
| `SERVICO_NOME`               | `grupo-11`                       | Identificador do grupo — **deve casar com `^[a-z0-9-]+$`** (minúsculas, números, hífen; sem espaço/maiúscula), senão o registro no Core falha com 422 |
| `DELEGACAO_TIMEOUT_SEGUNDOS` | `500`                            | Timeout do vigia de corridas delegadas ao Core                                                                                                        |

Se `SERVICO_URL` não for o IP correto da máquina, o Core não consegue entregar os webhooks de leilão e o grupo fica de fora dos matches.

Para rodar contra um Core local (em vez do Core remoto do professor), é preciso subir `ridefleet-core-sin142/` (`docker compose -f infra/docker-compose.core.yml up -d --build`) e reconectar os serviços à rede `ridefleet-net` (removida por padrão), trocando `CORE_URL`/`SERVICO_URL` para os nomes de container Docker.

## Portas

| Serviço               | URL                                     |
| --------------------- | --------------------------------------- |
| API (via nginx)       | http://localhost:5000                   |
| Frontend (Vite dev)   | http://localhost:5173                   |
| Grafana (grupo)       | http://localhost:3001 (admin/ridefleet) |
| Prometheus (grupo)    | http://localhost:9091                   |
| RabbitMQ mgmt (grupo) | http://localhost:15673 (guest/guest)    |

## Testando a API

**Suíte automatizada** (dentro do container):

```bash
docker exec ridefleet2-backend1-1 python -m pytest tests/ -v
```

**Manual / exploratório:** importe [`ridefleet.postman_collection.json`](ridefleet.postman_collection.json) no Postman — já traz `base_url`, login com salvamento automático de token, e todos os endpoints organizados por área (Auth, Corridas, Motoristas, Webhooks do Core, Sistema, Admin).

Login da conta administradora (acesso a `/admin/*`): `adimin@gmail.com` / `123456` (configurável via `ADMIN_EMAIL`/`ADMIN_SENHA`).

## Observabilidade

`/metrics` expõe métricas no formato Prometheus/OpenMetrics: corridas locais vs. delegadas vs. recebidas, latência (média/p95) geral e por endpoint de corrida, throughput (janela de 60s), estado do serviço (mesma régua do `/health`: 0=UP, 1=DEGRADED, 2=DOWN), filas de entrada/saída, locks adquiridos/expirados, estado do circuit breaker e transições da saga — todas rotuladas por `instance_id` quando aplicável, para visualizar a distribuição de carga entre `backend1`/`backend2`. Consumido pelo Prometheus/Grafana próprios do grupo (`grafana/` traz dashboard pré-provisionado) e, quando configurado no lado do Core, pelo Grafana do professor.

## Estrutura do repositório

```
ridefleet2/
├── backend/
│   ├── app.py                 # factory Flask, rotas de sistema
│   ├── core_client.py         # cliente HTTP do Core
│   ├── fila.py                # RabbitMQ (entrada/saída) + congestionamento
│   ├── logger.py              # log estruturado JSON
│   ├── metrics.py             # contadores Prometheus
│   ├── database.py / models.py
│   ├── routes/                # auth, rides, drivers, admin
│   └── tests/                 # suíte pytest
├── ridefleet-frontend/        # SPA React (Vite)
├── grafana/                   # dashboards + datasource provisionados
├── docker-compose.yml
├── nginx.conf
├── prometheus.yml
└── ridefleet.postman_collection.json
```

## Contribuições

Divisão de trabalho entre os 4 integrantes do grupo-11, por frente do projeto.

| Integrante                 | Área principal                                                                                                                                                                                                           | Contribuições                                                                                                                                                                                                                                                                                                                                                                                                                                     |
| -------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------ | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| **Pessoa 1**               | Lógica de negócio central                                                                                                                                                                                                | Modelagem de dados (`models.py`: Corrida, Motorista, Passageiro); máquina de estados da corrida (`request → match → confirm → in_transit → complete`) em `routes/rides.py`; CRUD e atribuição de motoristas (`routes/drivers.py`); autenticação e gestão de passageiros (`routes/auth.py`); testes unitários (`test_corridas.py`, `test_motoristas.py`, `test_auth.py`)                                                                           |
| **Meishan Huang - 8761**   | Logging estruturado em JSON (`logger.py`); health check e política de overflow/congestionamento (`fila.py`); fila de corridas via RabbitMQ (entrada/saída); painel administrativo (`routes/admin.py` + tela `Admin.jsx`) |
| **Gabriel Menezes - 8763** | Integração com o Core                                                                                                                                                                                                    | Load balancer nginx com 2 instâncias de backend (`nginx.conf`);Cliente HTTP do contrato (`core_client.py`): registro do grupo, leilão, locks distribuídos, avanço de saga, relógio de Lamport; webhooks de leilão (`/rides/incoming`, `/rides/{uuid}/assigned`); lógica de delegação de saída/entrada e vigia de corridas delegadas; testes de contrato (`test_contrato.py`, `test_vigia.py`); compensação de saga e resiliência a falhas do Core |
| **Pessoa 4**               | Front-end + Observabilidade/CI-CD                                                                                                                                                                                        | SPA React completa (`ridefleet-frontend/`: solicitar corrida, status em tempo real, histórico, indicação de delegação); métricas Prometheus (`metrics.py`, endpoint `/metrics`) e dashboards Grafana; pipeline de CI/CD (`.github/workflows/ci.yml`); coleção Postman e documentação do repositório                                                                                                                                               |
