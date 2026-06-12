"""
Fixtures de teste.

Mocks ativos durante todos os testes:
  - fila.*          → evita conexão com RabbitMQ
  - app.tamanho_fila → mesmo motivo (app.py importa diretamente)
  - core_client.*   → evita chamadas HTTP ao Core

Os mocks de core_client são MagicMock — os testes de contrato podem chamar
.assert_called_once(), .reset_mock(), etc. sobre eles.
"""

import pytest
from unittest.mock import patch, MagicMock
from app import criar_app
from database import db as _db
from werkzeug.security import generate_password_hash



# Fila RabbitMQ
_fila_patcher = patch.multiple(
    "fila",
    entrar_na_fila=MagicMock(return_value={"corrida_id": 1, "tipo": "saida"}),
    esta_congestionado=MagicMock(return_value=False),
    tamanho_fila=MagicMock(return_value=0),
    proxima_da_fila=MagicMock(return_value=None),
    descartar_antigas=MagicMock(return_value=0),
)

# tamanho_fila importado diretamente em app.py
_app_fila_patcher = patch("app.tamanho_fila", MagicMock(return_value=0))

# Core HTTP client — MagicMock para permitir assert_called / reset_mock nos testes
_core_patcher = patch.multiple(
    "core_client",
    registrar_grupo=MagicMock(return_value="test-api-key"),
    criar_corrida=MagicMock(return_value="test-ride-uuid"),
    adquirir_lock=MagicMock(return_value=True),
    liberar_lock=MagicMock(return_value=None),
    avancar_status_core=MagicMock(return_value=True),
    status_corrida=MagicMock(return_value=None),
    auditoria_corrida=MagicMock(return_value=None),
)


# Fixtures


@pytest.fixture(scope="function")
def app():
    with _fila_patcher, _app_fila_patcher, _core_patcher:
        application = criar_app({
            "TESTING": True,
            "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
            "JWT_SECRET_KEY": "test-secret",
        })
        with application.app_context():
            _db.create_all()
            _popular_banco_teste()
            yield application
            _db.session.remove()
            _db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def token(client):
    """Token JWT de um passageiro de teste já cadastrado."""
    r = client.post("/auth/login", json={
        "email": "teste@email.com",
        "senha": "123456",
    })
    return r.get_json()["token"]


# Helpers

def _popular_banco_teste():
    from models import Passageiro, Motorista
    db = _db

    passageiro = Passageiro(
        nome="Passageiro Teste",
        email="teste@email.com",
        senha=generate_password_hash("123456"),
    )
    motoristas = [
        Motorista(nome="Motorista Um",   veiculo="Gol",  placa="AAA1111", status="disponivel"),
        Motorista(nome="Motorista Dois", veiculo="Uno",  placa="BBB2222", status="ocupado"),
        Motorista(nome="Motorista Tres", veiculo="Polo", placa="CCC3333", status="offline"),
    ]
    db.session.add(passageiro)
    db.session.add_all(motoristas)
    db.session.commit()
