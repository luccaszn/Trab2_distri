"""Rede real somente com opt-in; nunca executado como parte dos testes locais.

RUN_E2E=1: GET público. RUN_E2E_WRITES=1 adicional: cria dados e pode enviar SNS.
Sem limpeza automática: os registros de teste permanecem para auditoria.
"""
import json
import os
from pathlib import Path
import re
import sys
import urllib.error
import urllib.request
import uuid

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import sebo_deploy as deploy

pytestmark = [pytest.mark.e2e, pytest.mark.skipif(os.environ.get('RUN_E2E') != '1', reason='Exige RUN_E2E=1 e deploy real verificado')]


@pytest.fixture
def urls():
    path = ROOT / 'build' / 'deployment.json'
    if not path.exists():
        pytest.fail('Sem manifesto de deploy real: build/deployment.json')
    data = json.loads(path.read_text(encoding='utf-8'))
    result = data['urls']
    assert set(result) == {'URL_' + key for key in deploy.FUNCTIONS}
    for url in result.values():
        assert re.fullmatch(r'https://[a-z0-9]+\.lambda-url\.us-east-1\.on\.aws/', url), 'URL fora do contrato'
    return result


def request(url, payload=None):
    data = json.dumps(payload).encode('utf-8') if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json', 'Origin': 'http://localhost:8000'})
    with urllib.request.urlopen(req, timeout=40) as response:
        assert response.status == 200
        assert response.headers.get('Access-Control-Allow-Origin') == '*'
        return json.load(response)


def test_public_list_readonly(urls):
    for resource in ['livros', 'interesses', 'vendas']:
        data = request(urls['URL_LISTAR'] + '?recurso=' + resource)
        assert data['recurso'] == resource
        assert isinstance(data['itens'], list)
        assert data['total'] == len(data['itens'])


@pytest.mark.skipif(os.environ.get('RUN_E2E_WRITES') != '1', reason='Cria estoque/interesse/venda e pode enviar e-mail; exige RUN_E2E_WRITES=1 adicional')
def test_write_flow_requires_real_email(urls):
    config = deploy.load_config(ROOT / 'config.env')
    email = config.get('TEST_EMAIL', '').strip().lower()
    if not email or email not in deploy.emails(config):
        pytest.fail('TEST_EMAIL real obrigatório; nenhum e-mail de fallback')
    book_id = 'LIV-E2E-' + uuid.uuid4().hex[:12].upper()
    created = request(urls['URL_CADASTRAR'], {'livroId': book_id, 'titulo': 'Teste E2E explícito',
                      'autor': 'Automação', 'quantidade': 1, 'preco': 10})
    assert created['livro']['livroId'] == book_id
    interest = request(urls['URL_SOLICITAR'], {'livroId': book_id, 'emailCliente': email})
    assert interest['status'] == 'RESERVADO'
    assert interest['emailEnviado'] is True  # aceito pelo SNS != entregue
    sale = request(urls['URL_EFETIVAR'], {'interesseId': interest['interesseId']})
    assert sale['status'] == 'VENDIDO'
    assert sale['venda']['livroId'] == book_id
    books = request(urls['URL_LISTAR'] + '?recurso=livros')['itens']
    assert next(x for x in books if x['livroId'] == book_id)['quantidade'] == 0
    sales = request(urls['URL_LISTAR'] + '?recurso=vendas')['itens']
    assert any(x['vendaId'] == sale['venda']['vendaId'] for x in sales)
    pending = request(urls['URL_SOLICITAR'], {'livroId': book_id, 'emailCliente': email})
    assert pending['status'] == 'PENDENTE' and pending['emailEnviado'] is False
    arrival = request(urls['URL_CADASTRAR'], {'livroId': book_id, 'titulo': 'Teste E2E explícito',
                      'autor': 'Automação', 'quantidade': 2, 'preco': 12})
    assert arrival['livro']['quantidade'] == 1
    assert arrival['clientesReservados'] == 1 and arrival['clientesNotificados'] == 1
    assert arrival['emailsNotificados'] == [email]
    interests = request(urls['URL_LISTAR'] + '?recurso=interesses')['itens']
    assert next(x for x in interests if x['interesseId'] == pending['interesseId'])['status'] == 'RESERVADO'
    with pytest.raises(urllib.error.HTTPError) as duplicate:
        request(urls['URL_SOLICITAR'], {'livroId': book_id, 'emailCliente': email})
    assert duplicate.value.code == 409
    with pytest.raises(urllib.error.HTTPError) as sold_again:
        request(urls['URL_EFETIVAR'], {'interesseId': interest['interesseId']})
    assert sold_again.value.code == 409
