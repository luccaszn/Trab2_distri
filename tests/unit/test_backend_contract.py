"""Offline packaging and infrastructure contracts, no AWS deployment."""
import ast
import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


@pytest.mark.parametrize('slug,method,body', [
    ('sebo-listar-livros', 'GET', None),
    ('sebo-solicitar-livro', 'POST', '{}'),
    ('sebo-cadastrar-livro', 'POST', '{}'),
    ('sebo-efetivar-venda', 'POST', '{}'),
])
def test_actual_lambda_entrypoints(aws, slug, method, body):
    spec = importlib.util.spec_from_file_location(slug, ROOT / 'lambdas' / slug / 'app.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    event = {'requestContext': {'http': {'method': method}}, 'body': body}
    result = module.lambda_handler(event, None)
    assert result['statusCode'] == (200 if method == 'GET' else 400)
    assert not any(name.lower().startswith('access-control-') for name in result['headers'])


def test_python312_layer_source_only():
    layer = ROOT / 'layers' / 'sebo-common' / 'python'
    sources = list(layer.rglob('*.py'))
    assert sources
    assert not list(layer.rglob('boto3/__init__.py'))
    for path in sources + list((ROOT / 'lambdas').rglob('app.py')):
        ast.parse(path.read_text(encoding='utf-8'), feature_version=(3, 12))


def test_infra_matches_lab_contract():
    template = json.loads((ROOT / 'infra' / 'template.json').read_text(encoding='utf-8'))
    resources = list(template['Resources'].values())
    assert not any(item['Type'].startswith('AWS::IAM::') for item in resources)
    functions = [item['Properties'] for item in resources if item['Type'] == 'AWS::Lambda::Function']
    assert len(functions) == 4
    for item in functions:
        assert item['Runtime'] == 'python3.12' and item['Handler'] == 'app.lambda_handler'
        assert item['Role'] == {'Ref': 'LabRoleArn'}
        assert item['FunctionName'].startswith('sebo-')
        assert set(item['Environment']['Variables']) == {'TABELA_LIVROS', 'TABELA_INTERESSES', 'TABELA_VENDAS', 'SNS_TOPIC_ARN'}
    tables = [item['Properties'] for item in resources if item['Type'] == 'AWS::DynamoDB::Table']
    assert len(tables) == 3 and all(item['BillingMode'] == 'PAY_PER_REQUEST' for item in tables)
    urls = [item['Properties'] for item in resources if item['Type'] == 'AWS::Lambda::Url']
    assert len(urls) == 4 and all(item['AuthType'] == 'NONE' and 'Cors' in item for item in urls)
