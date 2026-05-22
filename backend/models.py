from database import db
from datetime import datetime


class Passageiro(db.Model):
    __tablename__ = "passageiros"

    id        = db.Column(db.Integer, primary_key=True)
    nome      = db.Column(db.String(100), nullable=False)
    email     = db.Column(db.String(120), unique=True, nullable=False)
    senha     = db.Column(db.String(200), nullable=False)
    criado_em = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {"id": self.id, "nome": self.nome, "email": self.email}


class Motorista(db.Model):
    __tablename__ = "motoristas"

    id       = db.Column(db.Integer, primary_key=True)
    nome     = db.Column(db.String(100), nullable=False)
    veiculo  = db.Column(db.String(100), nullable=False)
    placa    = db.Column(db.String(10), nullable=False)
    status   = db.Column(db.String(20), default="disponivel")
    # status: disponivel, ocupado, offline

    def to_dict(self):
        return {
            "id": self.id,
            "nome": self.nome,
            "veiculo": self.veiculo,
            "placa": self.placa,
            "status": self.status,
        }


class Corrida(db.Model):
    __tablename__ = "corridas"

    id             = db.Column(db.Integer, primary_key=True)
    passageiro_id  = db.Column(db.Integer, db.ForeignKey("passageiros.id"), nullable=False)
    motorista_id   = db.Column(db.Integer, db.ForeignKey("motoristas.id"), nullable=True)

    origem         = db.Column(db.String(200), nullable=False)
    destino        = db.Column(db.String(200), nullable=False)

    # estados: request -> match -> confirm -> in_transit -> complete
    status         = db.Column(db.String(30), default="request")

    # indica se veio de outro grupo via Core
    delegada       = db.Column(db.Boolean, default=False)
    servico_origem = db.Column(db.String(50), default="local")

    criado_em      = db.Column(db.DateTime, default=datetime.utcnow)
    atualizado_em  = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    passageiro = db.relationship("Passageiro", backref="corridas")
    motorista  = db.relationship("Motorista",  backref="corridas")

    def to_dict(self):
        return {
            "id": self.id,
            "origem": self.origem,
            "destino": self.destino,
            "status": self.status,
            "delegada": self.delegada,
            "servico_origem": self.servico_origem,
            "motorista": self.motorista.to_dict() if self.motorista else None,
            "criado_em": self.criado_em.isoformat() if self.criado_em else None,
        }


class FilaCorrida(db.Model):
    """Fila local de corridas — entrada (delegadas) e saída (overflow)."""
    __tablename__ = "fila_corridas"

    id         = db.Column(db.Integer, primary_key=True)
    corrida_id = db.Column(db.Integer, db.ForeignKey("corridas.id"), nullable=False)
    tipo       = db.Column(db.String(10), nullable=False)  # "entrada" ou "saida"
    status     = db.Column(db.String(20), default="aguardando")  # aguardando, processando, descartada
    tentativas = db.Column(db.Integer, default=0)
    criado_em  = db.Column(db.DateTime, default=datetime.utcnow)

    corrida = db.relationship("Corrida", backref="fila")

    def to_dict(self):
        return {
            "id": self.id,
            "corrida_id": self.corrida_id,
            "tipo": self.tipo,
            "status": self.status,
            "tentativas": self.tentativas,
            "criado_em": self.criado_em.isoformat() if self.criado_em else None,
        }
