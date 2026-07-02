import os
import threading
import time
from datetime import datetime, timedelta, timezone
from math import asin, cos, radians, sin, sqrt
from flask import Blueprint, request, jsonify, current_app
from flask_jwt_extended import jwt_required, get_jwt_identity
from models import Corrida, Motorista
from database import db
from logger import log_evento
from fila import esta_congestionado, entrar_na_fila
import core_client as core
import metrics as _m

rides_bp = Blueprint("rides", __name__)

# Segundos entre cada etapa da simulação local
_TEMPOS = {
    "match":      3,   # match     → confirm    (motorista aceita)
    "confirm":    6,   # confirm   → in_transit (motorista chegou)
    "in_transit": 12,  # in_transit → complete  (corrida encerrada)
}
_PROXIMA = {"match": "confirm", "confirm": "in_transit", "in_transit": "complete"}


# Simulação de progresso automático da corrida
def _simular_progresso(corrida_id, status_inicial, app):
    """Thread que avança automaticamente a saga local, etapa a etapa."""
    status_atual = status_inicial
    while status_atual in _PROXIMA:
        espera = _TEMPOS.get(status_atual, 5)
        time.sleep(espera)

        with app.app_context():
            corrida = Corrida.query.get(corrida_id)
            # Interrompe se a corrida sumiu ou foi alterada externamente
            if corrida is None or corrida.status != status_atual:
                break

            proximo = _PROXIMA[status_atual]
            anterior = corrida.status
            corrida.status = proximo
            _m.registrar_transicao(anterior, proximo)

            if proximo == "complete" and corrida.motorista:
                corrida.motorista.status = "disponivel"
                if corrida.core_ride_uuid:
                    core.liberar_lock(corrida.core_ride_uuid)

            db.session.commit()
            log_evento("status_auto", corrida_id=corrida_id,
                       estado_anterior=anterior, estado_novo=proximo)

            # Propaga ao Core se corrida for delegada
            if corrida.core_ride_uuid and proximo in ("confirm", "in_transit", "complete"):
                core.adquirir_lock(corrida.core_ride_uuid, ttl=60)
                core.avancar_status_core(corrida.core_ride_uuid, proximo)

        status_atual = proximo


def _iniciar_progresso(corrida_id, status_inicial):
    """Dispara a thread de simulação em background."""
    app = current_app._get_current_object()
    t = threading.Thread(
        target=_simular_progresso,
        args=(corrida_id, status_inicial, app),
        daemon=True,
    )
    t.start()


# Vigia de corridas delegadas ao Core
# O Core não chama os webhooks deste grupo para corridas que ELE recebeu de
# nós (somos excluídos do próprio leilão). Então quem acompanha a corrida
# delegada é este vigia: espelha o estado remoto e, se a corrida não concluir
# dentro do prazo, cancela local e remotamente.

_TIMEOUT_DELEGACAO_S = int(os.getenv("DELEGACAO_TIMEOUT_SEGUNDOS", "500"))
_INTERVALO_VIGIA_S   = 20
_ESTADOS_TERMINAIS   = ("complete", "cancelled")
_ESTADOS_CONHECIDOS  = ("request", "match", "confirm", "in_transit",
                        "complete", "cancelled")


def _verificar_corrida_delegada(corrida):
    """Um passo do vigia. Espelha o estado do Core na corrida local e cancela
    se o prazo de conclusão estourou. Retorna True quando a corrida chegou a
    um estado terminal e o vigia pode parar."""
    if corrida.status in _ESTADOS_TERMINAIS:
        return True

    # Outro grupo executa a corrida; o Core é a fonte da verdade do estado
    if corrida.core_ride_uuid:
        info = core.status_corrida(corrida.core_ride_uuid)
        estado_core = (info or {}).get("state")
        if estado_core in _ESTADOS_CONHECIDOS and estado_core != corrida.status:
            anterior = corrida.status
            corrida.status = estado_core
            db.session.commit()
            log_evento("status_espelhado_core", corrida_id=corrida.id,
                       ride_uuid=corrida.core_ride_uuid,
                       estado_anterior=anterior, estado_novo=estado_core)
        if corrida.status in _ESTADOS_TERMINAIS:
            return True

    # Sem conclusão dentro do prazo: antes de desistir, tenta recuperar a
    # corrida localmente — se surgiu motorista livre nesse meio-tempo, ela
    # volta ao pool local em vez de simplesmente cancelar.
    prazo = corrida.criado_em + timedelta(seconds=_TIMEOUT_DELEGACAO_S)
    if datetime.utcnow() >= prazo:
        motorista = Motorista.query.filter_by(status="disponivel").first()
        if motorista:
            anterior = corrida.status
            motorista.status = "ocupado"
            corrida.motorista_id = motorista.id
            corrida.status = "match"
            db.session.commit()
            log_evento("corrida_delegada_recuperada_localmente", corrida_id=corrida.id,
                       ride_uuid=corrida.core_ride_uuid,
                       estado_anterior=anterior, estado_novo="match", nivel="WARN")
            if corrida.core_ride_uuid:
                # Best-effort: avisa o Core que desistimos da delegação. O
                # motorista já foi reservado localmente independente do
                # resultado dessa chamada.
                core.avancar_status_core(corrida.core_ride_uuid, "cancelled")
            _iniciar_progresso(corrida.id, "match")
            return True

        # Ninguém livre nem no Core, nem localmente → cancela de fato.
        anterior = corrida.status
        corrida.status = "cancelled"
        db.session.commit()
        log_evento("corrida_delegada_timeout", corrida_id=corrida.id,
                   ride_uuid=corrida.core_ride_uuid,
                   timeout_s=_TIMEOUT_DELEGACAO_S,
                   estado_anterior=anterior, estado_novo="cancelled",
                   nivel="WARN")
        if corrida.core_ride_uuid:
            core.adquirir_lock(corrida.core_ride_uuid, ttl=30)
            core.avancar_status_core(corrida.core_ride_uuid, "cancelled")
        return True

    return False


def _vigiar_delegada(corrida_id, app):
    """Thread que acompanha uma corrida delegada até concluir ou estourar o prazo."""
    while True:
        with app.app_context():
            corrida = Corrida.query.get(corrida_id)
            if corrida is None or _verificar_corrida_delegada(corrida):
                return
        time.sleep(_INTERVALO_VIGIA_S)


def _iniciar_vigia(corrida_id):
    """Dispara a thread do vigia em background."""
    app = current_app._get_current_object()
    t = threading.Thread(target=_vigiar_delegada, args=(corrida_id, app), daemon=True)
    t.start()


def retomar_corridas_pendentes(app):
    """Chamada no boot: retoma threads para corridas presas em estados transitórios."""
    with app.app_context():
        pendentes = Corrida.query.filter(
            Corrida.status.in_(["request", "match", "confirm", "in_transit"])
        ).all()
        simuladas = vigiadas = 0
        for corrida in pendentes:
            if corrida.motorista_id is not None and corrida.status != "request":
                # corrida com motorista local → retoma a simulação de progresso
                t = threading.Thread(target=_simular_progresso,
                                     args=(corrida.id, corrida.status, app),
                                     daemon=True)
                simuladas += 1
            else:
                # corrida delegada/aguardando o Core → retoma o vigia
                t = threading.Thread(target=_vigiar_delegada,
                                     args=(corrida.id, app), daemon=True)
                vigiadas += 1
            t.start()
        if pendentes:
            print(f"[OK] corridas retomadas: {simuladas} locais, {vigiadas} delegadas vigiadas.")


# Solicitação de corrida pelo passageiro
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

    # ── Política de overflow ─────────────────────────────────────────────────
    if esta_congestionado():
        entrar_na_fila(corrida.id, tipo="saida")
        _delegar_via_core(corrida)
        _iniciar_vigia(corrida.id)
        return jsonify({
            "mensagem": "Serviço ocupado. Corrida enviada ao leilão via Core.",
            "corrida_id": corrida.id,
            "status": corrida.status,
            "core_ride_uuid": corrida.core_ride_uuid,
        })

    #Tenta atribuir motorista local 
    motorista = Motorista.query.filter_by(status="disponivel").first()

    if motorista:
        motorista.status = "ocupado"
        corrida.motorista_id = motorista.id
        corrida.status = "match"
        db.session.commit()
        log_evento("motorista_atribuido", corrida_id=corrida.id,
                   estado_anterior="request", estado_novo="match")
        _m.contadores["corridas_locais"] += 1

        # Avança automaticamente: match → confirm → in_transit → complete
        _iniciar_progresso(corrida.id, "match")

        return jsonify({
            "mensagem": "Motorista encontrado!",
            "corrida_id": corrida.id,
            "status": corrida.status,
            "motorista": motorista.to_dict()
        })

    #Sem motorista → delega ao Core
    entrar_na_fila(corrida.id, tipo="saida")
    _delegar_via_core(corrida)
    _iniciar_vigia(corrida.id)
    return jsonify({
        "mensagem": "Sem motorista disponível. Corrida enviada ao leilão via Core.",
        "corrida_id": corrida.id,
        "status": corrida.status,
        "core_ride_uuid": corrida.core_ride_uuid,
    })


# Delegação de saída
def _delegar_via_core(corrida):
    ride_uuid = core.criar_corrida(corrida)
    if ride_uuid:
        corrida.core_ride_uuid = ride_uuid
        corrida.delegada = True
        corrida.servico_origem = "core-auction"
        db.session.commit()
        _m.contadores["corridas_delegadas"] += 1
        log_evento("corrida_leilao_iniciado", corrida_id=corrida.id,
                   ride_uuid=ride_uuid, estado_novo="request")
    else:
        log_evento("erro_delegacao_core", corrida_id=corrida.id, nivel="ERROR")


# Webhooks — o Core chama estes endpoints

# Política de proposta para leilões
_PRECO_BASE        = 1.0   # bandeirada (R$)
_PRECO_POR_KM      = 1.0    # tarifa por km entre origem e destino (R$)
_ETA_BASE          = 300    # ETA com um único motorista livre (s)
_ETA_POR_MOTORISTA = 30     # redução por motorista livre adicional (s)
_ETA_MINIMO        = 120    # piso do ETA (s)

_LOCK_TTL = 60  # TTL pedido ao renovar o lock distribuído (s)

def _tick_seguro(valor):
    """Aplica o logicalTimestamp remoto ao relógio de Lamport.
    Valor ausente ou não numérico conta como tick local simples."""
    try:
        core._tick(int(valor))
    except (TypeError, ValueError):
        core._tick()


def _parse_iso_utc(valor):
    """Converte string ISO-8601 (aware ou naive) em datetime naive UTC.
    Retorna None se ausente ou inválida."""
    if not valor:
        return None
    try:
        dt = datetime.fromisoformat(str(valor).replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is not None:
        dt = dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _haversine_km(origem, destino):
    """Distância em km entre dois pontos {lat, lng}. Coordenadas ausentes
    ou inválidas contam como distância zero (cobra-se só a bandeirada)."""
    try:
        lat1, lng1 = float(origem.get("lat")), float(origem.get("lng"))
        lat2, lng2 = float(destino.get("lat")), float(destino.get("lng"))
    except (TypeError, ValueError, AttributeError):
        return 0.0
    rlat1, rlng1, rlat2, rlng2 = map(radians, (lat1, lng1, lat2, lng2))
    a = sin((rlat2 - rlat1) / 2) ** 2 + cos(rlat1) * cos(rlat2) * sin((rlng2 - rlng1) / 2) ** 2
    return 6371.0 * 2 * asin(sqrt(a))


def _montar_proposta(dados, motoristas_livres):
    """Calcula (eta, preco): ETA cai conforme há mais motoristas livres;
    preço é bandeirada + tarifa pela distância origem→destino."""
    eta = max(_ETA_MINIMO, _ETA_BASE - _ETA_POR_MOTORISTA * (motoristas_livres - 1))
    km = _haversine_km(dados.get("origin"), dados.get("destination"))
    preco = round(_PRECO_BASE + _PRECO_POR_KM * km, 2)
    return eta, preco


@rides_bp.route("/incoming", methods=["POST"])
def receber_leilao():
   #Core convida para o leilão. Responde 200 com proposta ou 204.
    try:
        dados = request.get_json(silent=True) or {}
        _tick_seguro(dados.get("logicalTimestamp"))
        ride_uuid = dados.get("rideUuid")

        # Proposta após o auctionDeadline é ignorada pelo Core — recusa logo
        deadline = _parse_iso_utc(dados.get("auctionDeadline"))
        if deadline and datetime.utcnow() >= deadline:
            log_evento("leilao_deadline_expirado", ride_uuid=ride_uuid, nivel="WARN")
            return "", 204

        livres = Motorista.query.filter_by(status="disponivel").count()
        if not livres:
            log_evento("leilao_recusado", ride_uuid=ride_uuid, nivel="INFO")
            return "", 204

        eta, preco = _montar_proposta(dados, livres)
        log_evento("leilao_proposta_enviada", ride_uuid=ride_uuid, nivel="INFO")
        return jsonify({
            "estimatedEta":     eta,
            "estimatedPrice":   preco,
            "logicalTimestamp": core.get_clock(),
        }), 200

    except Exception:
        log_evento("erro_webhook_incoming", nivel="ERROR")
        return "", 204


def _compensar_aceite_local(corrida, motivo):
    """Desfaz um aceite de leilão que não pôde ser confirmado no Core:
    libera o motorista e cancela a corrida local. O lock distribuído NÃO é
    liberado — deixá-lo expirar é o que faz o Core detectar a falha,
    compensar e re-leiloar a corrida excluindo este grupo."""
    if corrida.motorista:
        corrida.motorista.status = "disponivel"
    corrida.status = "cancelled"
    db.session.commit()
    log_evento("aceite_leilao_compensado", corrida_id=corrida.id,
               ride_uuid=corrida.core_ride_uuid, motivo=motivo,
               estado_anterior="match", estado_novo="cancelled", nivel="WARN")


@rides_bp.route("/<ride_uuid>/assigned", methods=["POST"])
def corrida_atribuida(ride_uuid):
    """[Webhook] Core notifica que este grupo venceu o leilão.

    O lock distribuído chega transferido junto com o callback
    (lockExpiresAt). Confirma o recebimento com 200 e transita a corrida
    para confirm no Core dentro do prazo do lock. Qualquer falha responde
    409 (sem penalidade de circuit breaker) e deixa o lock expirar — o
    Core então compensa e re-executa o leilão sem este grupo.
    """
    try:
        dados = request.get_json(silent=True) or {}
        _tick_seguro(dados.get("logicalTimestamp"))

        # Idempotência: callback repetido (retry do Core) não duplica corrida
        existente = Corrida.query.filter_by(core_ride_uuid=ride_uuid).first()
        if existente:
            log_evento("leilao_assigned_repetido", corrida_id=existente.id,
                       ride_uuid=ride_uuid, nivel="WARN")
            return jsonify({"aceito": True, "corrida_id": existente.id}), 200

        motorista = Motorista.query.filter_by(status="disponivel").first()
        if not motorista:
            log_evento("leilao_ganho_sem_motorista", ride_uuid=ride_uuid, nivel="WARN")
            return jsonify({"erro": "motorista indisponível"}), 409

        from models import Passageiro
        externo = Passageiro.query.filter_by(email="externo@ridefleet.internal").first()
        passageiro_id = externo.id if externo else 1

        corrida = Corrida(
            passageiro_id=passageiro_id,
            origem=dados.get("origin", {}).get("street", ""),
            destino=dados.get("destination", {}).get("street", ""),
            status="match",
            delegada=True,
            servico_origem=dados.get("originServiceId", "externo"),
            motorista_id=motorista.id,
            core_ride_uuid=ride_uuid,
        )
        motorista.status = "ocupado"
        db.session.add(corrida)
        db.session.commit()
        log_evento("corrida_recebida_leilao", corrida_id=corrida.id,
                   ride_uuid=ride_uuid, estado_novo="match")

        # Registra na fila de entrada — pool durável de corridas recebidas
        # por delegação, sobrevive a um restart do serviço.
        entrar_na_fila(corrida.id, tipo="entrada")

        # Lock já transferido pelo Core; renova para ganhar folga. Se a
        # renovação falhar mas o lock transferido ainda valer, dá para seguir.
        lock_expira = _parse_iso_utc(dados.get("lockExpiresAt"))
        renovado = core.adquirir_lock(ride_uuid, ttl=_LOCK_TTL)
        if renovado:
            _m.registrar_lock_adquirido()
        elif lock_expira is None or datetime.utcnow() >= lock_expira:
            _compensar_aceite_local(corrida, "lock_indisponivel")
            return jsonify({"erro": "lock indisponível"}), 409

        # Transição match → confirm no Core dentro do prazo do lock (1 retry)
        confirmado = core.avancar_status_core(ride_uuid, "confirm")
        if not confirmado:
            core.adquirir_lock(ride_uuid, ttl=_LOCK_TTL)
            confirmado = core.avancar_status_core(ride_uuid, "confirm")
        if not confirmado:
            _compensar_aceite_local(corrida, "confirm_rejeitado_pelo_core")
            return jsonify({"erro": "falha ao confirmar no Core"}), 409

        corrida.status = "confirm"
        _m.registrar_corrida_recebida()
        _m.registrar_transicao("match", "confirm")
        db.session.commit()
        log_evento("status_atualizado", corrida_id=corrida.id, ride_uuid=ride_uuid,
                   estado_anterior="match", estado_novo="confirm")

        # Avança automaticamente: confirm → in_transit → complete
        _iniciar_progresso(corrida.id, "confirm")

        return jsonify({"aceito": True, "corrida_id": corrida.id}), 200

    except Exception:
        db.session.rollback()
        log_evento("erro_webhook_assigned", ride_uuid=ride_uuid, nivel="ERROR")
        return jsonify({"erro": "falha interna ao aceitar a corrida"}), 409


# Consulta de status
@rides_bp.route("/status/<int:corrida_id>", methods=["GET"])
@jwt_required()
def status(corrida_id):
    corrida = Corrida.query.get_or_404(corrida_id)
    dados = corrida.to_dict()

    if corrida.core_ride_uuid:
        estado_core = core.status_corrida(corrida.core_ride_uuid)
        if estado_core:
            dados["core_status"] = estado_core

    return jsonify(dados)


@rides_bp.route("/auditoria/<ride_uuid>", methods=["GET"])
@jwt_required()
def auditoria(ride_uuid):
    log = core.auditoria_corrida(ride_uuid)
    if log is None:
        return jsonify({"erro": "auditoria não disponível"}), 404
    return jsonify(log)


# Avanço manual de estados (ainda disponível para casos externos)
@rides_bp.route("/avancar/<int:corrida_id>", methods=["POST"])
@jwt_required()
def avancar(corrida_id):
    corrida = Corrida.query.get_or_404(corrida_id)
    dados = request.get_json() or {}
    novo_status = dados.get("status")

    transicoes = {
        "match":      "confirm",
        "confirm":    "in_transit",
        "in_transit": "complete",
    }
    if transicoes.get(corrida.status) != novo_status:
        return jsonify({"erro": f"Transição inválida: {corrida.status} → {novo_status}"}), 400

    anterior = corrida.status
    corrida.status = novo_status

    if novo_status == "complete" and corrida.motorista:
        corrida.motorista.status = "disponivel"
        if corrida.core_ride_uuid:
            core.liberar_lock(corrida.core_ride_uuid)

    db.session.commit()
    log_evento("status_atualizado", corrida_id=corrida.id,
               estado_anterior=anterior, estado_novo=novo_status)

    if corrida.core_ride_uuid and novo_status in ("confirm", "in_transit", "complete"):
        core.adquirir_lock(corrida.core_ride_uuid, ttl=60)
        core.avancar_status_core(corrida.core_ride_uuid, novo_status)

    return jsonify(corrida.to_dict())


# ---------------------------------------------------------------------------
# Minhas corridas
# ---------------------------------------------------------------------------

@rides_bp.route("/minhas", methods=["GET"])
@jwt_required()
def minhas():
    passageiro_id = int(get_jwt_identity())
    corridas = (Corrida.query
                .filter_by(passageiro_id=passageiro_id)
                .order_by(Corrida.criado_em.desc())
                .all())
    return jsonify([c.to_dict() for c in corridas])
