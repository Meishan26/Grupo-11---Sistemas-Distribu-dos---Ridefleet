from database import db
from models import FilaCorrida, Corrida, Motorista
from logger import log_evento
from datetime import datetime, timedelta

# política de overflow: delega se motoristas livres < esse número
LIMITE_MOTORISTAS_LIVRES = 1
TEMPO_MAX_FILA_MINUTOS = 10


def esta_congestionado():
    """Verifica se o serviço deve delegar corridas (política de overflow)."""
    livres = Motorista.query.filter_by(status="disponivel").count()
    fila_saida = FilaCorrida.query.filter_by(tipo="saida", status="aguardando").count()

    if livres <= LIMITE_MOTORISTAS_LIVRES or fila_saida > 5:
        log_evento("servico_congestionado", nivel="WARN")
        return True
    return False


def entrar_na_fila(corrida_id, tipo):
    """Adiciona corrida na fila de entrada ou saída."""
    item = FilaCorrida(corrida_id=corrida_id, tipo=tipo)
    db.session.add(item)
    db.session.commit()
    log_evento("corrida_enfileirada", corrida_id=corrida_id, evento=f"fila_{tipo}")
    return item


def proxima_da_fila(tipo="entrada"):
    """Pega a próxima corrida aguardando na fila."""
    return FilaCorrida.query.filter_by(tipo=tipo, status="aguardando").order_by(FilaCorrida.criado_em).first()


def descartar_antigas():
    """Descarta corridas que estão na fila há mais de TEMPO_MAX_FILA_MINUTOS."""
    limite = datetime.utcnow() - timedelta(minutes=TEMPO_MAX_FILA_MINUTOS)
    antigas = FilaCorrida.query.filter(
        FilaCorrida.status == "aguardando",
        FilaCorrida.criado_em < limite
    ).all()

    for item in antigas:
        item.status = "descartada"
        log_evento("corrida_descartada", corrida_id=item.corrida_id, nivel="WARN")

    db.session.commit()
    return len(antigas)


def tamanho_fila(tipo=None):
    """Retorna quantas corridas estão aguardando na fila."""
    q = FilaCorrida.query.filter_by(status="aguardando")
    if tipo:
        q = q.filter_by(tipo=tipo)
    return q.count()
