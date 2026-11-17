"""Shared Python 3.12 backend. AWS SDK supplied by the Lambda runtime.

Only low-level DynamoDB clients are accepted: transaction AttributeValues are
serialized explicitly, never sent through boto3.resource's marshalling hooks.
"""
import base64
import binascii
import hashlib
import json
import logging
import os
import random
import re
import time
import uuid
from datetime import datetime, timezone
from decimal import Decimal, DecimalException

import boto3
from boto3.dynamodb.types import TypeDeserializer, TypeSerializer
from botocore.exceptions import BotoCoreError, ClientError

LOG = logging.getLogger(__name__)
SERIALIZER = TypeSerializer()
DESERIALIZER = TypeDeserializer()
MAX_ATTEMPTS = 5
MAX_QUANTITY = 1_000_000_000
ID_PATTERN = re.compile(r'[A-Za-z0-9][A-Za-z0-9_-]{0,79}\Z')
EMAIL_PATTERN = re.compile(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?(?:\.[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?)+\Z")


def encode(item):
    return {key: SERIALIZER.serialize(value) for key, value in item.items()}


def decode(item):
    return {key: DESERIALIZER.deserialize(value) for key, value in item.items()}


def now():
    return datetime.now(timezone.utc).isoformat(timespec='microseconds').replace('+00:00', 'Z')


def identifier(prefix):
    return prefix + uuid.uuid4().hex.upper()


class HTTPError(Exception):
    def __init__(self, code, message, **extra):
        self.code = code
        self.payload = {'erro': message, **extra}
        super().__init__(message)


def text(data, key, *, required=True, limit=300):
    value = data.get(key)
    if value is None and not required and key not in data:
        return None
    if not isinstance(value, str) or not value.strip() or len(value.strip()) > limit or any(ord(c) < 32 or 0xD800 <= ord(c) <= 0xDFFF for c in value):
        raise HTTPError(400, f'{key} inválido.')
    return value.strip()


def valid_id(data, key, required=True):
    value = text(data, key, required=required, limit=80)
    if value is not None and not ID_PATTERN.fullmatch(value):
        raise HTTPError(400, f'{key} inválido.')
    return value


def integer(data, key, minimum, maximum):
    value = data.get(key)
    if type(value) is not int or not minimum <= value <= maximum:
        raise HTTPError(400, f'{key} deve ser inteiro entre {minimum} e {maximum}.')
    return value


def price(data):
    value = data.get('preco')
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        raise HTTPError(400, 'preco inválido.')
    try:
        number = Decimal(str(value))
        if not number.is_finite() or number < 0 or number > Decimal('999999999999.99') or (number and number.adjusted() < -130):
            raise ValueError
        number = number if number else Decimal(0)
        SERIALIZER.serialize(number)
    except (DecimalException, ValueError):
        raise HTTPError(400, 'preco deve ser finito, não negativo e representável no DynamoDB (máximo 999999999999.99).') from None
    return number


def email(data):
    value = text(data, 'emailCliente', limit=254).lower()
    if not EMAIL_PATTERN.fullmatch(value) or len(value.split('@')[0]) > 64 or '..' in value or value.startswith('.') or '.@' in value:
        raise HTTPError(400, 'emailCliente inválido.')
    return value


def guard_id(book_id, email_address):
    digest = hashlib.sha256((book_id + '\0' + email_address).encode()).hexdigest()
    return 'LOCK-' + digest


def json_default(value):
    if isinstance(value, Decimal):
        return int(value) if value == value.to_integral_value() else float(value)
    raise TypeError(type(value).__name__)


def response(code, data):
    return {'statusCode': code, 'headers': {'Content-Type': 'application/json; charset=utf-8', 'Cache-Control': 'no-store'},
            'body': json.dumps(data, default=json_default, ensure_ascii=False, allow_nan=False)}


def body(event):
    raw = event.get('body')
    if not isinstance(raw, str) or len(raw) > 100_000:
        raise HTTPError(400, 'Corpo JSON obrigatório (máximo 100 KB).')
    try:
        if event.get('isBase64Encoded') is True:
            raw = base64.b64decode(raw, validate=True).decode('utf-8')
        def reject_constant(value):
            raise ValueError(value)
        data = json.loads(raw, parse_float=Decimal, parse_constant=reject_constant)
    except (ValueError, UnicodeError, binascii.Error):
        raise HTTPError(400, 'JSON ou base64 inválido.') from None
    if not isinstance(data, dict):
        raise HTTPError(400, 'O corpo deve ser objeto JSON.')
    return data


class Backend:
    def __init__(self, db=None, sns=None):
        self.db = db if db is not None else boto3.client('dynamodb')
        self.sns = sns if sns is not None else boto3.client('sns')
        self.books = os.environ.get('TABELA_LIVROS', 'sebo-Livros')
        self.interests = os.environ.get('TABELA_INTERESSES', 'sebo-Interesses')
        self.sales = os.environ.get('TABELA_VENDAS', 'sebo-Vendas')
        self.topic = os.environ.get('SNS_TOPIC_ARN', '')

    def get(self, table, key, value):
        result = self.db.get_item(TableName=table, Key=encode({key: value}), ConsistentRead=True)
        return decode(result['Item']) if 'Item' in result else None

    def scan(self, table):
        result = []
        args = {'TableName': table, 'ConsistentRead': True}
        while True:
            page = self.db.scan(**args)
            result.extend(decode(item) for item in page.get('Items', []))
            if not page.get('LastEvaluatedKey'):
                return result
            args['ExclusiveStartKey'] = page['LastEvaluatedKey']

    def put(self, table, item, key, *, previous=None):
        put = {'TableName': table, 'Item': encode(item)}
        if previous is None:
            put['ConditionExpression'] = 'attribute_not_exists(#pk)'
            put['ExpressionAttributeNames'] = {'#pk': key}
        elif 'versao' in previous:
            put['ConditionExpression'] = '#v = :v'
            put['ExpressionAttributeNames'] = {'#v': 'versao'}
            put['ExpressionAttributeValues'] = encode({':v': previous['versao']})
        else:
            put['ConditionExpression'] = 'attribute_exists(#pk) AND attribute_not_exists(#v)'
            put['ExpressionAttributeNames'] = {'#pk': key, '#v': 'versao'}
        return {'Put': put}

    def commit(self, actions):
        try:
            self.db.transact_write_items(TransactItems=actions, ClientRequestToken=uuid.uuid4().hex)
            return True
        except ClientError as exc:
            code = exc.response['Error']['Code']
            if code in ('TransactionConflictException', 'ConditionalCheckFailedException'):
                return False
            if code == 'TransactionCanceledException':
                reasons = exc.response.get('CancellationReasons', [])
                if reasons and all(r.get('Code', 'None') in ('None', 'ConditionalCheckFailed', 'TransactionConflict') for r in reasons):
                    return False
            raise

    def pause(self, attempt):
        if attempt + 1 < MAX_ATTEMPTS:
            time.sleep(random.uniform(0.002, 0.008) * (2 ** attempt))

    def notify(self, interest, book, *, arrival=False):
        try:
            subject = f"Sebo: '{book['titulo']}' " + ('acabou de chegar!' if arrival else 'está disponível!')
            result = self.sns.publish(TopicArn=self.topic, Subject=subject[:99],
                             Message=f"O livro {book['titulo']} foi reservado. Você deve comparecer à livraria para efetivar a compra. Código da reserva: {interest['interesseId']}.",
                             MessageAttributes={'emailCliente': {'DataType': 'String', 'StringValue': interest['emailCliente']}})
        except (ClientError, BotoCoreError):
            LOG.warning('sns_publish_failed interest_id=%s', interest['interesseId'])
            return False
        message_id = result['MessageId']
        LOG.info('sns_publish_accepted interest_id=%s message_id=%s', interest['interesseId'], message_id)
        try:
            self.db.update_item(TableName=self.interests, Key=encode({'interesseId': interest['interesseId']}),
                                UpdateExpression='SET dataNotificacao = :date, dataAtualizacao = :date, mensagemSnsId = :mid',
                                ConditionExpression='attribute_exists(interesseId)',
                                ExpressionAttributeValues=encode({':date': now(), ':mid': message_id}))
        except (ClientError, BotoCoreError):
            # The message was accepted already; audit failure cannot undo that fact.
            LOG.warning('notification_audit_failed interest_id=%s', interest['interesseId'])
        return True

    def handle(self, action, event):
        try:
            if not isinstance(event, dict):
                raise HTTPError(400, 'Evento inválido.')
            context = event.get('requestContext', {})
            query = event.get('queryStringParameters')
            if not isinstance(context, dict) or not isinstance(context.get('http', {}), dict) or (query is not None and not isinstance(query, dict)):
                raise HTTPError(400, 'Formato do evento HTTP inválido.')
            expected = 'GET' if action == 'listar' else 'POST'
            method = context.get('http', {}).get('method') or event.get('httpMethod')
            if method != expected:
                result = response(405, {'erro': f'Método permitido: {expected}.'})
                result['headers']['Allow'] = expected
                return result
            if action == 'listar':
                return response(200, self.listar(event.get('queryStringParameters') or {}))
            if action not in ('solicitar', 'cadastrar', 'efetivar'):
                raise HTTPError(404, 'Operação inexistente.')
            return response(200, getattr(self, action)(body(event)))
        except HTTPError as exc:
            return response(exc.code, exc.payload)
        except (ClientError, BotoCoreError):
            LOG.error('aws_operation_failed action=%s', action)
            return response(503, {'erro': 'Serviço temporariamente indisponível. Consulte o estado antes de tentar novamente.'})

    def listar(self, query):
        resource = query.get('recurso', 'livros')
        tables = {'livros': self.books, 'interesses': self.interests, 'vendas': self.sales}
        if not isinstance(resource, str) or resource not in tables:
            raise HTTPError(400, 'recurso inválido.')
        items = [item for item in self.scan(tables[resource]) if item.get('_tipo') != 'GUARD']
        if resource == 'livros':
            items.sort(key=lambda x: (x.get('titulo', '').casefold(), x['livroId']))
        else:
            date_key = 'dataVenda' if resource == 'vendas' else 'dataCriacao'
            id_key = 'vendaId' if resource == 'vendas' else 'interesseId'
            items.sort(key=lambda x: (x.get(date_key, ''), x[id_key]), reverse=True)
        return {'recurso': resource, 'total': len(items), 'itens': [self.public(item) for item in items]}

    @staticmethod
    def public(item):
        return {k: v for k, v in item.items() if not k.startswith('_') and k != 'versao'}

    def solicitar(self, data):
        book_id = valid_id(data, 'livroId')
        address = email(data)
        name = text(data, 'nomeCliente', required=False, limit=150)
        lock_id = guard_id(book_id, address)
        interest_id = identifier('INT-')
        created = now()
        for attempt in range(MAX_ATTEMPTS):
            book = self.get(self.books, 'livroId', book_id)
            if book is None:
                raise HTTPError(404, 'Livro não encontrado.')
            if self.get(self.interests, 'interesseId', lock_id):
                raise HTTPError(409, 'Já existe interesse ativo para este livro e email.')
            available = book['quantidade'] > 0
            interest = {'interesseId': interest_id, 'livroId': book_id, 'emailCliente': address,
                        'titulo': book['titulo'], 'status': 'RESERVADO' if available else 'PENDENTE', 'dataCriacao': created,
                        'dataAtualizacao': created}
            if name is not None:
                interest['nomeCliente'] = name
            if available:
                interest.update(dataReserva=now(), valor=book['preco'])
            updated = {**book, 'quantidade': book['quantidade'] - int(available), 'versao': book.get('versao', 0) + 1, 'dataAtualizacao': now()}
            guard = {'interesseId': lock_id, '_tipo': 'GUARD', 'dono': interest_id}
            actions = [self.put(self.books, updated, 'livroId', previous=book),
                       self.put(self.interests, interest, 'interesseId'), self.put(self.interests, guard, 'interesseId')]
            if self.commit(actions):
                sent = self.notify(interest, book) if available else False
                return {'mensagem': 'Livro reservado.' if available else 'Interesse registrado na fila.',
                        'disponivel': available, 'status': interest['status'], 'interesseId': interest_id, 'emailEnviado': sent}
            self.pause(attempt)
        raise HTTPError(409, 'Conflito concorrente; consulte o estado e tente novamente.')

    def cadastrar(self, data):
        requested_id = valid_id(data, 'livroId', required=False)
        book_id = requested_id or ('LIV-' + uuid.uuid4().hex[:8].upper())
        title = text(data, 'titulo')
        author = text(data, 'autor')
        quantity = integer(data, 'quantidade', 1, MAX_QUANTITY)
        value = price(data)
        metadata = {}
        if 'ano' in data:
            metadata['ano'] = integer(data, 'ano', 1, 9999)
        if 'condicao' in data:
            metadata['condicao'] = text(data, 'condicao', limit=100)
        for attempt in range(MAX_ATTEMPTS):
            book = self.get(self.books, 'livroId', book_id)
            if requested_id is None and book is not None:
                book_id = 'LIV-' + uuid.uuid4().hex[:8].upper()
                continue
            total = (book['quantidade'] if book else 0) + quantity
            if total > MAX_QUANTITY:
                raise HTTPError(400, 'Estoque excede o limite permitido.')
            updated = {**(book or {}), 'livroId': book_id, 'titulo': title, 'autor': author, 'preco': value,
                       'quantidade': total, 'versao': (book or {}).get('versao', 0) + 1,
                       'dataCriacao': (book or {}).get('dataCriacao', now()), 'dataAtualizacao': now(), **metadata}
            # Read the book version BEFORE scanning. Every queue insertion and
            # stock mutation through this backend advances this version. A commit
            # with the same version validates the observed queue against writers.
            pending = [item for item in self.scan(self.interests)
                       if item.get('livroId') == book_id and item.get('status') == 'PENDENTE']
            pending.sort(key=lambda item: (item['dataCriacao'], item['interesseId']))
            selected = pending[:int(total)]
            if len(selected) > 99:
                raise HTTPError(409, 'Entrada atenderia mais de 99 pendentes; divida a quantidade em lotes menores.')
            updated['quantidade'] = total - len(selected)
            actions = [self.put(self.books, updated, 'livroId', previous=book)]
            reservations = []
            for interest in selected:
                reserved = {**interest, 'status': 'RESERVADO', 'dataReserva': now(), 'dataAtualizacao': now(), 'titulo': title, 'valor': value}
                reservations.append(reserved)
                actions.append({'Put': {'TableName': self.interests, 'Item': encode(reserved),
                                        'ConditionExpression': '#s = :pending',
                                        'ExpressionAttributeNames': {'#s': 'status'},
                                        'ExpressionAttributeValues': encode({':pending': 'PENDENTE'})}})
            if self.commit(actions):
                notified = [item['emailCliente'] for item in reservations if self.notify(item, updated, arrival=True)]
                return {'mensagem': 'Livro cadastrado; estoque atualizado.', 'livro': self.public(updated),
                        'clientesReservados': len(reservations), 'clientesNotificados': len(notified), 'emailsNotificados': notified}
            self.pause(attempt)
        raise HTTPError(409, 'Conflito concorrente; consulte o estoque antes de repetir a entrada.')

    def efetivar(self, data):
        interest_id = valid_id(data, 'interesseId')
        sale_id = identifier('VEN-')
        sold_at = now()
        for attempt in range(MAX_ATTEMPTS):
            interest = self.get(self.interests, 'interesseId', interest_id)
            if interest is None or interest.get('_tipo') == 'GUARD':
                raise HTTPError(404, 'Interesse não encontrado.')
            if interest['status'] != 'RESERVADO':
                raise HTTPError(409, 'Somente interesses reservados podem ser vendidos.', statusAtual=interest['status'])
            sale = {'vendaId': sale_id, 'interesseId': interest_id, 'livroId': interest['livroId'],
                    'titulo': interest['titulo'], 'emailCliente': interest['emailCliente'],
                    'valor': interest['valor'], 'dataVenda': sold_at}
            updated = {**interest, 'status': 'VENDIDO', 'vendaId': sale_id, 'dataVenda': sold_at, 'dataAtualizacao': sold_at}
            actions = [
                {'Put': {'TableName': self.interests, 'Item': encode(updated),
                         'ConditionExpression': '#s = :reserved', 'ExpressionAttributeNames': {'#s': 'status'},
                         'ExpressionAttributeValues': encode({':reserved': 'RESERVADO'})}},
                self.put(self.sales, sale, 'vendaId'),
                {'Delete': {'TableName': self.interests,
                            'Key': encode({'interesseId': guard_id(interest['livroId'], interest['emailCliente'])}),
                            'ConditionExpression': 'dono = :owner',
                            'ExpressionAttributeValues': encode({':owner': interest_id})}},
            ]
            if self.commit(actions):
                return {'mensagem': 'Venda efetivada.', 'venda': sale, 'status': 'VENDIDO'}
            self.pause(attempt)
        current = self.get(self.interests, 'interesseId', interest_id)
        raise HTTPError(409, 'Conflito concorrente; consulte o interesse antes de repetir.', statusAtual=(current or {}).get('status'))


def handle(action, event, context=None):
    return Backend().handle(action, event)
