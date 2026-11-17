from botocore.exceptions import ClientError


def request(call, address='a@example.com'):
    code, payload = call('solicitar', {'livroId': 'LIV-TEST', 'emailCliente': address})
    assert code == 200, payload
    return payload


def test_arrival_reserves_fifo_with_tie_break(call, book, api):
    request(call, 'first@example.com')
    pending = [request(call, f'user{i}@example.com') for i in range(3)]
    from sebo_common import encode
    # Explicit timestamps make the deterministic FIFO ordering observable.
    for index, item in enumerate(pending):
        api.db.update_item(TableName=api.interests, Key=encode({'interesseId': item['interesseId']}),
                           UpdateExpression='SET dataCriacao = :d', ExpressionAttributeValues=encode({':d': '2026-01-01T00:00:00Z'}))
    expected = sorted(pending, key=lambda item: item['interesseId'])
    code, result = call('cadastrar', {'livroId': 'LIV-TEST', 'titulo': 'Livro', 'autor': 'Autor', 'quantidade': 2, 'preco': 15})
    assert code == 200, result
    assert result['livro']['quantidade'] == 0
    assert result['clientesNotificados'] == 2
    assert len(result['emailsNotificados']) == 2
    states = {item['interesseId']: item['status'] for item in call('listar', query={'recurso': 'interesses'})[1]['itens']}
    assert [states[item['interesseId']] for item in expected] == ['RESERVADO', 'RESERVADO', 'PENDENTE']


def test_sale_atomic_and_repeat_rejected(call, book, api, monkeypatch):
    interest = request(call)
    original = api.db.transact_write_items
    def fail(**kwargs):
        raise ClientError({'Error': {'Code': 'InternalServerError', 'Message': 'injected'}}, 'TransactWriteItems')
    monkeypatch.setattr(api.db, 'transact_write_items', fail)
    assert call('efetivar', {'interesseId': interest['interesseId']})[0] == 503
    assert call('listar', query={'recurso': 'vendas'})[1]['total'] == 0
    assert api.get(api.interests, 'interesseId', interest['interesseId'])['status'] == 'RESERVADO'
    monkeypatch.setattr(api.db, 'transact_write_items', original)
    code, sale = call('efetivar', {'interesseId': interest['interesseId']})
    assert code == 200 and sale['status'] == 'VENDIDO'
    assert sale['venda']['valor'] == 12.5
    code, repeated = call('efetivar', {'interesseId': interest['interesseId']})
    assert code == 409 and repeated['statusAtual'] == 'VENDIDO'
    assert call('listar', query={'recurso': 'vendas'})[1]['total'] == 1
    assert call('listar', query={'recurso': 'livros'})[1]['itens'][0]['quantidade'] == 0
    # A new interest after sale is valid, unlike a second active interest.
    assert request(call)['status'] == 'PENDENTE'


def test_sns_failure_keeps_committed_reservation_and_arrival(call, book, api, monkeypatch):
    def fail(**kwargs):
        raise ClientError({'Error': {'Code': 'InternalError', 'Message': 'injected'}}, 'Publish')
    monkeypatch.setattr(api.sns, 'publish', fail)
    first = request(call)
    assert first['status'] == 'RESERVADO' and first['emailEnviado'] is False
    second = request(call, 'b@example.com')
    code, arrival = call('cadastrar', {'livroId': 'LIV-TEST', 'titulo': 'Livro', 'autor': 'Autor', 'quantidade': 1, 'preco': 20})
    assert code == 200 and arrival['livro']['quantidade'] == 0
    assert arrival['clientesNotificados'] == 0 and arrival['emailsNotificados'] == []
    assert api.get(api.interests, 'interesseId', second['interesseId'])['status'] == 'RESERVADO'


def test_sale_condition_failure_rolls_back_transition_and_sale(call, book, api, monkeypatch):
    interest = request(call)
    original = api.db.transact_write_items
    def reject(**kwargs):
        kwargs['TransactItems'][-1]['Delete']['ExpressionAttributeValues'][':owner'] = {'S': 'wrong-owner'}
        return original(**kwargs)
    monkeypatch.setattr(api.db, 'transact_write_items', reject)
    assert call('efetivar', {'interesseId': interest['interesseId']})[0] == 409
    assert api.get(api.interests, 'interesseId', interest['interesseId'])['status'] == 'RESERVADO'
    assert call('listar', query={'recurso': 'vendas'})[1]['total'] == 0


def test_arrival_uses_creation_date_before_id(call, book, api):
    request(call)
    earliest = request(call, 'early@example.com')
    latest = request(call, 'late@example.com')
    from sebo_common import encode
    api.db.update_item(TableName=api.interests, Key=encode({'interesseId': earliest['interesseId']}),
                       UpdateExpression='SET dataCriacao = :d', ExpressionAttributeValues=encode({':d': '2020-01-01T00:00:00Z'}))
    code, result = call('cadastrar', {'livroId': 'LIV-TEST', 'titulo': 'Livro', 'autor': 'Autor', 'quantidade': 1, 'preco': 10})
    assert code == 200 and result['emailsNotificados'] == ['early@example.com']
    assert api.get(api.interests, 'interesseId', latest['interesseId'])['status'] == 'PENDENTE'


def test_sale_pending_and_missing(call, book):
    request(call)
    pending = request(call, 'b@example.com')
    assert call('efetivar', {'interesseId': pending['interesseId']}) == (409, {'erro': 'Somente interesses reservados podem ser vendidos.', 'statusAtual': 'PENDENTE'})
    assert call('efetivar', {'interesseId': 'INT-missing'})[0] == 404


def test_reservation_and_dedupe(call, book):
    code, first = call('solicitar', {'livroId': book['livroId'], 'emailCliente': '  A@Example.com '})
    assert code == 200 and first['status'] == 'RESERVADO'
    assert first['emailEnviado'] is True
    assert call('solicitar', {'livroId': book['livroId'], 'emailCliente': 'a@example.com'})[0] == 409
    assert call('listar', query={'recurso': 'livros'})[1]['itens'][0]['quantidade'] == 0
    assert call('listar', query={'recurso': 'interesses'})[1]['total'] == 1


def test_transaction_failure_rolls_back_reservation(call, book, api, monkeypatch):
    def fail(**kwargs):
        raise ClientError({'Error': {'Code': 'InternalServerError', 'Message': 'injected'}}, 'TransactWriteItems')
    monkeypatch.setattr(api.db, 'transact_write_items', fail)
    assert call('solicitar', {'livroId': book['livroId'], 'emailCliente': 'a@example.com'})[0] == 503
    assert call('listar', query={'recurso': 'livros'})[1]['itens'][0]['quantidade'] == 1
    assert call('listar', query={'recurso': 'interesses'})[1]['total'] == 0
