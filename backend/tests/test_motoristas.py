"""Testes de gestão de motoristas."""


def test_listar_motoristas(client):
    r = client.get("/drivers/")
    assert r.status_code == 200
    lista = r.get_json()
    assert len(lista) == 3


def test_listar_disponiveis(client):
    r = client.get("/drivers/disponiveis")
    assert r.status_code == 200
    lista = r.get_json()
    # só 1 motorista está disponível no banco de teste
    assert len(lista) == 1
    assert lista[0]["status"] == "disponivel"


def test_cadastrar_motorista(client):
    r = client.post("/drivers/cadastrar", json={
        "nome": "Carlos Silva",
        "veiculo": "Corolla",
        "placa": "XYZ9999"
    })
    assert r.status_code == 201
    dados = r.get_json()
    assert dados["nome"] == "Carlos Silva"
    assert dados["placa"] == "XYZ9999"
    assert dados["status"] == "disponivel"


def test_cadastrar_motorista_campos_faltando(client):
    r = client.post("/drivers/cadastrar", json={"nome": "Sem placa"})
    assert r.status_code == 400


def test_atualizar_status_motorista(client):
    # pega o id do primeiro motorista
    lista = client.get("/drivers/").get_json()
    id_motorista = lista[0]["id"]

    r = client.put(f"/drivers/{id_motorista}/status", json={"status": "offline"})
    assert r.status_code == 200
    assert r.get_json()["status"] == "offline"


def test_atualizar_status_invalido(client):
    lista = client.get("/drivers/").get_json()
    id_motorista = lista[0]["id"]

    r = client.put(f"/drivers/{id_motorista}/status", json={"status": "viajem"})
    assert r.status_code == 400
