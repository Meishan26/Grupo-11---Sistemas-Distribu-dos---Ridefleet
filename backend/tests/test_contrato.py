"""
Testes de contrato local — simulam exatamente as chamadas que o Core faz.

Execute antes da integração real:
    pytest tests/test_contrato.py -v

Estes testes garantem que os webhooks /rides/incoming e /rides/{uuid}/assigned
respondem no formato correto esperado pelo Core (OpenAPI v0.4.x).
"""

import core_client


# POST /rides/incoming  — oferta de leilão (scatter-gather)


def test_incoming_com_motorista_responde_proposta(client):
    """Com motorista disponível → 200 com estimatedEta, estimatedPrice e logicalTimestamp."""
    r = client.post("/rides/incoming", json={
        "rideUuid":        "uuid-leilao-1",
        "origin":          {"lat": -20.75, "lng": -42.88, "street": "Rua A, 10"},
        "destination":     {"lat": -20.80, "lng": -42.90, "street": "Rua B, 5"},
        "originServiceId": "grupo-origem",
        "passengerId":     "passageiro-externo-1",
        "logicalTimestamp": 5,
        "auctionDeadline": "2026-12-31T23:59:00Z",
    })
    assert r.status_code == 200
    dados = r.get_json()
    assert "estimatedEta"     in dados, "campo estimatedEta ausente"
    assert "estimatedPrice"   in dados, "campo estimatedPrice ausente"
    assert "logicalTimestamp" in dados, "campo logicalTimestamp ausente"
    assert dados["estimatedEta"]   > 0,  "ETA deve ser positivo"
    assert dados["estimatedPrice"] >= 0, "preço não pode ser negativo"
    assert isinstance(dados["logicalTimestamp"], int), "logicalTimestamp deve ser inteiro"


def test_incoming_sem_motorista_recusa_com_204(client):
    """Sem motorista disponível → 204 No Content (recusa silenciosa)."""
    # desabilita o único motorista disponível
    motoristas = client.get("/drivers/").get_json()
    id_disp = next((m["id"] for m in motoristas if m["status"] == "disponivel"), None)
    if id_disp:
        client.put(f"/drivers/{id_disp}/status", json={"status": "offline"})

    r = client.post("/rides/incoming", json={
        "rideUuid":        "uuid-sem-cap",
        "origin":          {"lat": 0, "lng": 0, "street": "Rua X"},
        "destination":     {"lat": 0, "lng": 0, "street": "Rua Y"},
        "originServiceId": "grupo-z",
        "passengerId":     "p-ext",
        "logicalTimestamp": 2,
        "auctionDeadline": "2026-12-31T23:59:00Z",
    })
    assert r.status_code == 204
    assert r.data == b"", "corpo deve estar vazio no 204"


def test_incoming_sem_body_nao_quebra(client):
    """Chamada malformada não deve gerar 500."""
    r = client.post("/rides/incoming", data="", content_type="application/json")
    assert r.status_code in (200, 204, 400)


def test_incoming_deadline_expirado_recusa_com_204(client):
    """auctionDeadline no passado → proposta seria ignorada → recusa 204."""
    r = client.post("/rides/incoming", json={
        "rideUuid":        "uuid-deadline-velho",
        "origin":          {"lat": 0, "lng": 0, "street": "Rua X"},
        "destination":     {"lat": 0, "lng": 0, "street": "Rua Y"},
        "originServiceId": "grupo-z",
        "passengerId":     "p-ext",
        "logicalTimestamp": 4,
        "auctionDeadline": "2020-01-01T00:00:00Z",
    })
    assert r.status_code == 204


def test_incoming_timestamp_invalido_nao_gera_500(client):
    """logicalTimestamp não numérico não pode derrubar o webhook (nada de 5xx)."""
    r = client.post("/rides/incoming", json={
        "rideUuid":        "uuid-ts-invalido",
        "origin":          {"lat": 0, "lng": 0, "street": "Rua X"},
        "destination":     {"lat": 0, "lng": 0, "street": "Rua Y"},
        "originServiceId": "grupo-z",
        "passengerId":     "p-ext",
        "logicalTimestamp": "nao-e-numero",
        "auctionDeadline": "2026-12-31T23:59:00Z",
    })
    assert r.status_code in (200, 204)


def test_incoming_preco_cresce_com_distancia(client):
    """Proposta dinâmica: corrida mais longa deve custar mais que a curta."""
    base = {
        "originServiceId": "grupo-z",
        "passengerId":     "p-ext",
        "logicalTimestamp": 6,
        "auctionDeadline": "2026-12-31T23:59:00Z",
    }
    curta = client.post("/rides/incoming", json={
        **base,
        "rideUuid":    "uuid-curta",
        "origin":      {"lat": -20.75, "lng": -42.88},
        "destination": {"lat": -20.75, "lng": -42.88},
    }).get_json()
    longa = client.post("/rides/incoming", json={
        **base,
        "rideUuid":    "uuid-longa",
        "origin":      {"lat": -20.75, "lng": -42.88},
        "destination": {"lat": -21.75, "lng": -43.88},
    }).get_json()
    assert longa["estimatedPrice"] > curta["estimatedPrice"]


# POST /rides/{rideUuid}/assigned  

def test_assigned_aceita_e_cria_corrida_local(client):
    """Com motorista disponível → 200, aceito=True e corrida_id no corpo."""
    r = client.post("/rides/uuid-ganhou-123/assigned", json={
        "rideUuid":        "uuid-ganhou-123",
        "origin":          {"lat": -20.75, "lng": -42.88, "street": "Av. Central, 1"},
        "destination":     {"lat": -20.80, "lng": -42.90, "street": "Rua Norte, 99"},
        "passengerId":     "passageiro-externo-2",
        "originServiceId": "grupo-solicitante",
        "logicalTimestamp": 8,
        "lockExpiresAt":   "2026-12-31T23:59:00Z",
    })
    assert r.status_code == 200
    dados = r.get_json()
    assert dados.get("aceito") is True, "campo aceito deve ser True"
    assert "corrida_id" in dados,        "corrida_id deve estar presente"
    assert isinstance(dados["corrida_id"], int)


def test_assigned_sem_motorista_retorna_409(client):
    """Sem motorista → 409 (Core deve re-leiloar excluindo este grupo)."""
    motoristas = client.get("/drivers/").get_json()
    id_disp = next((m["id"] for m in motoristas if m["status"] == "disponivel"), None)
    if id_disp:
        client.put(f"/drivers/{id_disp}/status", json={"status": "offline"})

    r = client.post("/rides/uuid-sem-cap-999/assigned", json={
        "rideUuid":        "uuid-sem-cap-999",
        "origin":          {"lat": 0, "lng": 0, "street": "Rua A"},
        "destination":     {"lat": 0, "lng": 0, "street": "Rua B"},
        "passengerId":     "p-ext",
        "originServiceId": "grupo-x",
        "logicalTimestamp": 3,
        "lockExpiresAt":   "2026-12-31T23:59:00Z",
    })
    assert r.status_code == 409


def test_assigned_propaga_lock_e_confirm(client):
    """Ao aceitar, o serviço deve ter chamado adquirir_lock e avancar_status_core."""
    from unittest.mock import call
    import core_client as cc

    cc.adquirir_lock.reset_mock()
    cc.avancar_status_core.reset_mock()

    client.post("/rides/uuid-lock-test/assigned", json={
        "rideUuid":        "uuid-lock-test",
        "origin":          {"lat": 0, "lng": 0, "street": "Rua A"},
        "destination":     {"lat": 0, "lng": 0, "street": "Rua B"},
        "passengerId":     "p-ext",
        "originServiceId": "grupo-x",
        "logicalTimestamp": 10,
        "lockExpiresAt":   "2026-12-31T23:59:00Z",
    })

    cc.adquirir_lock.assert_called_once_with("uuid-lock-test", ttl=60)
    cc.avancar_status_core.assert_called_once_with("uuid-lock-test", "confirm")


def _payload_assigned(uuid, lock_expires="2026-12-31T23:59:00Z"):
    return {
        "rideUuid":        uuid,
        "origin":          {"lat": 0, "lng": 0, "street": "Rua A"},
        "destination":     {"lat": 0, "lng": 0, "street": "Rua B"},
        "passengerId":     "p-ext",
        "originServiceId": "grupo-x",
        "logicalTimestamp": 12,
        "lockExpiresAt":   lock_expires,
    }


def _motorista_um_disponivel(client):
    """True se algum motorista voltou ao estado disponivel."""
    motoristas = client.get("/drivers/").get_json()
    return any(m["status"] == "disponivel" for m in motoristas)


def test_assigned_idempotente_nao_duplica_corrida(client):
    """Callback repetido (retry do Core) → mesma corrida, sem duplicar."""
    r1 = client.post("/rides/uuid-idem/assigned", json=_payload_assigned("uuid-idem"))
    r2 = client.post("/rides/uuid-idem/assigned", json=_payload_assigned("uuid-idem"))
    assert r1.status_code == 200
    assert r2.status_code == 200
    assert r2.get_json()["corrida_id"] == r1.get_json()["corrida_id"]


def test_assigned_renovacao_falha_mas_lock_transferido_vale(client):
    """Renovação de lock falhou, mas lockExpiresAt ainda no futuro → prossegue."""
    import core_client as cc
    cc.adquirir_lock.return_value = False
    try:
        r = client.post("/rides/uuid-lock-herdado/assigned",
                        json=_payload_assigned("uuid-lock-herdado"))
        assert r.status_code == 200
        assert r.get_json()["aceito"] is True
    finally:
        cc.adquirir_lock.return_value = True


def test_assigned_lock_indisponivel_compensa_e_recusa(client):
    """Renovação falhou e lock transferido já expirou → 409 e motorista liberado."""
    import core_client as cc
    cc.adquirir_lock.return_value = False
    try:
        r = client.post(
            "/rides/uuid-lock-perdido/assigned",
            json=_payload_assigned("uuid-lock-perdido",
                                   lock_expires="2020-01-01T00:00:00Z"),
        )
        assert r.status_code == 409
        assert _motorista_um_disponivel(client), \
            "compensação local deve devolver o motorista ao estado disponivel"
    finally:
        cc.adquirir_lock.return_value = True


def test_assigned_confirm_rejeitado_compensa_e_recusa(client):
    """PATCH confirm falhou (com retry) → 409, motorista liberado e lock
    deixado expirar para o Core compensar e re-leiloar."""
    import core_client as cc
    cc.avancar_status_core.return_value = False
    cc.liberar_lock.reset_mock()
    try:
        r = client.post("/rides/uuid-confirm-falhou/assigned",
                        json=_payload_assigned("uuid-confirm-falhou"))
        assert r.status_code == 409
        assert _motorista_um_disponivel(client), \
            "compensação local deve devolver o motorista ao estado disponivel"
        # lock NÃO deve ser liberado — expirar é o gatilho da compensação no Core
        cc.liberar_lock.assert_not_called()
    finally:
        cc.avancar_status_core.return_value = True



# Lamport clock


def test_lamport_clock_atualiza_em_incoming(client):
    """logicalTimestamp recebido deve atualizar o relógio local: max(local, remoto)+1."""
    clock_antes = core_client.get_clock()
    ts_remoto   = clock_antes + 50

    client.post("/rides/incoming", json={
        "rideUuid":        "uuid-clock-test",
        "origin":          {"lat": 0, "lng": 0},
        "destination":     {"lat": 0, "lng": 0},
        "originServiceId": "grupo-x",
        "passengerId":     "p-1",
        "logicalTimestamp": ts_remoto,
        "auctionDeadline": "2026-12-31T23:59:00Z",
    })
    assert core_client.get_clock() >= ts_remoto + 1, \
        "relógio deve ser max(local, remoto) + 1"


# Delegação de saída — corrida gerada localmente vai ao Core

def test_delegacao_saida_sem_motorista_chama_core(client, token):
    """Sem motorista disponível → core.criar_corrida deve ser chamado."""
    import core_client as cc
    cc.criar_corrida.reset_mock()

    motoristas = client.get("/drivers/").get_json()
    id_disp = next((m["id"] for m in motoristas if m["status"] == "disponivel"), None)
    if id_disp:
        client.put(f"/drivers/{id_disp}/status", json={"status": "offline"})

    client.post("/rides/solicitar",
                json={"origem": "Rua A", "destino": "Rua B"},
                headers={"Authorization": f"Bearer {token}"})

    cc.criar_corrida.assert_called_once(), \
        "toda delegação deve passar pelo Core (criar_corrida deve ter sido chamado)"


def test_delegacao_saida_nunca_e_direta(client, token):
    """Verifica que não há chamada direta a outros serviços — só ao Core."""

    import core_client as cc
    cc.criar_corrida.reset_mock()

    motoristas = client.get("/drivers/").get_json()
    id_disp = next((m["id"] for m in motoristas if m["status"] == "disponivel"), None)
    if id_disp:
        client.put(f"/drivers/{id_disp}/status", json={"status": "offline"})

    client.post("/rides/solicitar",
                json={"origem": "Ponto X", "destino": "Ponto Y"},
                headers={"Authorization": f"Bearer {token}"})

    assert cc.criar_corrida.call_count == 1, \
        "apenas core.criar_corrida deve ser chamado para delegação"



# /health — compatibilidade com circuit breaker do Core

def test_health_campos_obrigatorios(client):
    """O /health deve ter os campos que o Core usa para circuit breaker."""
    r = client.get("/health")
    assert r.status_code == 200
    dados = r.get_json()
    assert "status"  in dados
    assert dados["status"] in ("UP", "DEGRADED", "DOWN")
    assert "motoristas_disponiveis" in dados
    assert "fila_entrada"           in dados
    assert "fila_saida"             in dados
    assert "lamport_clock"          in dados


def test_metrics_formato_prometheus(client):
    """O /metrics deve estar no formato texto Prometheus."""
    r = client.get("/metrics")
    assert r.status_code == 200
    assert r.content_type == "text/plain; charset=utf-8"
    texto = r.data.decode()
    assert "ridefleet_motoristas_disponiveis" in texto
    assert "ridefleet_fila_entrada"           in texto
    assert "ridefleet_fila_saida"             in texto
    assert "ridefleet_lamport_clock"          in texto


def test_metrics_observabilidade_completa(client):
    """Checklist de observabilidade: todas as métricas mínimas expostas."""
    texto = client.get("/metrics").data.decode()
    obrigatorias = [
        "ridefleet_rides_local_total",        # corridas locais
        "ridefleet_rides_delegated_total",    # delegadas para fora
        "ridefleet_rides_received_total",     # recebidas de outros grupos
        "ridefleet_rides_latencia_media_ms",  # latência dos endpoints de corrida
        "ridefleet_rides_latencia_p95_ms",
        "ridefleet_throughput_rps",           # throughput (req/s)
        "ridefleet_service_state",            # disponível / congestionado
        "ridefleet_fila_entrada",             # filas de entrada e saída
        "ridefleet_fila_saida",
        'instance_id="',                      # distribuição entre instâncias
    ]
    for metrica in obrigatorias:
        assert metrica in texto, f"métrica ausente no /metrics: {metrica}"


def test_metrics_rides_received_incrementa_apos_assigned(client):
    """Ganhar um leilão (webhook /assigned) conta como corrida recebida."""
    import re

    def valor_received():
        texto = client.get("/metrics").data.decode()
        m = re.search(r"ridefleet_rides_received_total\{[^}]*\}\s+(\d+)", texto)
        return int(m.group(1)) if m else 0

    antes = valor_received()
    r = client.post("/rides/uuid-metrica-recebida/assigned",
                    json=_payload_assigned("uuid-metrica-recebida"))
    assert r.status_code == 200
    assert valor_received() == antes + 1
