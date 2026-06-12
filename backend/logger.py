"""
Logger estruturado em JSON para o RideFleet.

Todos os eventos são emitidos no formato:
{
  "timestamp":      "2026-05-30T02:00:00",
  "nivel":          "INFO | WARN | ERROR",
  "evento":         "nome_do_evento",
  "mensagem":       "texto livre",
  "corrida_id":     1,
  "ride_uuid":      "uuid-do-core",
  "servico_origem": "local | grupo-xx",
  "estado_anterior":"request",
  "estado_novo":    "match",
  "lamport_clock":  5,
  "duracao_ms":     12.3     # só em eventos de requisição HTTP
}
"""

import json
import logging
from datetime import datetime


class LoggerJSON(logging.Formatter):
    """Formata todos os logs em JSON para facilitar auditoria e parsing."""

    _CAMPOS = (
        "evento", "corrida_id", "ride_uuid",
        "servico_origem", "estado_anterior", "estado_novo",
        "lamport_clock", "duracao_ms", "metodo", "rota", "status_http",
    )

    def format(self, record):
        log = {
            "timestamp": datetime.utcnow().isoformat(),
            "nivel":     record.levelname,
            "mensagem":  record.getMessage(),
        }
        for campo in self._CAMPOS:
            if hasattr(record, campo):
                log[campo] = getattr(record, campo)
        return json.dumps(log, ensure_ascii=False)


def get_logger(nome="ridefleet"):
    logger = logging.getLogger(nome)
    if not logger.handlers:
        handler = logging.StreamHandler()
        handler.setFormatter(LoggerJSON())
        logger.addHandler(handler)
        logger.setLevel(logging.INFO)
    return logger


# instância global
log = get_logger()


def log_evento(
    evento,
    corrida_id=None,
    ride_uuid=None,
    servico_origem="local",
    estado_anterior=None,
    estado_novo=None,
    lamport_clock=None,
    nivel="INFO",
    **kwargs,
):
    """Atalho para logar eventos de domínio no formato estruturado."""
    extra = {
        "evento":          evento,
        "corrida_id":      corrida_id,
        "ride_uuid":       ride_uuid,
        "servico_origem":  servico_origem,
        "estado_anterior": estado_anterior,
        "estado_novo":     estado_novo,
        "lamport_clock":   lamport_clock,
    }
    extra.update(kwargs)   # campos extras livres

    if nivel == "WARN":
        log.warning(evento, extra=extra)
    elif nivel == "ERROR":
        log.error(evento, extra=extra)
    else:
        log.info(evento, extra=extra)


def log_requisicao(metodo, rota, status_http, duracao_ms):
    """Loga cada requisição HTTP com método, rota, status e duração."""
    extra = {
        "evento":      "requisicao_http",
        "metodo":      metodo,
        "rota":        rota,
        "status_http": status_http,
        "duracao_ms":  round(duracao_ms, 2),
    }
    nivel = logging.WARNING if status_http >= 500 else logging.INFO
    log.log(nivel, f"{metodo} {rota} → {status_http}", extra=extra)
