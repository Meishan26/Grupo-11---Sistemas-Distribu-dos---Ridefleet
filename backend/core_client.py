"""
Cliente HTTP para o Core do RideFleet.

Responsabilidades:
- Registro do grupo e obtenção de API key
- Relógio de Lamport thread-safe (max + 1 a cada evento)
- Criação de corrida via leilão (scatter-gather)
- Gestão de lock distribuído
- Avanço de estados da saga
- Consulta de status e auditoria
"""

import os
import threading
import requests as http
from logger import log_evento

CORE_URL    = os.getenv("CORE_URL",     "http://ridefleet-core:8080/api/v1")
SERVICO_ID  = os.getenv("SERVICO_NOME", "grupo-11")
SERVICO_URL = os.getenv("SERVICO_URL",  "http://ridefleet-grupo11-nginx:80")

_api_key         = None
_clock           = 0
_clock_lock      = threading.Lock()
_registrado      = False
_tentativas_reg  = 0


# Relógio de Lamport
def _tick(received=None):
    """Incrementa o relógio local. Se `received` vier de uma resposta remota,
    aplica max(local, received) + 1 antes de retornar o novo valor."""
    global _clock
    with _clock_lock:
        if received is not None:
            _clock = max(_clock, int(received)) + 1
        else:
            _clock += 1
        return _clock


def get_clock():
    with _clock_lock:
        return _clock



# Autenticação
def _headers():
    return {"X-API-Key": _api_key or ""}


def registrar_grupo():
    """Registra (ou re-registra) o grupo no Core e armazena a API key.
    Deve ser chamado uma vez na inicialização do serviço."""
    global _api_key
    try:
        resp = http.post(f"{CORE_URL}/groups/register", json={
            "groupId":    SERVICO_ID,
            "groupName":  f"{SERVICO_ID} — SIN 142",
            "serviceUrl": SERVICO_URL,
        }, timeout=10)

        if resp.status_code in (200, 201):
            _api_key = resp.json().get("apiKey")
            log_evento("grupo_registrado_core", nivel="INFO")
            return _api_key

        log_evento("erro_registro_core", nivel="WARN")
    except Exception:
        log_evento("erro_registro_core", nivel="ERROR")
    return None



# Corridas — criação via leilão
def criar_corrida(corrida):
    """Envia corrida ao Core para iniciar o leilão (scatter-gather).
    Retorna o rideUuid gerado pelo Core, ou None em caso de falha."""
    ts = _tick()
    try:
        resp = http.post(f"{CORE_URL}/rides", headers=_headers(), json={
            "originServiceId":      SERVICO_ID,
            "passengerId":          str(corrida.passageiro_id),
            "passengerName":        corrida.passageiro.nome if corrida.passageiro else "Passageiro",
            "origin":               {"lat": 0.0, "lng": 0.0, "street": corrida.origem},
            "destination":          {"lat": 0.0, "lng": 0.0, "street": corrida.destino},
            "logicalTimestamp":     ts,
            "auctionTimeoutSeconds": 10,
        }, timeout=15)

        if resp.status_code == 202:
            data = resp.json()
            _tick(data.get("logicalTimestamp"))
            return data.get("rideUuid")

        log_evento("erro_criar_corrida_core", nivel="WARN")
    except Exception:
        log_evento("erro_criar_corrida_core", nivel="ERROR")
    return None


def status_corrida(ride_uuid):
    """Consulta o estado atual de uma corrida no Core."""
    try:
        resp = http.get(f"{CORE_URL}/rides/{ride_uuid}/status",
                        headers=_headers(), timeout=5)
        if resp.ok:
            data = resp.json()
            _tick(data.get("logicalTimestamp"))
            return data
    except Exception:
        pass
    return None


def auditoria_corrida(ride_uuid):
    """Retorna o log causal completo de uma corrida (ordenado por Lamport)."""
    try:
        resp = http.get(f"{CORE_URL}/rides/{ride_uuid}/audit",
                        headers=_headers(), timeout=5)
        return resp.json() if resp.ok else None
    except Exception:
        return None


# Locks distribuídos
def adquirir_lock(ride_uuid, ttl=60):
    """Adquire ou renova o lock distribuído para uma corrida.
    Retorna True se bem-sucedido."""
    try:
        resp = http.post(f"{CORE_URL}/locks/{ride_uuid}", headers=_headers(), json={
            "serviceId":  SERVICO_ID,
            "ttlSeconds": ttl,
        }, timeout=10)
        return resp.status_code in (200, 201)
    except Exception:
        return False


def liberar_lock(ride_uuid):
    """Libera explicitamente o lock de uma corrida."""
    try:
        http.delete(f"{CORE_URL}/locks/{ride_uuid}",
                    headers=_headers(),
                    json={"serviceId": SERVICO_ID},
                    timeout=5)
    except Exception:
        pass



# Saga — avanço de estados
def avancar_status_core(ride_uuid, novo_estado):
    """Avança o estado da corrida na saga do Core.
    Estados válidos: confirm, in_transit, complete, compensating, cancelled."""
    ts = _tick()
    try:
        resp = http.patch(f"{CORE_URL}/rides/{ride_uuid}/status",
                          headers=_headers(), json={
                              "newState":         novo_estado,
                              "serviceId":        SERVICO_ID,
                              "logicalTimestamp": ts,
                          }, timeout=10)
        if resp.ok:
            data = resp.json()
            _tick(data.get("logicalTimestamp"))
            return True

        log_evento("erro_avancar_status_core", nivel="WARN")
    except Exception:
        log_evento("erro_avancar_status_core", nivel="ERROR")
    return False
