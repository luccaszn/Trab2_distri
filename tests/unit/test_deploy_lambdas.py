import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

from botocore.exceptions import ClientError
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import sebo_deploy as d


def missing():
    return ClientError({'Error': {'Code': 'ResourceNotFoundException', 'Message': 'missing'}}, 'GetFunction')


class LambdaDouble:
    """Contrato local de AWS, não evidência de que o Learner Lab permite os writes."""
    def __init__(self):
        self.state = None
        self.url = None
        self.policy = []
        self.writes = []
        self.waiter = MagicMock()

    def get_waiter(self, name):
        return self.waiter

    def get_function(self, **kw):
        if self.state is None:
            raise missing()
        return {'Configuration': self.state.copy()}

    def create_function(self, **kw):
        self.writes.append('create')
        self.state = {k: v for k, v in kw.items() if k not in {'Code', 'Publish'}}
        self.state['Layers'] = [{'Arn': a} for a in kw['Layers']]
        self.state['CodeSha256'] = d.code_hash(kw['Code']['ZipFile'])

    def update_function_code(self, **kw):
        self.writes.append('update_code')
        self.state['CodeSha256'] = d.code_hash(kw['ZipFile'])

    def update_function_configuration(self, **kw):
        self.writes.append('update_config')
        self.state.update(kw)
        self.state['Layers'] = [{'Arn': a} for a in kw['Layers']]

    def get_function_url_config(self, **kw):
        if self.url is None:
            raise missing()
        return self.url.copy()

    def create_function_url_config(self, **kw):
        self.writes.append('create_url')
        self.url = {'FunctionUrl': 'https://abc.lambda-url.us-east-1.on.aws/', **kw}

    def update_function_url_config(self, **kw):
        self.writes.append('update_url')
        self.url.update(kw)

    def get_policy(self, **kw):
        return {'Policy': json.dumps({'Statement': self.policy})}

    def add_permission(self, **kw):
        self.writes.append('add_permission')
        condition = {'Bool': {'lambda:InvokedViaFunctionUrl': 'true'}} if kw.get('InvokedViaFunctionUrl') else {'StringEquals': {'lambda:FunctionUrlAuthType': kw['FunctionUrlAuthType']}}
        self.policy.append({'Sid': kw['StatementId'], 'Effect': 'Allow', 'Principal': {'AWS': '*'}, 'Action': kw['Action'], 'Condition': condition})

    def remove_permission(self, **kw):
        self.writes.append('remove_permission')
        self.policy[:] = [s for s in self.policy if s['Sid'] != kw['StatementId']]


def test_create_update_and_idempotent_lambda_url():
    c = LambdaDouble()
    args = {'client': c, 'name': 'sebo-listar-livros', 'package': b'zip1',
            'role': 'arn:aws:iam::123456789012:role/LabRole',
            'layer': 'arn:aws:lambda:us-east-1:123456789012:layer:sebo-common:1',
            'environment': {'TABELA_LIVROS': 'sebo-Livros'}}
    url = d.ensure_function(**args)
    assert url == 'https://abc.lambda-url.us-east-1.on.aws/'
    assert c.writes == ['create', 'create_url', 'add_permission', 'add_permission']
    assert c.state['Handler'] == 'app.lambda_handler'
    assert c.state['Runtime'] == 'python3.12'
    assert c.url['Cors'] == d.CORS
    c.writes.clear()
    assert d.ensure_function(**args) == url
    assert c.writes == []
    args['package'] = b'zip2'
    args['environment'] = {'TABELA_LIVROS': 'sebo-Livros', 'SNS_TOPIC_ARN': 'new'}
    d.ensure_function(**args)
    assert c.writes == ['update_code', 'update_config']


def test_url_access_denied_is_not_api_gateway_fallback():
    c = LambdaDouble()
    def denied(**kw):
        raise ClientError({'Error': {'Code': 'AccessDeniedException', 'Message': 'lab policy'}}, 'CreateFunctionUrlConfig')
    c.create_function_url_config = denied
    with pytest.raises(ClientError, match='AccessDeniedException'):
        d.ensure_function(c, 'sebo-listar-livros', b'zip', 'role', 'layer', {})
    assert c.writes == ['create']


def test_wrong_permission_condition_replaced_without_unrelated_removal():
    c = LambdaDouble()
    unrelated = {'Sid': 'other', 'Action': 'lambda:GetFunction'}
    c.policy = [unrelated, {'Sid': 'sebo-url-invoke', 'Action': 'lambda:InvokeFunction', 'Principal': {'AWS': '*'}, 'Condition': {}, 'Effect': 'Allow'}]
    d.ensure_permissions(c, 'sebo-listar-livros')
    assert unrelated in c.policy
    assert c.writes.count('remove_permission') == 1
    assert len(c.policy) == 3


def test_permissions_accept_aws_wildcard_principal_string():
    c = LambdaDouble()
    original = c.add_permission
    def aws_add(**kw):
        original(**kw)
        c.policy[-1]['Principal'] = '*'
    c.add_permission = aws_add
    d.ensure_permissions(c, 'sebo-listar-livros')
    c.writes.clear()
    d.ensure_permissions(c, 'sebo-listar-livros')
    assert c.writes == []


def test_lambda_cors_readback_allows_explicit_aws_defaults():
    c = LambdaDouble()
    original = c.create_function_url_config
    def aws_create(**kw):
        original(**kw)
        c.url['Cors'] = {**kw['Cors'], 'AllowCredentials': False, 'ExposeHeaders': []}
    c.create_function_url_config = aws_create
    d.ensure_function(c, 'sebo-listar-livros', b'zip', 'role', 'layer', {})
    c.writes.clear()
    d.ensure_function(c, 'sebo-listar-livros', b'zip', 'role', 'layer', {})
    assert c.writes == []


def test_main_reset_guard_no_session(monkeypatch):
    monkeypatch.setattr('boto3.Session', lambda **kwargs: pytest.fail('session antes da confirmação'))
    assert d.main(['reset']) == 1
    assert d.main(['seed']) == 1


@pytest.mark.parametrize('layout', ['backend', 'lambdas'])
def test_discover_packages_creates_real_zip_layout(tmp_path, layout):
    for suffix in d.FUNCTIONS.values():
        app = tmp_path / layout / suffix.replace('-', '_') / 'app.py'
        app.parent.mkdir(parents=True)
        app.write_text('def lambda_handler(event, context):\n    return {}\n')
    layer = tmp_path / ('backend' if layout == 'backend' else 'layers') / 'layer' / 'python' / 'sebo_common' / '__init__.py'
    layer.parent.mkdir(parents=True)
    layer.write_text('VALUE = 1\n')
    import io
    import zipfile
    packages = d.discover_packages(tmp_path)
    assert len(packages) == 5
    assert zipfile.ZipFile(io.BytesIO(packages['LISTAR'])).namelist() == ['app.py']
    assert zipfile.ZipFile(io.BytesIO(packages['LAYER'])).namelist() == ['python/sebo_common/__init__.py']
