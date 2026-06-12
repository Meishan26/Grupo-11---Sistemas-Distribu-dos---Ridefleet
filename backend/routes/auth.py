import os
from flask import Blueprint, request, jsonify
from flask_jwt_extended import create_access_token
from werkzeug.security import generate_password_hash, check_password_hash
from models import Passageiro
from database import db
from logger import log_evento

auth_bp = Blueprint("auth", __name__)

# Conta com acesso ao painel administrativo (/admin/*)
ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "adimin@gmail.com")


@auth_bp.route("/cadastro", methods=["POST"])
def cadastro():
    dados = request.get_json()
    if not dados or not all(k in dados for k in ("nome", "email", "senha")):
        return jsonify({"erro": "nome, email e senha são obrigatórios"}), 400

    if Passageiro.query.filter_by(email=dados["email"]).first():
        return jsonify({"erro": "Email já cadastrado"}), 409

    p = Passageiro(
        nome=dados["nome"],
        email=dados["email"],
        senha=generate_password_hash(dados["senha"])
    )
    db.session.add(p)
    db.session.commit()
    log_evento("passageiro_cadastrado")
    return jsonify({"mensagem": "Conta criada!", "passageiro": p.to_dict()}), 201


@auth_bp.route("/login", methods=["POST"])
def login():
    dados = request.get_json()
    if not dados or not all(k in dados for k in ("email", "senha")):
        return jsonify({"erro": "email e senha são obrigatórios"}), 400

    p = Passageiro.query.filter_by(email=dados["email"]).first()
    if not p or not check_password_hash(p.senha, dados["senha"]):
        return jsonify({"erro": "Email ou senha incorretos"}), 401

    token = create_access_token(identity=str(p.id))
    log_evento("login_realizado")
    return jsonify({
        "token":    token,
        "nome":     p.nome,
        "id":       p.id,
        "email":    p.email,
        "is_admin": p.email == ADMIN_EMAIL,
    })
