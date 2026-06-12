import pika
import json
import os
from datetime import datetime
from logger import log_evento

RABBITMQ_URL      = os.getenv("RABBITMQ_URL", "amqp://guest:guest@rabbitmq:5672/")
TEMPO_MAX_FILA_MS = 10 * 60 * 1000   # 10 min em ms — TTL automático pelo RabbitMQ
LIMITE_MOTORISTAS_LIVRES = 0

_FILAS = {
    "entrada": "fila_corridas_entrada",
    "saida":   "fila_corridas_saida",
}


def _conectar():
    params = pika.URLParameters(RABBITMQ_URL)
    params.socket_timeout = 3
    return pika.BlockingConnection(params)


def _declarar(channel, tipo=None):
    """Declara fila(s) de forma idempotente."""
    nomes = [_FILAS[tipo]] if tipo else list(_FILAS.values())
    for nome in nomes:
        channel.queue_declare(
            queue=nome,
            durable=True,
            arguments={"x-message-ttl": TEMPO_MAX_FILA_MS}
        )


# ---------------------------------------------------------------------------
# Política de overflow
# ---------------------------------------------------------------------------

def esta_congestionado():
    """Retorna True se o serviço deve delegar corridas ao Core."""
    from models import Motorista
    livres     = Motorista.query.filter_by(status="disponivel").count()
    fila_saida = tamanho_fila("saida")
    if livres <= LIMITE_MOTORISTAS_LIVRES or fila_saida > 5:
        log_evento("servico_congestionado", nivel="WARN")
        return True
    return False


# ---------------------------------------------------------------------------
# Publicar na fila
# ---------------------------------------------------------------------------

def entrar_na_fila(corrida_id, tipo):
    """Publica corrida na fila RabbitMQ correspondente."""
    try:
        conn = _conectar()
        ch   = conn.channel()
        _declarar(ch, tipo)
        ch.basic_publish(
            exchange="",
            routing_key=_FILAS[tipo],
            body=json.dumps({"corrida_id": corrida_id,
                             "criado_em": datetime.utcnow().isoformat()}),
            properties=pika.BasicProperties(delivery_mode=2)   # persistente
        )
        conn.close()
    except Exception:
        log_evento("erro_fila_publicar", corrida_id=corrida_id, nivel="WARN")

    log_evento("corrida_enfileirada", corrida_id=corrida_id, estado_novo=f"fila_{tipo}")
    return {"corrida_id": corrida_id, "tipo": tipo}


# ---------------------------------------------------------------------------
# Consumir da fila
# ---------------------------------------------------------------------------

def proxima_da_fila(tipo="entrada"):
    """Consome a próxima mensagem (FIFO). Retorna dict ou None."""
    try:
        conn = _conectar()
        ch   = conn.channel()
        _declarar(ch, tipo)
        method, _, body = ch.basic_get(queue=_FILAS[tipo], auto_ack=True)
        conn.close()
        if body:
            return json.loads(body)
    except Exception:
        log_evento("erro_fila_consumir", nivel="WARN")
    return None


# ---------------------------------------------------------------------------
# Utilitários
# ---------------------------------------------------------------------------

def descartar_antigas():
    """RabbitMQ descarta automaticamente via x-message-ttl."""
    return 0


def tamanho_fila(tipo=None):
    """Retorna o número de mensagens aguardando. Retorna 0 em caso de falha."""
    try:
        conn = _conectar()
        ch   = conn.channel()
        if tipo:
            _declarar(ch, tipo)
            result = ch.queue_declare(
                queue=_FILAS[tipo], durable=True,
                arguments={"x-message-ttl": TEMPO_MAX_FILA_MS}
            )
            conn.close()
            return result.method.message_count

        total = 0
        for t in _FILAS:
            _declarar(ch, t)
            result = ch.queue_declare(
                queue=_FILAS[t], durable=True,
                arguments={"x-message-ttl": TEMPO_MAX_FILA_MS}
            )
            total += result.method.message_count
        conn.close()
        return total
    except Exception:
        return 0   # RabbitMQ indisponível — não quebra o health check
