"""
Testes do painel administrativo — /admin/* é restrito à conta administradora.
"""


def _login(client, email, senha="123456"):
    r = client.post("/auth/login", json={"email": email, "senha": senha})
    return r.get_json()


def test_admin_sem_token_retorna_401(client):
    """Sem JWT → 401 (rota não é mais pública)."""
    r = client.get("/admin/painel")
    assert r.status_code == 401


def test_admin_usuario_comum_retorna_403(client, token):
    """Passageiro comum logado → 403 (não basta estar autenticado)."""
    r = client.get("/admin/painel", headers={"Authorization": f"Bearer {token}"})
    assert r.status_code == 403


def test_admin_com_conta_admin_retorna_200(client):
    """Conta administradora → acesso liberado ao painel."""
    dados = _login(client, "adimin@gmail.com")
    r = client.get("/admin/painel",
                   headers={"Authorization": f"Bearer {dados['token']}"})
    assert r.status_code == 200
    corpo = r.get_json()
    assert "stats" in corpo
    assert "motoristas" in corpo


def test_login_admin_retorna_flag_is_admin(client):
    """Login do admin deve sinalizar is_admin=True (o frontend usa para a UI)."""
    dados = _login(client, "adimin@gmail.com")
    assert dados.get("is_admin") is True
    assert dados.get("email") == "adimin@gmail.com"


def test_login_comum_nao_e_admin(client):
    """Login de passageiro comum → is_admin=False."""
    dados = _login(client, "teste@email.com")
    assert dados.get("is_admin") is False
