"""
Contadores globais de métricas — módulo separado para evitar import circular
entre app.py e routes/rides.py.
"""

contadores = {
    "requisicoes_total":  0,
    "requisicoes_erro":   0,
    "corridas_locais":    0,
    "corridas_delegadas": 0,
    "locks_adquiridos":   0,
    "locks_expirados":    0,
}

saga_transitions: dict = {}   # {("match","confirm"): 3, ...}
circuit_breaker_state = 0     # 0=CLOSED, 1=OPEN, 2=HALF_OPEN


def registrar_transicao(de: str, para: str):
    key = (de, para)
    saga_transitions[key] = saga_transitions.get(key, 0) + 1


def registrar_lock_adquirido():
    contadores["locks_adquiridos"] += 1


def registrar_lock_expirado():
    contadores["locks_expirados"] += 1
