import json
import logging
from datetime import datetime

class LoggerJSON(logging.Formatter):
    """Formata todos os logs em JSON para facilitar auditoria."""

    def format(self, record):
        log = {
            "timestamp": datetime.utcnow().isoformat(),
            "nivel": record.levelname,
            "mensagem": record.getMessage(),
        }
        # campos extras passados via extra={}
        for campo in ("evento", "corrida_id", "servico_origem", "estado_anterior", "estado_novo"):
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


def log_evento(evento, corrida_id=None, servico_origem="local", estado_anterior=None, estado_novo=None, nivel="INFO"):
    """Atalho para logar eventos de corrida no formato que o Core espera."""
    extra = {
        "evento": evento,
        "corrida_id": corrida_id,
        "servico_origem": servico_origem,
        "estado_anterior": estado_anterior,
        "estado_novo": estado_novo,
    }
    if nivel == "WARN":
        log.warning(evento, extra=extra)
    elif nivel == "ERROR":
        log.error(evento, extra=extra)
    else:
        log.info(evento, extra=extra)
