from flask import Flask, jsonify, request
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from database import db
from routes.auth import auth_bp
from routes.rides import rides_bp
from routes.drivers import drivers_bp
from routes.admin import admin_bp
from fila import tamanho_fila
from logger import log_evento, log_requisicao
import core_client as core
import time
import os

START_TIME = time.time()

# ── Contadores globais de monitoramento ───────────────────────────────────────
import metrics as _m

_contadores = _m.contadores
_latencias = []   # últimas 100 latências (ms)


def _registrar_latencia(ms):
    _latencias.append(ms)
    if len(_latencias) > 100:
        _latencias.pop(0)


def _lat_media():
    return round(sum(_latencias) / len(_latencias), 2) if _latencias else 0


def _lat_p95():
    if not _latencias:
        return 0
    s = sorted(_latencias)
    idx = int(len(s) * 0.95)
    return round(s[min(idx, len(s) - 1)], 2)


# ── Factory ───────────────────────────────────────────────────────────────────

def criar_app(config_teste=None):
    app = Flask(__name__)

    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
        "DATABASE_URL",
        "postgresql://ridefleet:ridefleet@db:5432/ridefleet"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET", "ridefleet-secret-2026")

    if config_teste:
        app.config.update(config_teste)

    CORS(app)
    db.init_app(app)
    JWTManager(app)

    app.register_blueprint(auth_bp,    url_prefix="/auth")
    app.register_blueprint(rides_bp,   url_prefix="/rides")
    app.register_blueprint(drivers_bp, url_prefix="/drivers")
    app.register_blueprint(admin_bp,   url_prefix="/admin")

    # Registro no Core (idempotente; ignorado em modo teste)
    if not config_teste:
        with app.app_context():
            try:
                core.registrar_grupo()
            except Exception:
                log_evento("aviso_registro_core_adiado", nivel="WARN")

    # ── Middleware: latência + log de requisições ─────────────────────────────
    @app.before_request
    def antes():
        from flask import g
        g.inicio = time.time()

    @app.after_request
    def depois(response):
        from flask import g
        _contadores["requisicoes_total"] += 1
        if response.status_code >= 500:
            _contadores["requisicoes_erro"] += 1

        if hasattr(g, "inicio"):
            ms = (time.time() - g.inicio) * 1000
            _registrar_latencia(ms)
            log_requisicao(
                metodo=request.method,
                rota=request.path,
                status_http=response.status_code,
                duracao_ms=ms,
            )
        return response

    # ── Rotas de sistema ──────────────────────────────────────────────────────
    @app.route("/")
    def index():
        return jsonify({"servico": "RideFleet", "status": "ok"})

    @app.route("/debug/core")
    def debug_core():
        """Diagnóstico da conexão com o Core: API key, health e registro."""
        import requests as http
        resultado = {
            "core_url":   core.CORE_URL,
            "servico_id": core.SERVICO_ID,
            "servico_url": core.SERVICO_URL,
            "api_key_presente": bool(core._api_key),
            "api_key_prefixo": (core._api_key[:8] + "…") if core._api_key else None,
        }

        # Testa /health (não requer autenticação)
        try:
            r = http.get(f"{core.CORE_URL}/health", timeout=4)
            resultado["core_health"] = r.json() if r.ok else {"erro": r.status_code}
            resultado["core_acessivel"] = r.ok
        except Exception as e:
            resultado["core_health"] = {"erro": str(e)}
            resultado["core_acessivel"] = False

        # Tenta registrar/re-registrar para garantir API key
        if not core._api_key and resultado["core_acessivel"]:
            core.registrar_grupo()
            resultado["registro_tentado"] = True
            resultado["api_key_presente"] = bool(core._api_key)

        return jsonify(resultado)

    @app.route("/health")
    def health():
        """
        Health check — usado pelo Docker e pelo circuit breaker do Core.
        Retorna UP / DEGRADED / DOWN baseado nas filas e motoristas.
        """
        from models import Motorista
        livres       = Motorista.query.filter_by(status="disponivel").count()
        fila_entrada = tamanho_fila("entrada")
        fila_saida   = tamanho_fila("saida")

        if livres == 0 and fila_saida > 5:
            status_geral = "DEGRADED"
        else:
            status_geral = "UP"

        if fila_saida > 10:
            status_geral = "DOWN"
            log_evento("fila_overflow", nivel="ERROR")

        return jsonify({
            "status":                 status_geral,
            "motoristas_disponiveis": livres,
            "fila_entrada":           fila_entrada,
            "fila_saida":             fila_saida,
            "latencia_media_ms":      _lat_media(),
            "latencia_p95_ms":        _lat_p95(),
            "uptime_segundos":        round(time.time() - START_TIME),
            "lamport_clock":          core.get_clock(),
            "requisicoes_total":      _contadores["requisicoes_total"],
            "requisicoes_erro":       _contadores["requisicoes_erro"],
        })

    @app.route("/metrics")
    def metrics():
        """
        Métricas no formato Prometheus (OpenMetrics).
        Consumido pelo Prometheus / Grafana.
        """
        from models import Corrida, Motorista

        livres        = Motorista.query.filter_by(status="disponivel").count()
        fila_entrada  = tamanho_fila("entrada")
        fila_saida    = tamanho_fila("saida")

        linhas = [
            # motoristas
            "# HELP ridefleet_motoristas_disponiveis Motoristas com status disponivel",
            "# TYPE ridefleet_motoristas_disponiveis gauge",
            f"ridefleet_motoristas_disponiveis {livres}",

            # filas
            "# HELP ridefleet_fila_entrada Mensagens aguardando na fila de entrada",
            "# TYPE ridefleet_fila_entrada gauge",
            f"ridefleet_fila_entrada {fila_entrada}",

            "# HELP ridefleet_fila_saida Mensagens aguardando na fila de saida",
            "# TYPE ridefleet_fila_saida gauge",
            f"ridefleet_fila_saida {fila_saida}",

            # latência
            "# HELP ridefleet_latencia_media_ms Latencia media das requisicoes em ms",
            "# TYPE ridefleet_latencia_media_ms gauge",
            f"ridefleet_latencia_media_ms {_lat_media()}",

            "# HELP ridefleet_latencia_p95_ms Latencia p95 das requisicoes em ms",
            "# TYPE ridefleet_latencia_p95_ms gauge",
            f"ridefleet_latencia_p95_ms {_lat_p95()}",

            # requisições
            "# HELP ridefleet_requisicoes_total Total de requisicoes recebidas",
            "# TYPE ridefleet_requisicoes_total counter",
            f"ridefleet_requisicoes_total {_contadores['requisicoes_total']}",

            "# HELP ridefleet_requisicoes_erro Total de requisicoes com erro 5xx",
            "# TYPE ridefleet_requisicoes_erro counter",
            f"ridefleet_requisicoes_erro {_contadores['requisicoes_erro']}",

            # relógio de Lamport
            "# HELP ridefleet_lamport_clock Valor atual do relogio de Lamport",
            "# TYPE ridefleet_lamport_clock counter",
            f"ridefleet_lamport_clock {core.get_clock()}",

            # uptime
            "# HELP ridefleet_uptime_segundos Tempo de execucao do servico em segundos",
            "# TYPE ridefleet_uptime_segundos counter",
            f"ridefleet_uptime_segundos {round(time.time() - START_TIME)}",
        ]

        # corridas por estado
        linhas.append("# HELP ridefleet_corridas Corridas por estado da saga")
        linhas.append("# TYPE ridefleet_corridas gauge")
        for estado in ("request", "match", "confirm", "in_transit", "complete"):
            count = Corrida.query.filter_by(status=estado).count()
            linhas.append(f'ridefleet_corridas{{status="{estado}"}} {count}')

        # ── Métricas obrigatórias pelo contrato (seção 9.2 do tutorial) ──────
        svc = core.SERVICO_ID

        linhas += [
            "# HELP ridefleet_rides_local_total Corridas atendidas localmente",
            "# TYPE ridefleet_rides_local_total counter",
            f'ridefleet_rides_local_total{{service="{svc}"}} {_m.contadores["corridas_locais"]}',

            "# HELP ridefleet_rides_delegated_total Corridas delegadas ao Core",
            "# TYPE ridefleet_rides_delegated_total counter",
            f'ridefleet_rides_delegated_total{{service="{svc}"}} {_m.contadores["corridas_delegadas"]}',

            "# HELP ridefleet_locks_acquired_total Locks distribuidos adquiridos",
            "# TYPE ridefleet_locks_acquired_total counter",
            f'ridefleet_locks_acquired_total{{service="{svc}"}} {_m.contadores["locks_adquiridos"]}',

            "# HELP ridefleet_locks_expired_total Locks que expiraram sem transicao",
            "# TYPE ridefleet_locks_expired_total counter",
            f'ridefleet_locks_expired_total{{service="{svc}"}} {_m.contadores["locks_expirados"]}',

            "# HELP ridefleet_circuit_breaker_state Estado do circuit breaker (0=CLOSED 1=OPEN 2=HALF_OPEN)",
            "# TYPE ridefleet_circuit_breaker_state gauge",
            f'ridefleet_circuit_breaker_state{{service="{svc}"}} {_m.circuit_breaker_state}',
        ]

        # saga transitions
        linhas.append("# HELP ridefleet_saga_transitions_total Transicoes de estado da saga")
        linhas.append("# TYPE ridefleet_saga_transitions_total counter")
        for (de, para), total in _m.saga_transitions.items():
            linhas.append(
                f'ridefleet_saga_transitions_total{{from_state="{de}",to_state="{para}",service="{svc}"}} {total}'
            )
        if not _m.saga_transitions:
            for par in [("match","confirm"),("confirm","in_transit"),("in_transit","complete")]:
                linhas.append(
                    f'ridefleet_saga_transitions_total{{from_state="{par[0]}",to_state="{par[1]}",service="{svc}"}} 0'
                )

        return "\n".join(linhas) + "\n", 200, {"Content-Type": "text/plain; charset=utf-8"}

    return app


# ── Seed de dados ─────────────────────────────────────────────────────────────

def popular_banco(app):
    """Garante passageiro externo, 3 motoristas de exemplo e todos disponíveis."""
    with app.app_context():
        from models import Passageiro, Motorista
        from werkzeug.security import generate_password_hash

        # Passageiro reservado para corridas delegadas via Core (externas)
        if not Passageiro.query.filter_by(email="externo@ridefleet.internal").first():
            externo = Passageiro(
                nome="Passageiro Externo",
                email="externo@ridefleet.internal",
                senha=generate_password_hash("inaccessible"),
            )
            db.session.add(externo)
            db.session.commit()
            print("[OK] Passageiro externo criado.")

        seeds = [
            {"nome": "Carlos Silva",   "veiculo": "Toyota Corolla", "placa": "ABC1234"},
            {"nome": "Ana Souza",      "veiculo": "Honda Civic",    "placa": "DEF5678"},
            {"nome": "Bruno Oliveira", "veiculo": "VW Polo",        "placa": "GHI9012"},
        ]

        for seed in seeds:
            m = Motorista.query.filter_by(placa=seed["placa"]).first()
            if m is None:
                m = Motorista(**seed)
                db.session.add(m)
                print(f"[OK] Motorista criado: {seed['nome']}")
            # garante disponível a cada reinício
            m.status = "disponivel"

        db.session.commit()
        print("[OK] 3 motoristas disponíveis garantidos.")


if __name__ == "__main__":
    app = criar_app()
    with app.app_context():
        db.create_all()
        popular_banco(app)
    from routes.rides import retomar_corridas_pendentes
    retomar_corridas_pendentes(app)
    app.run(debug=True, host="0.0.0.0", port=5000)
