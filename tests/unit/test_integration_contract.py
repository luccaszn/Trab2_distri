import importlib.util
import io
import json
from pathlib import Path
import sys
import zipfile

from botocore.exceptions import ClientError

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))
import sebo_deploy as deploy


def test_real_schemas_packages_and_template_agree():
    schemas = deploy.load_schemas(ROOT)
    template = json.loads((ROOT / 'infra/template.json').read_text())
    for key in ('Livros', 'Interesses', 'Vendas'):
        assert schemas['sebo-' + key] == template['Resources'][key]['Properties']
    packages = deploy.discover_packages(ROOT)
    assert set(packages) == {'LISTAR', 'SOLICITAR', 'CADASTRAR', 'EFETIVAR', 'LAYER'}
    for key, content in packages.items():
        names = zipfile.ZipFile(io.BytesIO(content)).namelist()
        assert names == (['python/sebo_common/__init__.py'] if key == 'LAYER' else ['app.py'])


def test_seed_has_four_books_preserves_existing_and_matches_demo(aws):
    db, _ = aws
    result = deploy.seed_data(db, confirm=True)
    assert result['created'] is True
    from sebo_common import decode
    items = {i['livroId']: i for i in map(decode, db.scan(TableName='sebo-Livros')['Items'])}
    assert {key: item['quantidade'] for key, item in items.items()} == {
        'SEED-001': 2, 'SEED-002': 1, 'SEED-003': 0, 'SEED-004': 0}
    assert items['SEED-001']['preco'] == __import__('decimal').Decimal('25.90')
    assert deploy.seed_data(db, confirm=True)['created'] is False


def test_notifications_invite_to_store_and_record_acceptance(call, book, api, monkeypatch):
    messages = []
    original = api.sns.publish
    def capture(**kwargs):
        messages.append(kwargs)
        return original(**kwargs)
    monkeypatch.setattr(api.sns, 'publish', capture)
    status, interest = call('solicitar', {'livroId': book['livroId'], 'emailCliente': 'a@example.com'})
    assert status == 200 and interest['emailEnviado']
    assert 'comparecer à livraria' in messages[0]['Message']
    record = api.get(api.interests, 'interesseId', interest['interesseId'])
    assert record['dataNotificacao'] and record['mensagemSnsId'] and record['dataAtualizacao']
    pending = call('solicitar', {'livroId': book['livroId'], 'emailCliente': 'b@example.com'})[1]
    assert 'dataNotificacao' not in api.get(api.interests, 'interesseId', pending['interesseId'])
    status, arrival = call('cadastrar', {'livroId': book['livroId'], 'titulo': 'Livro', 'autor': 'Autor', 'quantidade': 1, 'preco': 10})
    assert status == 200 and arrival['clientesReservados'] == 1
    assert 'chegar' in messages[1]['Subject']


def test_notification_audit_failure_does_not_lie_about_publish(call, book, api, monkeypatch):
    def fail(**kwargs):
        raise ClientError({'Error': {'Code': 'InternalServerError', 'Message': 'injected'}}, 'UpdateItem')
    monkeypatch.setattr(api.db, 'update_item', fail)
    status, interest = call('solicitar', {'livroId': book['livroId'], 'emailCliente': 'a@example.com'})
    assert status == 200 and interest['emailEnviado'] is True
    assert api.get(api.interests, 'interesseId', interest['interesseId'])['status'] == 'RESERVADO'
