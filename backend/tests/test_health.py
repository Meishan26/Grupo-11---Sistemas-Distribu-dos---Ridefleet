"""Testes do health check e da fila de corridas."""


def test_health_retorna_up(client):
    r = client.get("/health")
    assert r.status_code == 200
    dados = r.get_json()
    assert dados["status"] in ("UP", "DEGRADED", "DOWN")
    assert "motoristas_disponiveis" in dados
    assert "fila_entrada" in dados
    assert "fila_saida" in dados
    assert "latencia_media_ms" in dados


def test_health_motoristas_disponiveis(client):
    r = client.get("/health")
    dados = r.get_json()
    # banco de teste tem 1 disponível
    assert dados["motoristas_disponiveis"] == 1


def test_metrics_retorna_texto(client):
    r = client.get("/metrics")
    assert r.status_code == 200
    assert b"ridefleet_motoristas_disponiveis" in r.data


def test_fila_overflow(client, token):
    """Quando não há motorista, corrida vai para fila de saída."""
    # deixa o motorista disponível ocupado
    lista = client.get("/drivers/").get_json()
    id_disp = next(m["id"] for m in lista if m["status"] == "disponivel")
    client.put(f"/drivers/{id_disp}/status", json={"status": "offline"})

    # agora não tem motorista — corrida vai para fila
    r = client.post("/rides/solicitar",
        json={"origem": "A", "destino": "B"},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 200
    dados = r.get_json()
    # sem motorista disponível
    assert dados["status"] in ("request", "sem_motorista_local")
