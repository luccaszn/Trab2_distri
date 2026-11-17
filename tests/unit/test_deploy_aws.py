"""AWS simulada: nenhum teste usa credenciais ou endpoints reais."""
import io
import json
import sys
import zipfile
from pathlib import Path
from unittest.mock import MagicMock

import boto3
from botocore.exceptions import ClientError
from botocore.stub import Stubber
from moto import mock_aws
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'scripts'))
import sebo_deploy as d


def client(service):
    return boto3.client(service, region_name='us-east-1', aws_access_key_id='testing', aws_secret_access_key='testing')


def schema(name, key):
    return {'TableName': name, 'KeySchema': [{'AttributeName': key, 'KeyType': 'HASH'}],
            'AttributeDefinitions': [{'AttributeName': key, 'AttributeType': 'S'}], 'BillingMode': 'PAY_PER_REQUEST'}


def test_access_denied_is_not_absence():
    c = client('dynamodb')
    with Stubber(c) as stub:
        stub.add_client_error('describe_table', service_error_code='AccessDeniedException', expected_params={'TableName': 'sebo-Livros'})
        with pytest.raises(ClientError, match='AccessDeniedException'):
            d.optional(c.describe_table, {'ResourceNotFoundException'}, TableName='sebo-Livros')
        stub.assert_no_pending_responses()


def test_missing_credentials_stops_before_aws():
    session = MagicMock(region_name='us-east-1')
    session.get_credentials.return_value = None
    with pytest.raises(RuntimeError, match='Credenciais'):
        d.check_environment(session)
    session.client.assert_not_called()


def test_check_is_read_only_and_uses_existing_labrole():
    session = MagicMock(region_name='us-east-1')
    sts, iam = MagicMock(), MagicMock()
    session.client.side_effect = [sts, iam]
    sts.get_caller_identity.return_value = {'Account': '123456789012'}
    iam.get_role.return_value = {'Role': {'Arn': 'arn:aws:iam::123456789012:role/LabRole'}}
    assert d.check_environment(session)['account'] == '123456789012'
    assert [c[0] for c in iam.mock_calls] == ['get_role']


@mock_aws
def test_tables_seed_reset_idempotency():
    c = client('dynamodb')
    schemas = {name: schema(name, key) for name, key in d.TABLES.items()}
    first = d.ensure_tables(c, schemas)
    assert d.ensure_tables(c, schemas) == first
    assert d.seed_data(c, confirm=True)['created'] is True
    assert d.seed_data(c, confirm=True)['created'] is False
    assert d.reset_data(c, confirm=True)['sebo-Livros'] == 4
    assert sum(d.reset_data(c, confirm=True).values()) == 0


@mock_aws
def test_confirmed_sns_subscription_filter_readback():
    c = client('sns')
    topic = d.ensure_topic(c, '123456789012')
    first = d.ensure_subscriptions(c, topic, ['reader@example.org'])
    second = d.ensure_subscriptions(c, topic, ['reader@example.org'])
    assert first == second
    assert len(c.list_subscriptions_by_topic(TopicArn=topic)['Subscriptions']) == 1
    attrs = c.get_subscription_attributes(SubscriptionArn=first[0]['arn'])['Attributes']
    assert json.loads(attrs['FilterPolicy']) == {'emailCliente': ['reader@example.org']}


def test_pending_sns_uses_returned_arn_not_pending_literal():
    c = MagicMock()
    topic = 'arn:aws:sns:us-east-1:123456789012:sebo-notificacoes'
    arn = topic + ':pending-id'
    c.get_paginator.return_value.paginate.return_value = [{'Subscriptions': [
        {'Protocol': 'email', 'Endpoint': 'reader@example.org', 'SubscriptionArn': 'PendingConfirmation'}]}]
    c.subscribe.return_value = {'SubscriptionArn': arn}
    c.get_subscription_attributes.return_value = {'Attributes': {
        'FilterPolicy': '{"emailCliente":["reader@example.org"]}', 'PendingConfirmation': 'true',
        'FilterPolicyScope': 'MessageAttributes'}}
    assert d.ensure_subscriptions(c, topic, ['reader@example.org'])[0]['pending_confirmation']
    assert c.subscribe.call_args.kwargs['ReturnSubscriptionArn'] is True
    assert all(x.kwargs['SubscriptionArn'] == arn for x in c.set_subscription_attributes.call_args_list)


@mock_aws
def test_layer_hash_is_idempotent(tmp_path):
    c = client('lambda')
    (tmp_path / '__init__.py').write_text('VALUE=1\n')
    package = d.package_python(tmp_path, 'python/sebo_common/')
    assert zipfile.ZipFile(io.BytesIO(package)).namelist() == ['python/sebo_common/__init__.py']
    first = d.ensure_layer(c, package)
    assert d.ensure_layer(c, package) == first
    assert len(c.list_layer_versions(LayerName='sebo-common')['LayerVersions']) == 1
    (tmp_path / '__init__.py').write_text('VALUE=2\n')
    assert d.ensure_layer(c, d.package_python(tmp_path, 'python/sebo_common/')) != first


def test_permissions_include_both_current_url_permissions_and_read_back():
    c = MagicMock()
    policy = []
    c.get_policy.side_effect = lambda **kwargs: {'Policy': json.dumps({'Statement': policy})}
    def add(**kwargs):
        condition = ({'StringEquals': {'lambda:FunctionUrlAuthType': 'NONE'}}
                     if kwargs['Action'] == 'lambda:InvokeFunctionUrl'
                     else {'Bool': {'lambda:InvokedViaFunctionUrl': 'true'}})
        policy.append({'Sid': kwargs['StatementId'], 'Effect': 'Allow', 'Principal': {'AWS': '*'},
                       'Action': kwargs['Action'], 'Condition': condition})
    c.add_permission.side_effect = add
    d.ensure_permissions(c, 'sebo-listar-livros')
    d.ensure_permissions(c, 'sebo-listar-livros')
    assert c.add_permission.call_count == 2
    assert c.add_permission.call_args_list[1].kwargs['InvokedViaFunctionUrl'] is True
    c.remove_permission.assert_not_called()


def test_scope_blocks_before_lambda_write():
    c = MagicMock()
    with pytest.raises(ValueError):
        d.ensure_function(c, 'outsider', b'zip', 'role', 'layer', {})
    assert not c.mock_calls


def test_invalid_region_and_email_do_not_silently_fallback(tmp_path, monkeypatch):
    monkeypatch.setenv('REGION', 'eu-west-1')
    with pytest.raises(ValueError, match='us-east-1'):
        d.load_config(tmp_path / 'missing')
    with pytest.raises(ValueError, match='E-mail inválido'):
        d.emails({'TEST_EMAIL': 'not-an-email'})
    assert d.emails({}) == []


def test_status_is_readonly():
    session = MagicMock(region_name='us-east-1')
    sts, iam, dynamo, sns, lambdas = [MagicMock() for _ in range(5)]
    clients = {'sts': sts, 'iam': iam, 'dynamodb': dynamo, 'sns': sns, 'lambda': lambdas}
    session.client.side_effect = lambda service, **kwargs: clients[service]
    sts.get_caller_identity.return_value = {'Account': '123456789012'}
    iam.get_role.return_value = {'Role': {'Arn': 'arn:aws:iam::123456789012:role/LabRole'}}
    dynamo.describe_table.side_effect = lambda **kw: {'Table': {'TableStatus': 'ACTIVE', 'TableArn': kw['TableName']}}
    sns.get_topic_attributes.return_value = {'Attributes': {'TopicArn': 'arn:aws:sns:us-east-1:123456789012:sebo-notificacoes'}}
    sns.get_paginator.return_value.paginate.return_value = [{'Subscriptions': []}]
    lambdas.get_function_url_config.return_value = {'FunctionUrl': 'https://test.lambda-url.us-east-1.on.aws/'}
    lambdas.get_function.return_value = {'Configuration': {'Runtime': 'python3.12', 'Role': 'LabRole'}}
    lambdas.get_policy.return_value = {'Policy': '{"Statement":[]}'}
    result = d.status(session)
    assert len(result['functions']) == 4
    calls = [call[0] for c in clients.values() for call in c.mock_calls]
    assert not any(part in x for x in calls for part in ['create_', 'put_', 'delete_', 'update_', 'subscribe', 'publish_', 'add_permission'])


def test_reset_checks_all_readback_pages():
    c = MagicMock()
    c.get_paginator.return_value.paginate.side_effect = [
        [{'Items': [{'livroId': {'S': 'one'}}]}], [{'Count': 0}, {'Count': 1}]]
    with pytest.raises(RuntimeError, match='não esvaziou'):
        d.reset_data(c, confirm=True)
    assert c.delete_item.call_count == 1


def test_tables_reject_schema_name_mismatch_before_write():
    c = MagicMock()
    with pytest.raises(ValueError, match='Schema'):
        d.ensure_tables(c, {'sebo-Livros': schema('outside-prefix', 'livroId')})
    assert not c.mock_calls


def test_subscriptions_reject_unowned_topic_before_write():
    c = MagicMock()
    with pytest.raises(ValueError, match='Tópico'):
        d.ensure_subscriptions(c, 'arn:aws:sns:us-east-1:123456789012:other-topic', ['reader@example.org'])
    assert not c.mock_calls
