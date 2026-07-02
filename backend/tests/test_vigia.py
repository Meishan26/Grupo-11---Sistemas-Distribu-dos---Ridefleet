"""
Testes do vigia de corridas delegadas ao Core.
"""

from datetime import datetime, timedelta

import core_client as cc
from database import db
from models import Corrida, Motorista
from routes.rides import _verificar_corrida_delegada, _TIMEOUT_DELEGACAO_S


def _ocupar_motoristas_livres():
    """Marca todo motorista disponível como ocupado — usado nos testes que
    precisam simular ausência total de motorista livre."""
    for m in Motorista.query.filter_by(status="disponivel").all():
        m.status = "ocupado"
    db.session.commit()


def _criar_delegada(criado_ha_s=0, uuid="uuid-vigia"):
    corrida = Corrida(
        passageiro_id=1,
        origem="Rua A",
        destino="Rua B",
        status="request",
        delegada=True,
        servico_origem="core-auction",
        core_ride_uuid=uuid,
    )
    corrida.criado_em = datetime.utcnow() - timedelta(seconds=criado_ha_s)
    db.session.add(corrida)
    db.session.commit()
    return corrida


def test_vigia_dentro_do_prazo_continua_aguardando(app):
    """Sem resposta do Core e dentro do prazo → segue vigiando, sem cancelar."""
    cc.status_corrida.return_value = None
    corrida = _criar_delegada(criado_ha_s=10, uuid="uuid-aguardando")
    assert _verificar_corrida_delegada(corrida) is False
    assert corrida.status == "request"


def test_vigia_cancela_apos_timeout(app):
    """Estourou o prazo, sem conclusão e sem motorista livre → cancela local
    e propaga ao Core."""
    _ocupar_motoristas_livres()
    cc.status_corrida.return_value = None
    cc.avancar_status_core.reset_mock()
    corrida = _criar_delegada(criado_ha_s=_TIMEOUT_DELEGACAO_S + 1,
                              uuid="uuid-timeout")
    assert _verificar_corrida_delegada(corrida) is True
    assert corrida.status == "cancelled"
    cc.avancar_status_core.assert_called_once_with("uuid-timeout", "cancelled")


def test_vigia_recupera_localmente_quando_motorista_fica_livre(app):
    """Estourou o prazo, mas surgiu motorista livre → corrida volta ao pool
    local (match) em vez de cancelar; Core é avisado best-effort."""
    cc.status_corrida.return_value = None
    cc.avancar_status_core.reset_mock()
    corrida = _criar_delegada(criado_ha_s=_TIMEOUT_DELEGACAO_S + 1,
                              uuid="uuid-recupera")
    assert _verificar_corrida_delegada(corrida) is True
    assert corrida.status == "match"
    assert corrida.motorista_id is not None
    assert corrida.motorista.status == "ocupado"
    cc.avancar_status_core.assert_called_once_with("uuid-recupera", "cancelled")


def test_vigia_espelha_conclusao_do_core(app):
    """Core diz complete → corrida local reflete e o vigia encerra."""
    cc.status_corrida.return_value = {"state": "complete"}
    try:
        corrida = _criar_delegada(criado_ha_s=10, uuid="uuid-concluida")
        assert _verificar_corrida_delegada(corrida) is True
        assert corrida.status == "complete"
    finally:
        cc.status_corrida.return_value = None


def test_vigia_espelha_estado_intermediario_sem_encerrar(app):
    """Core diz in_transit → espelha mas continua vigiando até concluir."""
    cc.status_corrida.return_value = {"state": "in_transit"}
    try:
        corrida = _criar_delegada(criado_ha_s=10, uuid="uuid-rodando")
        assert _verificar_corrida_delegada(corrida) is False
        assert corrida.status == "in_transit"
    finally:
        cc.status_corrida.return_value = None


def test_vigia_timeout_mesmo_sem_uuid_do_core(app):
    """Delegação que falhou (sem rideUuid) e sem motorista livre também não
    pode ficar presa."""
    _ocupar_motoristas_livres()
    cc.status_corrida.return_value = None
    cc.avancar_status_core.reset_mock()
    corrida = _criar_delegada(criado_ha_s=_TIMEOUT_DELEGACAO_S + 1, uuid=None)
    assert _verificar_corrida_delegada(corrida) is True
    assert corrida.status == "cancelled"
    cc.avancar_status_core.assert_not_called()
