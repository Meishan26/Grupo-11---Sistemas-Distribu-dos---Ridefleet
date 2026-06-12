from flask import Blueprint, jsonify, request
from flask_jwt_extended import verify_jwt_in_request, get_jwt_identity
from models import Motorista, Corrida, Passageiro
from routes.auth import ADMIN_EMAIL

admin_bp = Blueprint("admin", __name__)


@admin_bp.before_request
def _exigir_admin():
    """Todas as rotas /admin/* exigem login com a conta administradora.
    A regra vale no backend (não só na UI) para impedir acesso direto à API."""
    # Preflight CORS (OPTIONS) não carrega Authorization — precisa passar
    # para o navegador autorizar a requisição real
    if request.method == "OPTIONS":
        return None

    # Token ausente/expirado/inválido: deixa o flask-jwt-extended responder
    # 401 com a msg padrão, que o interceptor do frontend reconhece
    verify_jwt_in_request()

    passageiro = Passageiro.query.get(int(get_jwt_identity()))
    if not passageiro or passageiro.email != ADMIN_EMAIL:
        return jsonify({"erro": "acesso restrito ao administrador"}), 403


@admin_bp.route("/painel", methods=["GET"])
def painel():
    motoristas = Motorista.query.order_by(Motorista.id).all()

    corridas = Corrida.query.order_by(Corrida.criado_em.desc()).limit(50).all()

    def tipo_corrida(c):
        if not c.delegada:
            return "local"
        if c.servico_origem == "core-auction":
            return "enviada_ao_core"
        return "recebida_do_core"

    corridas_dict = []
    for c in corridas:
        d = c.to_dict()
        d["tipo"] = tipo_corrida(c)
        d["core_ride_uuid"] = c.core_ride_uuid
        d["servico_origem"] = c.servico_origem
        corridas_dict.append(d)

    total_m = len(motoristas)
    disponiveis = sum(1 for m in motoristas if m.status == "disponivel")
    ocupados    = sum(1 for m in motoristas if m.status == "ocupado")
    offline     = sum(1 for m in motoristas if m.status == "offline")

    total_c      = len(corridas)
    locais       = sum(1 for c in corridas if not c.delegada)
    recebidas    = sum(1 for c in corridas if c.delegada and c.servico_origem != "core-auction")
    enviadas     = sum(1 for c in corridas if c.delegada and c.servico_origem == "core-auction")
    em_andamento = sum(1 for c in corridas if c.status not in ("complete", "cancelled"))

    return jsonify({
        "motoristas": [m.to_dict() for m in motoristas],
        "corridas": corridas_dict,
        "stats": {
            "motoristas": {
                "total": total_m,
                "disponivel": disponiveis,
                "ocupado": ocupados,
                "offline": offline,
            },
            "corridas": {
                "total": total_c,
                "locais": locais,
                "recebidas_do_core": recebidas,
                "enviadas_ao_core": enviadas,
                "em_andamento": em_andamento,
            },
        },
    })
