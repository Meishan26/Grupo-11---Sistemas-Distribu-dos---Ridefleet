from flask import Blueprint, request, jsonify
from models import Motorista
from database import db

drivers_bp = Blueprint("drivers", __name__)


@drivers_bp.route("/", methods=["GET"])
def listar():
    return jsonify([m.to_dict() for m in Motorista.query.all()])


@drivers_bp.route("/disponiveis", methods=["GET"])
def disponiveis():
    return jsonify([m.to_dict() for m in Motorista.query.filter_by(status="disponivel").all()])


@drivers_bp.route("/cadastrar", methods=["POST"])
def cadastrar():
    dados = request.get_json()
    if not dados or not all(k in dados for k in ("nome", "veiculo", "placa")):
        return jsonify({"erro": "nome, veiculo e placa são obrigatórios"}), 400

    m = Motorista(nome=dados["nome"], veiculo=dados["veiculo"], placa=dados["placa"].upper())
    db.session.add(m)
    db.session.commit()
    return jsonify(m.to_dict()), 201


@drivers_bp.route("/<int:id>/status", methods=["PUT"])
def atualizar_status(id):
    m = Motorista.query.get_or_404(id)
    dados = request.get_json()
    if dados.get("status") not in ("disponivel", "ocupado", "offline"):
        return jsonify({"erro": "Status inválido"}), 400
    m.status = dados["status"]
    db.session.commit()
    return jsonify(m.to_dict())
