"""
Testes de integração com RabbitMQ real.

Pré-requisito: RabbitMQ rodando (docker-compose up)

Como rodar:
    cd ridefleet2/backend
    python test_rabbitmq.py
"""

import pika
import json
import os
import sys
import time
from datetime import datetime

RABBITMQ_URL = os.getenv("RABBITMQ_URL", "amqp://guest:guest@localhost:5672/")

FILA_ENTRADA = "fila_corridas_entrada"
FILA_SAIDA   = "fila_corridas_saida"
TTL_MS       = 10 * 60 * 1000

VERDE    = "\033[92m"
VERMELHO = "\033[91m"
RESET    = "\033[0m"

passou = 0
falhou = 0


def ok(nome):
    global passou
    passou += 1
    print(f"  {VERDE}✓ PASSOU{RESET} — {nome}")


def falha(nome, motivo):
    global falhou
    falhou += 1
    print(f"  {VERMELHO}✗ FALHOU{RESET} — {nome}: {motivo}")


def conectar():
    params = pika.URLParameters(RABBITMQ_URL)
    params.socket_timeout = 5
    return pika.BlockingConnection(params)


def declarar(channel, nome_fila):
    channel.queue_declare(
        queue=nome_fila,
        durable=True,
        arguments={"x-message-ttl": TTL_MS}
    )


def limpar_filas(channel):
    """Remove todas as mensagens antes de cada teste."""
    for fila in (FILA_ENTRADA, FILA_SAIDA):
        try:
            declarar(channel, fila)
            channel.queue_purge(fila)
        except Exception:
            pass


# ---------------------------------------------------------------------------
# Testes
# ---------------------------------------------------------------------------

def teste_conexao():
    nome = "Conectar ao RabbitMQ"
    try:
        conn = conectar()
        conn.close()
        ok(nome)
        return True
    except Exception as e:
        falha(nome, str(e))
        return False


def teste_publicar_mensagem():
    nome = "Publicar mensagem na fila de saída"
    try:
        conn = conectar()
        ch   = conn.channel()
        declarar(ch, FILA_SAIDA)
        ch.queue_purge(FILA_SAIDA)

        mensagem = json.dumps({"corrida_id": 42, "criado_em": datetime.utcnow().isoformat()})
        ch.basic_publish(
            exchange="",
            routing_key=FILA_SAIDA,
            body=mensagem,
            properties=pika.BasicProperties(delivery_mode=2)
        )
        conn.close()
        time.sleep(0.3)  # aguarda RabbitMQ registrar a mensagem

        conn = conectar()
        ch   = conn.channel()
        declarar(ch, "saida")
        result = ch.queue_declare(queue=FILA_SAIDA, durable=True,
                                   arguments={"x-message-ttl": TTL_MS})
        conn.close()

        if result.method.message_count == 1:
            ok(nome)
        else:
            falha(nome, f"esperava 1 mensagem, encontrou {result.method.message_count}")
    except Exception as e:
        falha(nome, str(e))


def teste_consumir_mensagem():
    nome = "Consumir mensagem da fila (FIFO)"
    try:
        conn = conectar()
        ch   = conn.channel()
        declarar(ch, FILA_SAIDA)
        ch.queue_purge(FILA_SAIDA)

        # publica
        payload = {"corrida_id": 99, "criado_em": datetime.utcnow().isoformat()}
        ch.basic_publish(
            exchange="",
            routing_key=FILA_SAIDA,
            body=json.dumps(payload),
            properties=pika.BasicProperties(delivery_mode=2)
        )

        # consome
        method, _, body = ch.basic_get(queue=FILA_SAIDA, auto_ack=True)
        conn.close()

        if body is None:
            falha(nome, "nenhuma mensagem recebida")
            return

        dados = json.loads(body)
        if dados["corrida_id"] == 99:
            ok(nome)
        else:
            falha(nome, f"corrida_id errado: {dados['corrida_id']}")
    except Exception as e:
        falha(nome, str(e))


def teste_fila_vazia():
    nome = "Fila vazia retorna None no basic_get"
    try:
        conn = conectar()
        ch   = conn.channel()
        declarar(ch, FILA_ENTRADA)
        ch.queue_purge(FILA_ENTRADA)

        method, _, body = ch.basic_get(queue=FILA_ENTRADA, auto_ack=True)
        conn.close()

        if body is None:
            ok(nome)
        else:
            falha(nome, "esperava fila vazia")
    except Exception as e:
        falha(nome, str(e))


def teste_ordem_fifo():
    nome = "Ordem FIFO — primeiro a entrar, primeiro a sair"
    try:
        conn = conectar()
        ch   = conn.channel()
        declarar(ch, FILA_ENTRADA)
        ch.queue_purge(FILA_ENTRADA)

        # publica 3 mensagens em ordem
        for i in [1, 2, 3]:
            ch.basic_publish(
                exchange="",
                routing_key=FILA_ENTRADA,
                body=json.dumps({"corrida_id": i, "criado_em": datetime.utcnow().isoformat()}),
                properties=pika.BasicProperties(delivery_mode=2)
            )

        # consome e verifica ordem
        ordem = []
        for _ in range(3):
            _, _, body = ch.basic_get(queue=FILA_ENTRADA, auto_ack=True)
            if body:
                ordem.append(json.loads(body)["corrida_id"])

        conn.close()

        if ordem == [1, 2, 3]:
            ok(nome)
        else:
            falha(nome, f"ordem incorreta: {ordem}")
    except Exception as e:
        falha(nome, str(e))


def teste_tamanho_fila():
    nome = "Tamanho da fila reflete mensagens publicadas"
    try:
        conn = conectar()
        ch   = conn.channel()
        declarar(ch, FILA_SAIDA)
        ch.queue_purge(FILA_SAIDA)

        # publica 5 mensagens
        for i in range(5):
            ch.basic_publish(
                exchange="",
                routing_key=FILA_SAIDA,
                body=json.dumps({"corrida_id": i, "criado_em": datetime.utcnow().isoformat()}),
                properties=pika.BasicProperties(delivery_mode=2)
            )
        conn.close()
        time.sleep(0.3)

        conn = conectar()
        ch   = conn.channel()
        declarar(ch, "saida")
        result = ch.queue_declare(queue=FILA_SAIDA, durable=True,
                                   arguments={"x-message-ttl": TTL_MS})
        conn.close()

        if result.method.message_count == 5:
            ok(nome)
        else:
            falha(nome, f"esperava 5, encontrou {result.method.message_count}")
    except Exception as e:
        falha(nome, str(e))


def teste_mensagem_persistente():
    nome = "Mensagem persistente (delivery_mode=2) sobrevive a reconexão"
    try:
        conn = conectar()
        ch   = conn.channel()
        declarar(ch, FILA_SAIDA)
        ch.queue_purge(FILA_SAIDA)

        ch.basic_publish(
            exchange="",
            routing_key=FILA_SAIDA,
            body=json.dumps({"corrida_id": 777, "criado_em": datetime.utcnow().isoformat()}),
            properties=pika.BasicProperties(delivery_mode=2)
        )
        conn.close()  # fecha a conexão

        # reabre e verifica se mensagem ainda está lá
        conn2 = conectar()
        ch2   = conn2.channel()
        result = ch2.queue_declare(queue=FILA_SAIDA, durable=True,
                                    arguments={"x-message-ttl": TTL_MS})
        conn2.close()

        if result.method.message_count == 1:
            ok(nome)
        else:
            falha(nome, f"mensagem não sobreviveu: count={result.method.message_count}")
    except Exception as e:
        falha(nome, str(e))


def teste_duas_filas_independentes():
    nome = "Fila de entrada e saída são independentes"
    try:
        conn = conectar()
        ch   = conn.channel()
        declarar(ch, FILA_ENTRADA)
        declarar(ch, FILA_SAIDA)
        ch.queue_purge(FILA_ENTRADA)
        ch.queue_purge(FILA_SAIDA)

        # 2 na entrada, 3 na saída
        for i in range(2):
            ch.basic_publish(exchange="", routing_key=FILA_ENTRADA,
                             body=json.dumps({"corrida_id": i}),
                             properties=pika.BasicProperties(delivery_mode=2))
        for i in range(3):
            ch.basic_publish(exchange="", routing_key=FILA_SAIDA,
                             body=json.dumps({"corrida_id": i}),
                             properties=pika.BasicProperties(delivery_mode=2))
        conn.close()
        time.sleep(0.3)

        conn = conectar()
        ch   = conn.channel()
        declarar(ch, FILA_ENTRADA)
        declarar(ch, FILA_SAIDA)
        r_entrada = ch.queue_declare(queue=FILA_ENTRADA, durable=True,
                                      arguments={"x-message-ttl": TTL_MS})
        r_saida   = ch.queue_declare(queue=FILA_SAIDA,   durable=True,
                                      arguments={"x-message-ttl": TTL_MS})
        conn.close()

        if r_entrada.method.message_count == 2 and r_saida.method.message_count == 3:
            ok(nome)
        else:
            falha(nome, f"entrada={r_entrada.method.message_count} saida={r_saida.method.message_count}")
    except Exception as e:
        falha(nome, str(e))


# ---------------------------------------------------------------------------
# Execução
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print(f"\n{'='*55}")
    print("  Testes de integração — RabbitMQ")
    print(f"  URL: {RABBITMQ_URL}")
    print(f"{'='*55}\n")

    # verifica conexão primeiro
    if not teste_conexao():
        print(f"\n{VERMELHO}RabbitMQ inacessível. Verifique se o Docker está rodando:{RESET}")
        print("  docker-compose up -d rabbitmq\n")
        sys.exit(1)

    # roda os demais testes
    teste_publicar_mensagem()
    teste_consumir_mensagem()
    teste_fila_vazia()
    teste_ordem_fifo()
    teste_tamanho_fila()
    teste_mensagem_persistente()
    teste_duas_filas_independentes()

    # resultado final
    total = passou + falhou
    print(f"\n{'='*55}")
    print(f"  Resultado: {passou}/{total} testes passaram")
    if falhou == 0:
        print(f"  {VERDE}Todos os testes passaram!{RESET}")
    else:
        print(f"  {VERMELHO}{falhou} teste(s) falharam.{RESET}")
    print(f"{'='*55}\n")

    sys.exit(0 if falhou == 0 else 1)
