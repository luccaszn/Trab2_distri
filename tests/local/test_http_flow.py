"""Integração HTTP local: handlers reais + serviços AWS emulados, nunca AWS real."""
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request

import pytest

ROOT = Path(__file__).resolve().parents[2]


def request(origin, method, path, body=None):
    payload = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(origin + path, data=payload, method=method,
                                 headers={'Content-Type': 'application/json'})
    try:
        response = urllib.request.urlopen(req, timeout=15)
    except urllib.error.HTTPError as exc:
        response = exc
    with response:
        data = response.read()
        return response.status, json.loads(data)


@pytest.fixture
def local_server(tmp_path):
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = sock.getsockname()[1]
    origin = f'http://127.0.0.1:{port}'
    with (tmp_path / 'server.log').open('w', encoding='utf-8') as output:
        process = subprocess.Popen([sys.executable, str(ROOT / 'tools/dev_server.py'), '--port', str(port)],
                                   cwd=ROOT, stdout=output, stderr=subprocess.STDOUT)
        try:
            for _ in range(100):
                if process.poll() is not None:
                    pytest.fail((tmp_path / 'server.log').read_text(encoding='utf-8'))
                try:
                    if request(origin, 'GET', '/api/listar')[0] == 200:
                        break
                except (OSError, ValueError):
                    time.sleep(0.1)
            else:
                pytest.fail('Servidor local não respondeu no prazo')
            yield origin
        finally:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)


def test_http_disponivel_dedupe_e_venda(local_server):
    call = lambda method, path, body=None: request(local_server, method, path, body)
    status, books = call('GET', '/api/listar')
    assert status == 200 and books['total'] == 4
    payload = {'livroId': 'SEED-001', 'emailCliente': ' ANA@Exemplo.COM ', 'nomeCliente': 'Ana'}
    status, interest = call('POST', '/api/solicitar', payload)
    assert status == 200 and interest['status'] == 'RESERVADO' and interest['emailEnviado']
    assert call('POST', '/api/solicitar', payload)[0] == 409
    interests = call('GET', '/api/listar?recurso=interesses')[1]['itens']
    assert len(interests) == 1 and interests[0]['emailCliente'] == 'ana@exemplo.com'
    status, sale = call('POST', '/api/efetivar', {'interesseId': interest['interesseId']})
    assert status == 200 and sale['venda']['valor'] == 25.9
    assert call('POST', '/api/efetivar', {'interesseId': interest['interesseId']})[0] == 409
    assert call('GET', '/api/listar?recurso=vendas')[1]['total'] == 1
    # Uma venda concluída libera novo interesse do mesmo cliente.
    assert call('POST', '/api/solicitar', payload)[0] == 200


def test_http_indisponivel_chegada_fifo_e_estoque(local_server):
    ids = []
    for email in ('primeiro@example.com', 'segundo@example.com', 'terceiro@example.com'):
        status, data = request(local_server, 'POST', '/api/solicitar', {'livroId': 'SEED-003', 'emailCliente': email})
        assert status == 200 and data['status'] == 'PENDENTE' and not data['emailEnviado']
        ids.append(data['interesseId'])
    status, data = request(local_server, 'POST', '/api/cadastrar', {
        'livroId': 'SEED-003', 'titulo': 'O Alienista', 'autor': 'Machado de Assis', 'quantidade': 2, 'preco': 18})
    assert status == 200 and data['clientesNotificados'] == 2
    assert data['emailsNotificados'] == ['primeiro@example.com', 'segundo@example.com']
    items = request(local_server, 'GET', '/api/listar?recurso=interesses')[1]['itens']
    states = {i['interesseId']: i['status'] for i in items}
    assert [states[i] for i in ids] == ['RESERVADO', 'RESERVADO', 'PENDENTE']
    books = request(local_server, 'GET', '/api/listar')[1]['itens']
    assert next(i for i in books if i['livroId'] == 'SEED-003')['quantidade'] == 0


def test_http_validacao_metodos_e_emulacao_explicita(local_server):
    assert request(local_server, 'POST', '/api/solicitar', {'livroId': 'X', 'emailCliente': 'a@example.com'})[0] == 404
    assert request(local_server, 'POST', '/api/solicitar', {'livroId': 'SEED-001', 'emailCliente': ''})[0] == 400
    assert request(local_server, 'GET', '/api/listar?recurso=invalido')[0] == 400
    assert request(local_server, 'GET', '/api/solicitar')[0] == 405
    assert request(local_server, 'POST', '/api/listar', {})[0] == 404
    with urllib.request.urlopen(local_server + '/config.js') as response:
        assert '"AMBIENTE": "local"' in response.read().decode()
    req = urllib.request.Request(local_server + '/api/solicitar', data=b'{}', method='POST',
                                 headers={'Origin': 'https://untrusted.example'})
    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(req, timeout=10)
    assert error.value.code == 403
