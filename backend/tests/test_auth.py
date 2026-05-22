"""Testes de autenticação — cadastro e login."""


def test_cadastro_ok(client):
    r = client.post("/auth/cadastro", json={
        "nome": "Novo Usuario",
        "email": "novo@email.com",
        "senha": "senha123"
    })
    assert r.status_code == 201
    assert r.get_json()["mensagem"] == "Conta criada!"


def test_cadastro_email_duplicado(client):
    # tenta cadastrar o mesmo email duas vezes
    dados = {"nome": "A", "email": "dup@email.com", "senha": "123456"}
    client.post("/auth/cadastro", json=dados)
    r = client.post("/auth/cadastro", json=dados)
    assert r.status_code == 409
    assert "erro" in r.get_json()


def test_cadastro_campos_faltando(client):
    r = client.post("/auth/cadastro", json={"nome": "Sem email"})
    assert r.status_code == 400


def test_login_ok(client):
    r = client.post("/auth/login", json={
        "email": "teste@email.com",
        "senha": "123456"
    })
    assert r.status_code == 200
    dados = r.get_json()
    assert "token" in dados
    assert dados["nome"] == "Passageiro Teste"


def test_login_senha_errada(client):
    r = client.post("/auth/login", json={
        "email": "teste@email.com",
        "senha": "senhaerrada"
    })
    assert r.status_code == 401
    assert "erro" in r.get_json()


def test_login_email_inexistente(client):
    r = client.post("/auth/login", json={
        "email": "naoexiste@email.com",
        "senha": "123456"
    })
    assert r.status_code == 401
