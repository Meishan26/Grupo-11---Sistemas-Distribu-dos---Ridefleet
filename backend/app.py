from flask import Flask, jsonify
from flask_cors import CORS
from flask_jwt_extended import JWTManager
from database import db
from routes.auth import auth_bp
from routes.rides import rides_bp
from routes.drivers import drivers_bp
from fila import tamanho_fila
from logger import log_evento
import time
import os

# guarda o tempo de início para calcular uptime
START_TIME = time.time()
latencias = []  # guarda as últimas latências para calcular média


def criar_app():
    app = Flask(__name__)

    app.config["SQLALCHEMY_DATABASE_URI"] = os.getenv(
        "DATABASE_URL",
        "postgresql://ridefleet:ridefleet@db:5432/ridefleet"
    )
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["JWT_SECRET_KEY"] = os.getenv("JWT_SECRET", "ridefleet-secret-2026")

    CORS(app)
    db.init_app(app)
    JWTManager(app)

    app.register_blueprint(auth_bp,    url_prefix="/auth")
    app.register_blueprint(rides_bp,   url_prefix="/rides")
    app.register_blueprint(drivers_bp, url_prefix="/drivers")

    # middleware para medir latência
    @app.before_request
    def antes():
        from flask import g
        g.inicio = time.time()

    @app.after_request
    def depois(response):
        from flask import g
        if hasattr(g, "inicio"):
            latencia = (time.time() - g.inicio) * 1000
            latencias.append(latencia)
            if len(latencias) > 100:
                latencias.pop(0)
        return response

    @app.route("/")
    def index():
        return jsonify({"servico": "RideFleet", "status": "ok"})

    @app.route("/health")
    def health():
        """Health check do serviço — usado pelo Docker e pelo Core."""
        from models import Motorista
        livres = Motorista.query.filter_by(status="disponivel").count()
        fila_entrada = tamanho_fila("entrada")
        fila_saida   = tamanho_fila("saida")
        lat_media    = round(sum(latencias) / len(latencias), 2) if latencias else 0

        # define status geral
        if livres == 0 and fila_saida > 5:
            status_geral = "DEGRADED"
        else:
            status_geral = "UP"

        if fila_saida > 10:
            status_geral = "DOWN"
            log_evento("fila_overflow", nivel="ERROR")

        return jsonify({
            "status": status_geral,
            "motoristas_disponiveis": livres,
            "fila_entrada": fila_entrada,
            "fila_saida": fila_saida,
            "latencia_media_ms": lat_media,
            "uptime_segundos": round(time.time() - START_TIME)
        })

    @app.route("/metrics")
    def metrics():
        """Métricas no formato Prometheus."""
        from models import Corrida, Motorista
        livres = Motorista.query.filter_by(status="disponivel").count()
        lat_media = round(sum(latencias) / len(latencias), 2) if latencias else 0

        linhas = [
            f"ridefleet_motoristas_disponiveis {livres}",
            f"ridefleet_fila_entrada {tamanho_fila('entrada')}",
            f"ridefleet_fila_saida {tamanho_fila('saida')}",
            f"ridefleet_latencia_media_ms {lat_media}",
        ]
        for status in ("request", "match", "confirm", "in_transit", "complete"):
            count = Corrida.query.filter_by(status=status).count()
            linhas.append(f'ridefleet_corridas{{status="{status}"}} {count}')

        return "\n".join(linhas), 200, {"Content-Type": "text/plain"}

    return app


def popular_banco(app):
    """Cria motoristas de exemplo se o banco estiver vazio."""
    with app.app_context():
        from models import Motorista
        if Motorista.query.count() == 0:
            motoristas = [
                Motorista(nome="Carlos Silva",   veiculo="Toyota Corolla", placa="ABC1234"),
                Motorista(nome="Ana Souza",      veiculo="Honda Civic",    placa="DEF5678"),
                Motorista(nome="Bruno Oliveira", veiculo="VW Polo",        placa="GHI9012"),
            ]
            db.session.add_all(motoristas)
            db.session.commit()
            print("[OK] Motoristas de exemplo criados.")


if __name__ == "__main__":
    app = criar_app()
    with app.app_context():
        db.create_all()
        popular_banco(app)
    app.run(debug=True, host="0.0.0.0", port=5000)
