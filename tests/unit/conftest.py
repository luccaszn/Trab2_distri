"""Isolated moto AWS services; never uses real AWS endpoints."""
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'layers' / 'sebo-common' / 'python'))

import boto3
import pytest
from moto import mock_aws


@pytest.fixture
def aws(monkeypatch):
    for key, value in {
        'AWS_ACCESS_KEY_ID': 'testing', 'AWS_SECRET_ACCESS_KEY': 'testing',
        'AWS_SESSION_TOKEN': 'testing', 'AWS_DEFAULT_REGION': 'us-east-1',
        'AWS_EC2_METADATA_DISABLED': 'true', 'TABELA_LIVROS': 'sebo-Livros',
        'TABELA_INTERESSES': 'sebo-Interesses', 'TABELA_VENDAS': 'sebo-Vendas',
    }.items():
        monkeypatch.setenv(key, value)
    with mock_aws():
        db = boto3.client('dynamodb', region_name='us-east-1')
        import json
        for schema in sorted((ROOT / 'infra').glob('tabela_*.json')):
            db.create_table(**json.loads(schema.read_text(encoding='utf-8')))
        sns = boto3.client('sns', region_name='us-east-1')
        arn = sns.create_topic(Name='sebo-notificacoes')['TopicArn']
        monkeypatch.setenv('SNS_TOPIC_ARN', arn)
        yield db, sns


@pytest.fixture
def api(aws):
    import sebo_common
    return sebo_common.Backend(db=aws[0], sns=aws[1])


@pytest.fixture
def call(api):
    import json
    def invoke(action, payload=None, query=None, **event_extra):
        event = {'requestContext': {'http': {'method': 'GET' if action == 'listar' else 'POST'}},
                 'body': json.dumps(payload) if payload is not None else None,
                 'queryStringParameters': query or {}}
        event.update(event_extra)
        response = api.handle(action, event)
        return response['statusCode'], json.loads(response['body'])
    return invoke


@pytest.fixture
def book(call):
    status, body = call('cadastrar', {'livroId': 'LIV-TEST', 'titulo': 'Livro', 'autor': 'Autor', 'quantidade': 1, 'preco': 12.50})
    assert status == 200, body
    return body['livro']
