from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import Corrida, Motorista
from database import db
from logger import log_evento
from fila import esta_congestionado, entrar_na_fila, tamanho_fila
import requests as http
import os

rides_bp = Blueprint("rides", __name__)

# URL do Core — definida pelo subgrupo core
CORE_URL = os.getenv("CORE_URL", "http://core:8000")


@rides_bp.route("/solicitar", methods=["POST"])
@jwt_required()
def solicitar():
    passageiro_id = int(get_jwt_identity())
    dados = request.get_json()

    if not dados or not all(k in dados for k in ("origem", "destino")):
        return jsonify({"erro": "origem e destino são obrigatórios"}), 400

    corrida = Corrida(
        passageiro_id=passageiro_id,
        origem=dados["origem"],
        destino=dados["destino"],
        status="request"
    )
    db.session.add(corrida)
    db.session.commit()

    log_evento("corrida_solicitada", corrida_id=corrida.id, estado_novo="request")

    # verifica se está congestionado — se sim, manda pro Core delegar
    if esta_congestionado():
        entrar_na_fila(corrida.id, tipo="saida")
        _delegar_via_core(corrida)
        return jsonify({
            "mensagem": "Serviço ocupado. Corrida sendo delegada via Core.",
            "corrida_id": corrida.id,
            "status": corrida.status
        })

    # tenta atribuir motorista local
    motorista = Motorista.query.filter_by(status="disponivel").first()
    if not motorista:
        entrar_na_fila(corrida.id, tipo="saida")
        return jsonify({
            "mensagem": "Sem motorista disponível. Corrida na fila.",
            "corrida_id": corrida.id,
            "status": "request"
        })

    motorista.status = "ocupado"
    corrida.motorista_id = motorista.id
    corrida.status = "match"
    db.session.commit()

    log_evento("motorista_atribuido", corrida_id=corrida.id,
               estado_anterior="request", estado_novo="match")

    return jsonify({
        "mensagem": "Motorista encontrado!",
        "corrida_id": corrida.id,
        "status": corrida.status,
        "motorista": motorista.to_dict()
    })


def _delegar_via_core(corrida):
    """Envia corrida ao Core para delegação entre grupos."""
    try:
        resp = http.post(f"{CORE_URL}/api/delegar", json={
            "corrida_id": corrida.id,
            "origem": corrida.origem,
            "destino": corrida.destino,
            "servico_solicitante": os.getenv("SERVICO_NOME", "grupo-11")
        }, timeout=5)

        if resp.status_code == 200:
            dados = resp.json()
            corrida.status = "match"
            corrida.delegada = True
            corrida.servico_origem = dados.get("servico_aceito", "desconhecido")
            db.session.commit()
            log_evento("corrida_delegada", corrida_id=corrida.id,
                       servico_origem=corrida.servico_origem, estado_novo="match")
    except Exception as e:
        log_evento("erro_delegacao", corrida_id=corrida.id, nivel="ERROR")


@rides_bp.route("/status/<int:corrida_id>", methods=["GET"])
@jwt_required()
def status(corrida_id):
    corrida = Corrida.query.get_or_404(corrida_id)
    return jsonify(corrida.to_dict())


@rides_bp.route("/avancar/<int:corrida_id>", methods=["POST"])
@jwt_required()
def avancar(corrida_id):
    """Avança o status da corrida: confirm -> in_transit -> complete."""
    corrida = Corrida.query.get_or_404(corrida_id)
    dados = request.get_json()
    novo_status = dados.get("status")

    transicoes = {
        "match": "confirm",
        "confirm": "in_transit",
        "in_transit": "complete"
    }

    if transicoes.get(corrida.status) != novo_status:
        return jsonify({"erro": f"Transição inválida: {corrida.status} -> {novo_status}"}), 400

    anterior = corrida.status
    corrida.status = novo_status

    # libera motorista ao completar
    if novo_status == "complete" and corrida.motorista:
        corrida.motorista.status = "disponivel"

    db.session.commit()
    log_evento("status_atualizado", corrida_id=corrida.id,
               estado_anterior=anterior, estado_novo=novo_status)

    return jsonify(corrida.to_dict())

<<<<<<< HEAD
=======

>>>>>>> 687fc1b53b7fe0cf1124ed72e44d5440524392c0
@rides_bp.route("/minhas", methods=["GET"])
@jwt_required()
def minhas():
    passageiro_id = int(get_jwt_identity())
    corridas = Corrida.query.filter_by(passageiro_id=passageiro_id)\
                            .order_by(Corrida.criado_em.desc()).all()
    return jsonify([c.to_dict() for c in corridas])


# recebe corrida delegada pelo Core
@rides_bp.route("/receber", methods=["POST"])
def receber_delegada():
    """Core manda uma corrida para esse serviço atender."""
    dados = request.get_json()

    motorista = Motorista.query.filter_by(status="disponivel").first()
    if not motorista:
        return jsonify({"aceito": False, "motivo": "sem motorista disponivel"}), 200

    corrida = Corrida(
        passageiro_id=1,  # passageiro externo
        origem=dados.get("origem", ""),
        destino=dados.get("destino", ""),
        status="match",
        delegada=True,
        servico_origem=dados.get("servico_solicitante", "externo"),
        motorista_id=motorista.id
    )
    motorista.status = "ocupado"
    db.session.add(corrida)
    db.session.commit()

    log_evento("corrida_recebida_delegacao", corrida_id=corrida.id,
               servico_origem=corrida.servico_origem, estado_novo="match")

    return jsonify({
        "aceito": True,
        "corrida_id": corrida.id,
        "motorista": motorista.to_dict(),
        "eta": 5
    })
