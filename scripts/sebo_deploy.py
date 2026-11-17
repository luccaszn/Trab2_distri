"""Deploy restrito ao AWS Academy; nenhum comando roda ao importar este módulo.

Credenciais: cadeia padrão boto3 (ambiente/perfil já configurado pelo usuário).
As URLs NONE são públicas, incluindo operações de escrita: apenas demonstração.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import io
import json
import os
from pathlib import Path
import re
import sys
import zipfile

ROOT = Path(__file__).resolve().parents[1]
REGION = 'us-east-1'
TABLES = {'sebo-Livros': 'livroId', 'sebo-Interesses': 'interesseId', 'sebo-Vendas': 'vendaId'}
FUNCTIONS = {'LISTAR': 'listar-livros', 'SOLICITAR': 'solicitar-livro',
             'CADASTRAR': 'cadastrar-livro', 'EFETIVAR': 'efetivar-venda'}
ALLOWED_CONFIG = {'REGION', 'TEST_EMAIL', 'EMAILS_ASSINANTES'}
CORS = {'AllowOrigins': ['*'], 'AllowMethods': ['GET', 'POST'],
        'AllowHeaders': ['content-type'], 'MaxAge': 300}


def scoped(name):
    if not re.fullmatch(r'sebo-[A-Za-z0-9][A-Za-z0-9_-]*', name):
        raise ValueError('Recurso fora do escopo sebo-')
    return name


def load_config(path):
    config = {}
    if Path(path).exists():
        for line in Path(path).read_text(encoding='utf-8-sig').splitlines():
            line = line.strip()
            if not line or line.startswith('#'):
                continue
            key, sep, value = line.partition('=')
            if not sep or key.strip() not in ALLOWED_CONFIG:
                raise ValueError('Chave não permitida em config.env (somente configuração pública)')
            config[key.strip()] = value.strip().strip('\"\'')
    for key in ALLOWED_CONFIG:
        if key in os.environ:
            config[key] = os.environ[key]
    if config.get('REGION', REGION) != REGION:
        raise ValueError('Somente us-east-1 é permitido')
    return config


def emails(config):
    values = [x.strip().lower() for x in config.get('EMAILS_ASSINANTES', '').split(',') if x.strip()]
    test = config.get('TEST_EMAIL', '').strip().lower()
    if test:
        values.append(test)
    for email in values:
        if not re.fullmatch(r'[^\s@,]+@[^\s@,]+\.[^\s@,]+', email):
            raise ValueError('E-mail inválido na configuração; nenhum fallback é utilizado')
    return sorted(set(values))


def package_python(source, prefix=''):
    source = Path(source)
    if not source.is_dir():
        raise ValueError(f'Diretório de código ausente: {source}')
    ignored = {'__pycache__', 'boto3', 'botocore', 's3transfer', '.git', '.venv', 'tests', 'test'}
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, 'w', zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(source.rglob('*.py')):
            relative = path.relative_to(source)
            if any(part in ignored or part.startswith('.') for part in relative.parts):
                continue
            if path.is_symlink() or not path.resolve().is_relative_to(source.resolve()):
                raise ValueError('Symlink fora do pacote recusado')
            info = zipfile.ZipInfo(prefix + relative.as_posix(), (2020, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o644 << 16
            archive.writestr(info, path.read_bytes())
    if not zipfile.ZipFile(io.BytesIO(buffer.getvalue())).namelist():
        raise ValueError('Pacote Python vazio')
    return buffer.getvalue()


def code_hash(content):
    return base64.b64encode(hashlib.sha256(content).digest()).decode('ascii')


def optional(call, missing, **kwargs):
    """Só ausência documentada é convertida em None; AccessDenied propaga."""
    from botocore.exceptions import ClientError
    try:
        return call(**kwargs)
    except ClientError as exc:
        if exc.response['Error']['Code'] in missing:
            return None
        raise


def check_environment(session):
    if session.region_name != REGION:
        raise ValueError('Somente us-east-1 é permitido')
    if session.get_credentials() is None:
        raise RuntimeError('Credenciais AWS ausentes; configure o Learner Lab fora deste script')
    identity = session.client('sts', region_name=REGION).get_caller_identity()
    account = identity['Account']
    if not re.fullmatch(r'\d{12}', account):
        raise RuntimeError('Conta STS inválida')
    # Consulta somente; nunca create_role/attach_role_policy/pass-role policy edits.
    role = session.client('iam', region_name=REGION).get_role(RoleName='LabRole')['Role']
    expected = f'arn:aws:iam::{account}:role/'
    if not role['Arn'].startswith(expected) or role['Arn'].split('/')[-1] != 'LabRole':
        raise RuntimeError('LabRole não pertence à conta STS')
    return {'account': account, 'role': role['Arn'], 'region': REGION}


def _verify_table(actual, desired):
    if actual.get('KeySchema') != desired['KeySchema']:
        raise RuntimeError('KeySchema incompatível; nenhuma tabela será removida')
    attribute_types = {x['AttributeName']: x['AttributeType'] for x in actual.get('AttributeDefinitions', [])}
    if attribute_types != {x['AttributeName']: x['AttributeType'] for x in desired['AttributeDefinitions']}:
        raise RuntimeError('Tipos de atributos incompatíveis; migração manual necessária')
    if actual.get('BillingModeSummary', {}).get('BillingMode') != 'PAY_PER_REQUEST':
        raise RuntimeError('Tabela existente não é PAY_PER_REQUEST; migração manual necessária')
    expected = desired.get('GlobalSecondaryIndexes', [])
    current = {x['IndexName']: x for x in actual.get('GlobalSecondaryIndexes', [])}
    if set(current) != {x['IndexName'] for x in expected}:
        raise RuntimeError('Índices incompatíveis; migração manual necessária')
    for index in expected:
        for field in ['KeySchema', 'Projection']:
            if current[index['IndexName']][field] != index[field]:
                raise RuntimeError('GSI incompatível; migração manual necessária')


def load_schemas(root):
    schemas = {}
    for path in sorted((root / 'infra').glob('tabela_*.json')):
        data = json.loads(path.read_text(encoding='utf-8-sig'))
        name = scoped(data['TableName'])
        if name not in TABLES or data.get('BillingMode') != 'PAY_PER_REQUEST':
            raise ValueError('Schema fora do contrato de tabelas')
        if data['KeySchema'] != [{'AttributeName': TABLES[name], 'KeyType': 'HASH'}]:
            raise ValueError('Chave primária fora do contrato')
        if name in schemas:
            raise ValueError('Schema duplicado')
        schemas[name] = data
    if set(schemas) != set(TABLES):
        raise ValueError('Esperados três schemas infra/tabela_*.json')
    expected = [{'IndexName': 'livroId-status-index', 'KeySchema': [
        {'AttributeName': 'livroId', 'KeyType': 'HASH'},
        {'AttributeName': 'status', 'KeyType': 'RANGE'}], 'Projection': {'ProjectionType': 'ALL'}}]
    if schemas['sebo-Interesses'].get('GlobalSecondaryIndexes') != expected:
        raise ValueError('GSI de interesses fora do contrato')
    return schemas


def ensure_tables(client, schemas):
    result = {}
    for name, schema in schemas.items():
        scoped(name)
        if name not in TABLES or schema.get('TableName') != name:
            raise ValueError('Schema de tabela fora do escopo esperado')
        found = optional(client.describe_table, {'ResourceNotFoundException'}, TableName=name)
        if found is None:
            client.create_table(**schema)
        client.get_waiter('table_exists').wait(TableName=name, WaiterConfig={'Delay': 2, 'MaxAttempts': 90})
        table = client.describe_table(TableName=name)['Table']
        _verify_table(table, schema)
        if table['TableStatus'] != 'ACTIVE':
            raise RuntimeError('Tabela ainda não está ACTIVE')
        result[name] = table['TableArn']
    return result


def ensure_topic(client, account):
    arn = client.create_topic(Name=scoped('sebo-notificacoes'))['TopicArn']
    if arn != f'arn:aws:sns:{REGION}:{account}:sebo-notificacoes':
        raise RuntimeError('Tópico SNS fora da conta/região esperadas')
    if client.get_topic_attributes(TopicArn=arn)['Attributes']['TopicArn'] != arn:
        raise RuntimeError('Readback SNS divergente')
    return arn


def ensure_subscriptions(client, topic, addresses):
    if not re.fullmatch(r'arn:aws:sns:us-east-1:\d{12}:sebo-notificacoes', topic):
        raise ValueError('Tópico fora do escopo permitido')
    subscriptions = []
    for page in client.get_paginator('list_subscriptions_by_topic').paginate(TopicArn=topic):
        subscriptions.extend(page['Subscriptions'])
    status = []
    for email in addresses:
        matches = [s for s in subscriptions if s['Protocol'] == 'email' and s['Endpoint'].lower() == email]
        policy = json.dumps({'emailCliente': [email]}, separators=(',', ':'))
        # PendingConfirmation não é um ARN utilizável em set_subscription_attributes.
        # subscribe idempotente retorna o ARN real e preserva a confirmação humana.
        if len(matches) > 1:
            raise RuntimeError('Assinaturas duplicadas; revisar SNS manualmente')
        arn = matches[0]['SubscriptionArn'] if matches else ''
        if not arn.startswith(topic + ':'):
            arn = client.subscribe(TopicArn=topic, Protocol='email', Endpoint=email,
                                   Attributes={'FilterPolicy': policy, 'FilterPolicyScope': 'MessageAttributes'},
                                   ReturnSubscriptionArn=True)['SubscriptionArn']
        if not arn.startswith(topic + ':'):
            raise RuntimeError('SNS não retornou ARN confirmável')
        attrs = client.get_subscription_attributes(SubscriptionArn=arn)['Attributes']
        if json.loads(attrs.get('FilterPolicy', '{}')) != {'emailCliente': [email]}:
            client.set_subscription_attributes(SubscriptionArn=arn, AttributeName='FilterPolicy', AttributeValue=policy)
        if attrs.get('FilterPolicyScope') != 'MessageAttributes':
            client.set_subscription_attributes(SubscriptionArn=arn, AttributeName='FilterPolicyScope', AttributeValue='MessageAttributes')
        attrs = client.get_subscription_attributes(SubscriptionArn=arn)['Attributes']
        if json.loads(attrs.get('FilterPolicy', '{}')) != {'emailCliente': [email]}:
            raise RuntimeError('Filtro SNS divergente')
        if attrs.get('FilterPolicyScope') != 'MessageAttributes':
            raise RuntimeError('Escopo do filtro SNS divergente')
        status.append({'arn': arn, 'pending_confirmation': attrs.get('PendingConfirmation') == 'true'})
    return status


def ensure_layer(client, package):
    digest = code_hash(package)
    for page in client.get_paginator('list_layer_versions').paginate(LayerName=scoped('sebo-common')):
        for version in page['LayerVersions']:
            detail = client.get_layer_version(LayerName='sebo-common', VersionNumber=version['Version'])
            if detail['Content']['CodeSha256'] == digest and 'python3.12' in detail.get('CompatibleRuntimes', []):
                return detail['LayerVersionArn']
    created = client.publish_layer_version(LayerName='sebo-common', Content={'ZipFile': package},
                                           CompatibleRuntimes=['python3.12'], Description='sha256:' + hashlib.sha256(package).hexdigest())
    readback = client.get_layer_version(LayerName='sebo-common', VersionNumber=created['Version'])
    if readback['Content']['CodeSha256'] != digest:
        raise RuntimeError('Hash da layer divergente')
    return readback['LayerVersionArn']


def _policy(client, name):
    response = optional(client.get_policy, {'ResourceNotFoundException'}, FunctionName=scoped(name))
    return json.loads(response['Policy']).get('Statement', []) if response else []


def ensure_permissions(client, name):
    specs = [
        ('sebo-url-public', 'lambda:InvokeFunctionUrl', {'FunctionUrlAuthType': 'NONE'},
         {'StringEquals': {'lambda:FunctionUrlAuthType': 'NONE'}}),
        ('sebo-url-invoke', 'lambda:InvokeFunction', {'InvokedViaFunctionUrl': True},
         {'Bool': {'lambda:InvokedViaFunctionUrl': 'true'}}),
    ]
    for sid, action, extra, condition in specs:
        statements = _policy(client, name)
        current = next((s for s in statements if s['Sid'] == sid), None)
        expected_principals = ('*', {'AWS': '*'})
        if current and (current.get('Action') != action or current.get('Effect') != 'Allow'
                        or current.get('Principal') not in expected_principals or current.get('Condition') != condition):
            client.remove_permission(FunctionName=name, StatementId=sid)
            current = None
        if current is None:
            client.add_permission(FunctionName=name, StatementId=sid, Action=action, Principal='*', **extra)
        verified = next((s for s in _policy(client, name) if s['Sid'] == sid), None)
        if not verified or verified.get('Action') != action or verified.get('Condition') != condition or verified.get('Principal') not in expected_principals or verified.get('Effect') != 'Allow':
            raise RuntimeError('Readback de permissão divergente')


def cors_matches(actual):
    # O serviço pode retornar defaults explícitos omitidos na requisição.
    defaults = {'AllowCredentials': False, 'ExposeHeaders': []}
    return {**defaults, **(actual or {})} == {**defaults, **CORS}


def ensure_function(client, name, package, role, layer, environment):
    scoped(name)
    config = {'Role': role, 'Runtime': 'python3.12', 'Handler': 'app.lambda_handler',
              'Timeout': 30, 'MemorySize': 256, 'Environment': {'Variables': environment},
              'Layers': [layer]}
    found = optional(client.get_function, {'ResourceNotFoundException'}, FunctionName=name)
    if found is None:
        client.create_function(FunctionName=name, Code={'ZipFile': package}, Publish=False, **config)
        client.get_waiter('function_active_v2').wait(FunctionName=name)
    else:
        current = found['Configuration']
        client.get_waiter('function_updated_v2').wait(FunctionName=name)
        if current['CodeSha256'] != code_hash(package):
            client.update_function_code(FunctionName=name, ZipFile=package, Publish=False)
            client.get_waiter('function_updated_v2').wait(FunctionName=name)
        changed = any(current.get(k) != v for k, v in config.items() if k != 'Layers')
        changed = changed or [x['Arn'] for x in current.get('Layers', [])] != [layer]
        if changed:
            client.update_function_configuration(FunctionName=name, **config)
            client.get_waiter('function_updated_v2').wait(FunctionName=name)
    actual = client.get_function(FunctionName=name)['Configuration']
    for key, value in config.items():
        check = [x['Arn'] for x in actual.get('Layers', [])] if key == 'Layers' else actual.get(key)
        if check != value:
            raise RuntimeError(f'Configuração Lambda divergente: {key}')
    if actual['CodeSha256'] != code_hash(package):
        raise RuntimeError('Hash Lambda divergente')
    found_url = optional(client.get_function_url_config, {'ResourceNotFoundException'}, FunctionName=name)
    if found_url is None:
        client.create_function_url_config(FunctionName=name, AuthType='NONE', Cors=CORS)
    elif found_url.get('AuthType') != 'NONE' or not cors_matches(found_url.get('Cors')):
        client.update_function_url_config(FunctionName=name, AuthType='NONE', Cors=CORS)
    ensure_permissions(client, name)
    url = client.get_function_url_config(FunctionName=name)
    if url['AuthType'] != 'NONE' or not cors_matches(url.get('Cors')):
        raise RuntimeError('Readback da URL/CORS divergente')
    return url['FunctionUrl']


def discover_packages(root):
    root = Path(root)
    packages = {}
    app_roots = [root / 'lambdas', root / 'backend']
    for key, suffix in FUNCTIONS.items():
        candidates = [p.parent for directory in app_roots for p in directory.rglob('app.py')
                      if p.parent.name.replace('_', '-').removeprefix('sebo-') == suffix]
        if len(candidates) != 1:
            raise ValueError(f'Esperado lambdas/sebo-{suffix}/app.py único (ou backend equivalente)')
        packages[key] = package_python(candidates[0])
    candidates = [p for directory in (root / 'layers', root / 'backend')
                  for p in directory.rglob('sebo_common/__init__.py')]
    if len(candidates) != 1:
        raise ValueError('Esperado layers/**/sebo_common/__init__.py único (ou backend equivalente)')
    # A raiz contém somente o pacote compartilhado, não apps ou boto3.
    shared = candidates[0].parent
    packages['LAYER'] = package_python(shared, prefix='python/sebo_common/')
    return packages


def deploy(session, root, config):
    addresses = emails(config)
    schemas = load_schemas(root)
    packages = discover_packages(root)  # falhar antes de qualquer write se código ausente
    identity = check_environment(session)
    tables = ensure_tables(session.client('dynamodb', region_name=REGION), schemas)
    sns = session.client('sns', region_name=REGION)
    topic = ensure_topic(sns, identity['account'])
    subscriptions = ensure_subscriptions(sns, topic, addresses)
    lambdas = session.client('lambda', region_name=REGION)
    layer = ensure_layer(lambdas, packages['LAYER'])
    environment = {'TABELA_LIVROS': 'sebo-Livros', 'TABELA_INTERESSES': 'sebo-Interesses',
                   'TABELA_VENDAS': 'sebo-Vendas', 'SNS_TOPIC_ARN': topic}
    urls = {f'URL_{key}': ensure_function(lambdas, 'sebo-' + suffix, packages[key],
                                        identity['role'], layer, environment)
            for key, suffix in FUNCTIONS.items()}
    manifest = {**identity, 'tables': tables, 'topic': topic, 'subscriptions': subscriptions,
                'layer': layer, 'urls': urls}
    (root / 'build').mkdir(exist_ok=True)
    (root / 'build' / 'deployment.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    (root / 'frontend' / 'config.js').write_text('window.SEBO_CONFIG = ' + json.dumps(urls, indent=2) + ';\n', encoding='utf-8')
    return manifest


def status(session):
    """Readback público somente leitura; não publica nem assina tópicos."""
    identity = check_environment(session)
    dynamo = session.client('dynamodb', region_name=REGION)
    tables = {}
    for name in TABLES:
        response = optional(dynamo.describe_table, {'ResourceNotFoundException'}, TableName=scoped(name))
        tables[name] = response['Table'] if response else None
    sns = session.client('sns', region_name=REGION)
    topic = f"arn:aws:sns:{REGION}:{identity['account']}:sebo-notificacoes"
    attributes = optional(sns.get_topic_attributes, {'NotFound', 'NotFoundException'}, TopicArn=topic)
    subscriptions = []
    if attributes:
        for page in sns.get_paginator('list_subscriptions_by_topic').paginate(TopicArn=topic):
            for sub in page['Subscriptions']:
                arn = sub['SubscriptionArn']
                item = {'arn': arn, 'protocol': sub['Protocol'], 'pending_confirmation': arn == 'PendingConfirmation'}
                if arn.startswith(topic + ':'):
                    readback = sns.get_subscription_attributes(SubscriptionArn=arn)['Attributes']
                    item['pending_confirmation'] = readback.get('PendingConfirmation') == 'true'
                    item['filter_policy'] = json.loads(readback.get('FilterPolicy', '{}'))
                    item['filter_scope'] = readback.get('FilterPolicyScope')
                subscriptions.append(item)
    lambdas = session.client('lambda', region_name=REGION)
    functions = {}
    for suffix in FUNCTIONS.values():
        name = scoped('sebo-' + suffix)
        response = optional(lambdas.get_function, {'ResourceNotFoundException'}, FunctionName=name)
        functions[name] = None if response is None else {
            'configuration': {key: response['Configuration'][key]
                              for key in ('FunctionName', 'Runtime', 'Role', 'Handler', 'CodeSha256',
                                          'LastUpdateStatus', 'State', 'Layers')
                              if key in response['Configuration']},
            'url': optional(lambdas.get_function_url_config, {'ResourceNotFoundException'}, FunctionName=name),
            'permissions': _policy(lambdas, name)}
    return {**identity, 'tables': tables, 'topic_exists': attributes is not None,
            'subscriptions': subscriptions, 'functions': functions}


def reset_data(client, confirm=False):
    if not confirm:
        raise ValueError('Reset exige --confirm; remove TODOS os itens das três tabelas sebo-')
    deleted = {}
    for name, key in TABLES.items():
        scoped(name)
        count = 0
        for page in client.get_paginator('scan').paginate(TableName=name, ProjectionExpression='#pk', ExpressionAttributeNames={'#pk': key}, ConsistentRead=True):
            for item in page.get('Items', []):
                client.delete_item(TableName=name, Key={key: item[key]})
                count += 1
        # Operação exige ambiente ocioso; concorrência pode recriar itens.
        remaining = sum(page['Count'] for page in client.get_paginator('scan').paginate(
            TableName=name, Select='COUNT', ConsistentRead=True))
        if remaining:
            raise RuntimeError('Reset não esvaziou a tabela; interrompa escritores e tente novamente')
        deleted[name] = count
    return deleted


def seed_data(client, confirm=False):
    if not confirm:
        raise ValueError('Seed exige --confirm (escrita AWS explícita)')
    from decimal import Decimal
    from boto3.dynamodb.types import TypeSerializer
    from botocore.exceptions import ClientError
    serializer = TypeSerializer()
    items = json.loads((ROOT / 'infra' / 'livros_seed.json').read_text(encoding='utf-8'), parse_float=Decimal)
    name = scoped('sebo-Livros')
    created = []
    for source in items:
        item = {key: serializer.serialize(value) for key, value in source.items()}
        try:
            client.put_item(TableName=name, Item=item, ConditionExpression='attribute_not_exists(livroId)')
        except ClientError as exc:
            if exc.response['Error']['Code'] == 'ConditionalCheckFailedException':
                continue
            raise
        actual = client.get_item(TableName=name, Key={'livroId': item['livroId']}, ConsistentRead=True).get('Item')
        if actual != item:
            raise RuntimeError('Readback seed divergente; execute seed com a aplicação ociosa')
        created.append(source['livroId'])
    return {'created': bool(created), 'created_ids': created}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command', choices=['check', 'status', 'package', 'deploy', 'seed', 'reset'])
    parser.add_argument('--confirm', action='store_true', help='Autoriza escrita seed/reset explicitamente')
    args = parser.parse_args(argv)
    try:
        if args.command in {'seed', 'reset'} and not args.confirm:
            raise ValueError(f'{args.command} exige --confirm; nenhuma chamada AWS executada')
        config = load_config(ROOT / 'config.env')
        if args.command == 'package':
            packages = discover_packages(ROOT)
            output = ROOT / 'build'
            output.mkdir(exist_ok=True)
            for name, content in packages.items():
                (output / f'{name.lower()}.zip').write_bytes(content)
            print(json.dumps({k: code_hash(v) for k, v in packages.items()}, indent=2))
            return 0
        import boto3
        session = boto3.Session(region_name=REGION)
        if args.command == 'deploy':
            result = deploy(session, ROOT, config)
            print('Deploy verificado; manifesto público em build/deployment.json.')
            pending = sum(x['pending_confirmation'] for x in result['subscriptions'])
            print(f'Assinaturas pendentes de confirmação humana: {pending}. SNS aceito não prova entrega.')
        elif args.command == 'status':
            print(json.dumps(status(session), indent=2, default=str))
        else:
            identity = check_environment(session)
            if args.command == 'check':
                print(json.dumps(identity, indent=2))
            else:
                client = session.client('dynamodb', region_name=REGION)
                result = seed_data(client, args.confirm) if args.command == 'seed' else reset_data(client, args.confirm)
                print(json.dumps(result, indent=2))
        return 0
    except (ValueError, RuntimeError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    except ModuleNotFoundError as exc:
        print('Dependência Python ausente: ' + str(exc.name) + '; instale requirements.txt no venv.', file=sys.stderr)
        return 1
    except Exception as exc:
        # Não despejar requisições, credenciais, tokens nem respostas completas de SDK.
        from botocore.exceptions import BotoCoreError, ClientError
        if isinstance(exc, ClientError):
            print('Falha AWS: ' + exc.response['Error']['Code'] + ' (não tratado como ausência).', file=sys.stderr)
        elif isinstance(exc, BotoCoreError):
            print('Falha AWS de credenciais/conexão: ' + type(exc).__name__, file=sys.stderr)
        else:
            print('Falha: ' + type(exc).__name__ + '; nenhuma conclusão de sucesso.', file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
