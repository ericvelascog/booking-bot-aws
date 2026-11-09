"""Tests del almacén de conversaciones, con sus dos implementaciones.

DynamoDB se prueba contra moto: una DynamoDB de mentira, en memoria, que no
necesita cuenta de AWS ni internet. El CI la ejecuta gratis en cada PR.
"""
import boto3
import pytest
from moto import mock_aws

import session_store
from session_store import MAX_MESSAGES, SESSION_TTL_SECONDS, DynamoSessionStore, MemorySessionStore

PHONE = "34600000001"


@pytest.fixture
def dynamo_table(monkeypatch):
    # Credenciales de mentira: moto no las comprueba, pero boto3 las exige.
    # Además garantizan que un test nunca llega a tocar una cuenta real.
    monkeypatch.setenv("AWS_ACCESS_KEY_ID", "testing")
    monkeypatch.setenv("AWS_SECRET_ACCESS_KEY", "testing")
    with mock_aws():
        table = boto3.resource("dynamodb", region_name="eu-west-1").create_table(
            TableName="sessions-test",
            KeySchema=[{"AttributeName": "phone", "KeyType": "HASH"}],
            AttributeDefinitions=[{"AttributeName": "phone", "AttributeType": "S"}],
            BillingMode="PAY_PER_REQUEST",
        )
        yield table


# Cada test que usa `store` se ejecuta dos veces: con memoria y con DynamoDB
@pytest.fixture(params=["memory", "dynamodb"])
def store(request):
    if request.param == "memory":
        return MemorySessionStore()
    return DynamoSessionStore(request.getfixturevalue("dynamo_table"))


def test_a_new_number_has_no_history(store):
    assert store.get_history(PHONE) == []


def test_messages_are_kept_in_order(store):
    store.add_message(PHONE, "user", "Hola, quiero cita")
    store.add_message(PHONE, "assistant", "¿Qué día te va bien?")

    assert store.get_history(PHONE) == [
        {"role": "user", "content": "Hola, quiero cita"},
        {"role": "assistant", "content": "¿Qué día te va bien?"},
    ]


def test_only_the_last_messages_are_kept(store):
    for i in range(MAX_MESSAGES + 5):
        store.add_message(PHONE, "user", f"mensaje {i}")

    history = store.get_history(PHONE)
    assert len(history) == MAX_MESSAGES
    assert history[0]["content"] == "mensaje 5"  # los 5 más antiguos ya no están


def test_each_number_has_its_own_conversation(store):
    store.add_message(PHONE, "user", "soy el primero")
    store.add_message("34600000002", "user", "soy el segundo")

    assert store.get_history(PHONE) == [{"role": "user", "content": "soy el primero"}]


def test_clear_session_forgets_the_conversation(store):
    store.add_message(PHONE, "user", "Hola")
    store.clear_session(PHONE)

    assert store.get_history(PHONE) == []


def test_an_expired_conversation_starts_from_scratch(store, monkeypatch):
    store.add_message(PHONE, "user", "Hola")

    later = session_store._now() + SESSION_TTL_SECONDS + 1
    monkeypatch.setattr(session_store, "_now", lambda: later)

    assert store.get_history(PHONE) == []


def test_dynamodb_items_carry_the_ttl_attribute(dynamo_table, monkeypatch):
    monkeypatch.setattr(session_store, "_now", lambda: 1_000_000)
    DynamoSessionStore(dynamo_table).add_message(PHONE, "user", "Hola")

    item = dynamo_table.get_item(Key={"phone": PHONE})["Item"]
    assert item["expires_at"] == 1_000_000 + SESSION_TTL_SECONDS


def test_two_tasks_share_the_conversation_with_dynamodb(dynamo_table):
    # Dos tareas de ECS = dos procesos distintos apuntando a la misma tabla
    task_a = DynamoSessionStore(dynamo_table)
    task_b = DynamoSessionStore(dynamo_table)

    task_a.add_message(PHONE, "user", "Quiero cita el jueves")  # el ALB lo manda a la tarea A
    task_b.add_message(PHONE, "user", "A las 17:00")  # y el siguiente, a la B

    assert [m["content"] for m in task_a.get_history(PHONE)] == ["Quiero cita el jueves", "A las 17:00"]


def test_two_tasks_do_not_share_the_conversation_in_memory():
    # El problema que resuelve DynamoDB: cada proceso tiene su propia memoria
    task_a = MemorySessionStore()
    task_b = MemorySessionStore()

    task_a.add_message(PHONE, "user", "Quiero cita el jueves")

    assert task_b.get_history(PHONE) == []


def test_dynamodb_is_used_when_sessions_table_is_set(dynamo_table, monkeypatch):
    monkeypatch.setenv("SESSIONS_TABLE", "sessions-test")
    assert isinstance(session_store._build_store(), DynamoSessionStore)


def test_memory_is_used_without_sessions_table(monkeypatch):
    monkeypatch.delenv("SESSIONS_TABLE", raising=False)
    assert isinstance(session_store._build_store(), MemorySessionStore)
