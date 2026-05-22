"""Testes da lógica de corridas — máquina de estados e fila."""


def test_solicitar_corrida_com_motorista(client, token):
    r = client.post("/rides/solicitar",
        json={"origem": "Rua A, 10", "destino": "Rua B, 20"},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 200
    dados = r.get_json()
    # tem motorista disponível, deve ir para match
    assert dados["status"] == "match"
    assert "motorista" in dados
    assert dados["motorista"] is not None


def test_solicitar_corrida_sem_autenticacao(client):
    r = client.post("/rides/solicitar",
        json={"origem": "Rua A", "destino": "Rua B"}
    )
    assert r.status_code == 401


def test_solicitar_corrida_campos_faltando(client, token):
    r = client.post("/rides/solicitar",
        json={"origem": "Só origem"},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 400


def test_ver_status_corrida(client, token):
    # cria uma corrida primeiro
    r_criar = client.post("/rides/solicitar",
        json={"origem": "A", "destino": "B"},
        headers={"Authorization": f"Bearer {token}"}
    )
    corrida_id = r_criar.get_json()["corrida_id"]

    r = client.get(f"/rides/status/{corrida_id}",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 200
    assert r.get_json()["id"] == corrida_id


def test_avancar_status_corrida(client, token):
    # cria corrida (vai para match)
    r = client.post("/rides/solicitar",
        json={"origem": "A", "destino": "B"},
        headers={"Authorization": f"Bearer {token}"}
    )
    corrida_id = r.get_json()["corrida_id"]

    # avança para confirm
    r2 = client.post(f"/rides/avancar/{corrida_id}",
        json={"status": "confirm"},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert r2.status_code == 200
    assert r2.get_json()["status"] == "confirm"


def test_transicao_invalida(client, token):
    # cria corrida (vai para match)
    r = client.post("/rides/solicitar",
        json={"origem": "A", "destino": "B"},
        headers={"Authorization": f"Bearer {token}"}
    )
    corrida_id = r.get_json()["corrida_id"]

    # tenta pular direto para complete (inválido)
    r2 = client.post(f"/rides/avancar/{corrida_id}",
        json={"status": "complete"},
        headers={"Authorization": f"Bearer {token}"}
    )
    assert r2.status_code == 400
    assert "erro" in r2.get_json()


def test_corrida_completa_libera_motorista(client, token):
    # cria e avança até complete
    r = client.post("/rides/solicitar",
        json={"origem": "A", "destino": "B"},
        headers={"Authorization": f"Bearer {token}"}
    )
    cid = r.get_json()["corrida_id"]
    motorista_id = r.get_json()["motorista"]["id"]

    client.post(f"/rides/avancar/{cid}", json={"status": "confirm"},
        headers={"Authorization": f"Bearer {token}"})
    client.post(f"/rides/avancar/{cid}", json={"status": "in_transit"},
        headers={"Authorization": f"Bearer {token}"})
    client.post(f"/rides/avancar/{cid}", json={"status": "complete"},
        headers={"Authorization": f"Bearer {token}"})

    # motorista deve estar disponível de novo
    r_m = client.get("/drivers/")
    motoristas = r_m.get_json()
    motorista = next(m for m in motoristas if m["id"] == motorista_id)
    assert motorista["status"] == "disponivel"


def test_minhas_corridas(client, token):
    # cria duas corridas
    client.post("/rides/solicitar", json={"origem": "A", "destino": "B"},
        headers={"Authorization": f"Bearer {token}"})
    client.post("/rides/solicitar", json={"origem": "C", "destino": "D"},
        headers={"Authorization": f"Bearer {token}"})

    r = client.get("/rides/minhas",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert r.status_code == 200
    assert len(r.get_json()) >= 1
