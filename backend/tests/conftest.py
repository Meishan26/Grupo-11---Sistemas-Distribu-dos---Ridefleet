import pytest
from app import criar_app
from database import db as _db

@pytest.fixture
def app():
    app = criar_app({
        "TESTING": True,
        "SQLALCHEMY_DATABASE_URI": "sqlite:///:memory:",
        "JWT_SECRET_KEY": "test-secret"
    })

    with app.app_context():
        _db.create_all()
        _popular_banco_teste()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture
def client(app):
    return app.test_client()


@pytest.fixture
def token(client):
    """Retorna token JWT de um passageiro de teste já cadastrado."""
    r = client.post("/auth/login", json={
        "email": "teste@email.com",
        "senha": "123456"
    })
    return r.get_json()["token"]


def _popular_banco_teste():
    from models import Passageiro, Motorista
    from database import db
    from werkzeug.security import generate_password_hash

    p = Passageiro(
        nome="Passageiro Teste",
        email="teste@email.com",
        senha=generate_password_hash("123456")
    )
    m1 = Motorista(nome="Motorista Um",  veiculo="Gol",   placa="AAA1111", status="disponivel")
    m2 = Motorista(nome="Motorista Dois", veiculo="Uno",  placa="BBB2222", status="ocupado")
    m3 = Motorista(nome="Motorista Tres", veiculo="Polo", placa="CCC3333", status="offline")

    db.session.add_all([p, m1, m2, m3])
    db.session.commit()
