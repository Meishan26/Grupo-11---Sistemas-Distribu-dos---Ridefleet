"""
Teste manual: dispara corridas UMA DE CADA VEZ (sequencial, nao concorrente)
ate a politica de overflow comecar a delegar ao Core.

Uso:
    python teste_ate_delegar.py [MAX_TENTATIVAS]

MAX_TENTATIVAS = trava de seguranca (default 30), caso a delegacao nunca
aconteca (ex: sempre tem motorista livre).
"""
import sys
import requests

BASE = "http://localhost:5000"
MAX_TENTATIVAS = int(sys.argv[1]) if len(sys.argv) > 1 else 30

EMAIL = "teste_overflow@ridefleet.internal"
SENHA = "teste12345"


def obter_token():
    resp = requests.post(f"{BASE}/auth/login", json={"email": EMAIL, "senha": SENHA})
    if resp.status_code == 200:
        return resp.json()["token"]

    cad = requests.post(f"{BASE}/auth/cadastro", json={
        "nome": "Teste Overflow", "email": EMAIL, "senha": SENHA,
    })
    if cad.status_code not in (200, 201, 409):
        print("Falha no cadastro:", cad.status_code, cad.text)
        sys.exit(1)

    resp = requests.post(f"{BASE}/auth/login", json={"email": EMAIL, "senha": SENHA})
    resp.raise_for_status()
    return resp.json()["token"]


def main():
    token = obter_token()
    headers = {"Authorization": f"Bearer {token}"}

    print(f"Disparando corridas sequencialmente ate delegar (max {MAX_TENTATIVAS})...\n")
    locais = 0

    for i in range(1, MAX_TENTATIVAS + 1):
        payload = {"origem": f"Rua Teste {i}", "destino": f"Avenida Destino {i}"}
        resp = requests.post(f"{BASE}/rides/solicitar", json=payload, headers=headers)

        if resp.status_code != 200:
            print(f"[{i:02d}] ERRO {resp.status_code}: {resp.text}")
            break

        dados = resp.json()
        status = dados.get("status")

        if status == "match":
            locais += 1
            print(f"[{i:02d}] LOCAL    corrida_id={dados.get('corrida_id')} "
                  f"motorista={dados.get('motorista', {}).get('nome')}")
        else:
            print(f"[{i:02d}] DELEGADA corrida_id={dados.get('corrida_id')} "
                  f"status={status} core_ride_uuid={dados.get('core_ride_uuid')}")
            print(f"\n>>> Delegou ao Core na tentativa {i} "
                  f"(depois de {locais} corridas atendidas localmente).")
            return

    print(f"\n>>> Chegou ao limite de {MAX_TENTATIVAS} tentativas sem delegar "
          f"({locais} corridas locais).")


if __name__ == "__main__":
    main()
