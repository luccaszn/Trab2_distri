"""Boundary and deterministic race regressions against real moto transactions."""
import base64
import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier, Lock

import pytest


BASE = {'livroId': 'LIV-TEST', 'titulo': 'Livro', 'autor': 'Autor', 'quantidade': 1, 'preco': 10}


def race(api, monkeypatch, operations):
    # Moto is not an AWS isolation simulator. Barrier forces stale reads, and a
    # mutex only around the actual mock transaction avoids moto's own races.
    barrier, mutex, count = Barrier(2), Lock(), 0
    original = api.db.transact_write_items
    def synchronized(**kwargs):
        nonlocal count
        with mutex:
            count += 1
            first_wave = count <= 2
        if first_wave:
            barrier.wait(timeout=10)
        with mutex:
            return original(**kwargs)
    monkeypatch.setattr(api.db, 'transact_write_items', synchronized)
    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(operation) for operation in operations]
        return [future.result(timeout=20) for future in futures]


def test_concurrent_duplicate_is_one_active_interest(call, book, api, monkeypatch):
    operation = lambda: call('solicitar', {'livroId': 'LIV-TEST', 'emailCliente': 'a@example.com'})
    results = race(api, monkeypatch, [operation, operation])
    assert sorted(item[0] for item in results) == [200, 409]
    assert call('listar', query={'recurso': 'interesses'})[1]['total'] == 1
    assert api.get(api.books, 'livroId', 'LIV-TEST')['quantidade'] == 0


def test_concurrent_customers_never_negative_stock(call, book, api, monkeypatch):
    operations = [lambda address=address: call('solicitar', {'livroId': 'LIV-TEST', 'emailCliente': address}) for address in ('a@example.com', 'b@example.com')]
    results = race(api, monkeypatch, operations)
    assert [item[0] for item in results] == [200, 200]
    assert sorted(item[1]['status'] for item in results) == ['PENDENTE', 'RESERVADO']
    assert api.get(api.books, 'livroId', 'LIV-TEST')['quantidade'] == 0


def test_concurrent_arrivals_do_not_reserve_pending_twice(call, book, api, monkeypatch):
    for address in ('a@example.com', 'b@example.com'):
        assert call('solicitar', {'livroId': 'LIV-TEST', 'emailCliente': address})[0] == 200
    operation = lambda: call('cadastrar', BASE)
    results = race(api, monkeypatch, [operation, operation])
    assert [item[0] for item in results] == [200, 200]
    assert sum(item[1]['clientesNotificados'] for item in results) == 1
    assert api.get(api.books, 'livroId', 'LIV-TEST')['quantidade'] == 1
    assert all(item['status'] == 'RESERVADO' for item in call('listar', query={'recurso': 'interesses'})[1]['itens'])


def test_concurrent_sale_records_once(call, book, api, monkeypatch):
    interest = call('solicitar', {'livroId': 'LIV-TEST', 'emailCliente': 'a@example.com'})[1]
    operation = lambda: call('efetivar', {'interesseId': interest['interesseId']})
    results = race(api, monkeypatch, [operation, operation])
    assert sorted(item[0] for item in results) == [200, 409]
    assert call('listar', query={'recurso': 'vendas'})[1]['total'] == 1


@pytest.mark.parametrize('field,value', [
    ('quantidade', True), ('quantidade', 1.5), ('quantidade', 0), ('quantidade', -1), ('quantidade', '2'),
    ('preco', True), ('preco', '3.00'), ('preco', -1), ('preco', float('nan')), ('preco', float('inf')),
    ('titulo', ''), ('autor', []), ('livroId', 'LOCK-/invalido'), ('ano', True), ('ano', 2020.5), ('condicao', None),
])
def test_invalid_book_rejected_without_writes(call, field, value):
    assert call('cadastrar', {**BASE, field: value})[0] == 400
    assert call('listar', query={'recurso': 'livros'})[1]['total'] == 0


@pytest.mark.parametrize('address', ['', 'a', 'a@b', 'a b@example.com', 'a..b@example.com', '.a@example.com', 'a@example.com\n', True, None])
def test_invalid_email(call, book, address):
    assert call('solicitar', {'livroId': 'LIV-TEST', 'emailCliente': address})[0] == 400


@pytest.mark.parametrize('raw', ['null', '[]', '"text"', '{', '{"preco":NaN}', '{"preco":Infinity}', ''])
def test_invalid_json(call, raw):
    assert call('cadastrar', body=raw)[0] == 400


def test_base64_and_invalid_encoding(call):
    raw = json.dumps(BASE).encode()
    assert call('cadastrar', body=base64.b64encode(raw).decode(), isBase64Encoded=True)[0] == 200
    assert call('cadastrar', body='%%%', isBase64Encoded=True)[0] == 400
    assert call('cadastrar', body='/w==', isBase64Encoded=True)[0] == 400


def test_methods_absent_book_bad_resource_and_optional_fields(call):
    assert call('cadastrar', BASE, requestContext={'http': {'method': 'GET'}})[0] == 405
    assert call('listar', requestContext={'http': {'method': 'POST'}})[0] == 405
    assert call('solicitar', {'livroId': 'MISSING', 'emailCliente': 'a@example.com'})[0] == 404
    assert call('listar', query={'recurso': 'no'})[0] == 400
    payload = {key: value for key, value in BASE.items() if key != 'livroId'}
    code, result = call('cadastrar', {**payload, 'ano': 2020, 'condicao': 'Usado'})
    assert code == 200
    import re
    assert re.fullmatch('LIV-[A-F0-9]{8}', result['livro']['livroId'])


def test_pagination_and_sorting_omit_internal_guards(call, book, api, monkeypatch):
    call('cadastrar', {**BASE, 'livroId': 'LIV-A', 'titulo': 'abacate'})
    call('solicitar', {'livroId': 'LIV-TEST', 'emailCliente': 'a@example.com'})
    original = api.db.scan
    def small_pages(**kwargs):
        return original(**kwargs, Limit=1)
    monkeypatch.setattr(api.db, 'scan', small_pages)
    code, items = call('listar', query={'recurso': 'livros'})
    assert code == 200 and items['total'] == 2
    assert [item['titulo'] for item in items['itens']] == ['abacate', 'Livro']
    assert all('versao' not in item for item in items['itens'])
    assert call('listar', query={'recurso': 'interesses'})[1]['total'] == 1


def test_arrival_condition_failure_rolls_back_every_item(call, book, api, monkeypatch):
    call('solicitar', {'livroId': 'LIV-TEST', 'emailCliente': 'a@example.com'})
    pending = call('solicitar', {'livroId': 'LIV-TEST', 'emailCliente': 'b@example.com'})[1]
    original = api.db.transact_write_items
    def reject(**kwargs):
        kwargs['TransactItems'][1]['Put']['ExpressionAttributeValues'][':pending'] = {'S': 'INVALID'}
        return original(**kwargs)
    monkeypatch.setattr(api.db, 'transact_write_items', reject)
    assert call('cadastrar', BASE)[0] == 409
    assert api.get(api.books, 'livroId', 'LIV-TEST')['quantidade'] == 0
    assert api.get(api.interests, 'interesseId', pending['interesseId'])['status'] == 'PENDENTE'


def test_price_retains_fraction_without_truncation(call):
    code, result = call('cadastrar', {**BASE, 'preco': 1.125})
    assert code == 200 and result['livro']['preco'] == 1.125


def test_malformed_event_shapes_return_400(api):
    for event in [None, {'requestContext': []}, {'requestContext': {'http': []}}, {'httpMethod': 'GET', 'queryStringParameters': []}, {'httpMethod': 'GET', 'queryStringParameters': 'x'}, {'httpMethod': 'GET', 'queryStringParameters': {'recurso': []}}]:
        assert api.handle('listar', event)['statusCode'] == 400


def test_retry_conflicts_are_bounded_and_success_is_not_duplicated(call, api, monkeypatch):
    from botocore.exceptions import ClientError
    original = api.db.transact_write_items
    count = 0
    def transient(**kwargs):
        nonlocal count
        count += 1
        assert len(kwargs['ClientRequestToken']) == 32
        if count < 3:
            raise ClientError({'Error': {'Code': 'TransactionConflictException'}}, 'TransactWriteItems')
        return original(**kwargs)
    monkeypatch.setattr(api.db, 'transact_write_items', transient)
    assert call('cadastrar', BASE)[0] == 200
    assert count == 3
    assert api.get(api.books, 'livroId', 'LIV-TEST')['quantidade'] == 1


def test_large_fifo_arrival_rejected_without_partial_stock(call, book, api):
    from sebo_common import encode
    # Test transaction item limit without requiring 100 HTTP requests.
    for index in range(100):
        api.db.put_item(TableName=api.interests, Item=encode({'interesseId': f'INT-{index:03}', 'livroId': 'LIV-TEST',
                        'status': 'PENDENTE', 'dataCriacao': f'2026-01-01T00:00:{index:03}Z', 'emailCliente': f'u{index}@example.com'}))
    assert call('cadastrar', {**BASE, 'quantidade': 100})[0] == 409
    assert api.get(api.books, 'livroId', 'LIV-TEST')['quantidade'] == 1
    # Existing 1 plus 98 newly received = 99 reserved + one remains pending.
    code, result = call('cadastrar', {**BASE, 'quantidade': 98})
    assert code == 200 and result['clientesNotificados'] == 99
    assert result['livro']['quantidade'] == 0


def test_new_book_id_collision_never_restocks_existing(call, monkeypatch):
    from types import SimpleNamespace
    assert call('cadastrar', {**BASE, 'livroId': 'LIV-AAAAAAAA'})[0] == 200
    sequence = iter(['A' * 32, 'B' * 32])
    # Replace only the backend module reference, not uuid.uuid4 shared by botocore.
    import sebo_common
    monkeypatch.setattr(sebo_common, 'uuid', SimpleNamespace(uuid4=lambda: SimpleNamespace(hex=next(sequence))))
    def commit_with_fixed_token(self, actions):
        self.db.transact_write_items(TransactItems=actions, ClientRequestToken='0' * 32)
        return True
    monkeypatch.setattr(sebo_common.Backend, 'commit', commit_with_fixed_token)
    code, result = call('cadastrar', {k: v for k, v in BASE.items() if k != 'livroId'})
    assert code == 200 and result['livro']['livroId'] == 'LIV-BBBBBBBB'
    assert call('listar', query={'recurso': 'livros'})[1]['total'] == 2


def test_unrepresentable_price_and_surrogates_rejected(call):
    assert call('cadastrar', body=json.dumps({**BASE, 'titulo': '\ud800'}))[0] == 400
    assert call('cadastrar', body='{"titulo":"x","autor":"x","quantidade":1,"preco":1e-999}')[0] == 400
