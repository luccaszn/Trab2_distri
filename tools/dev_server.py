"""Executa as Lambdas reais com AWS emulada em memória (sem e-mail real)."""
from __future__ import annotations

import argparse
import importlib.util
import json
import os
from decimal import Decimal
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'layers' / 'sebo-common' / 'python'))
ROUTES = {'/api/listar': 'listar_livros', '/api/solicitar': 'solicitar_livro',
          '/api/cadastrar': 'cadastrar_livro', '/api/efetivar': 'efetivar_venda'}


def load_handlers():
    handlers = {}
    for route, name in ROUTES.items():
        spec = importlib.util.spec_from_file_location(f'local_{name}', ROOT / 'lambdas' / ('sebo-' + name.replace('_', '-')) / 'app.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        handlers[route] = module.lambda_handler
    return handlers


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8080)
    args = parser.parse_args()
    os.environ.update(AWS_DEFAULT_REGION='us-east-1', AWS_ACCESS_KEY_ID='testing',
                      AWS_SECRET_ACCESS_KEY='testing', AWS_SESSION_TOKEN='testing',
                      AWS_EC2_METADATA_DISABLED='true', TABELA_LIVROS='sebo-Livros',
                      TABELA_INTERESSES='sebo-Interesses', TABELA_VENDAS='sebo-Vendas')
    import boto3
    from moto import mock_aws
    with mock_aws():
        db = boto3.client('dynamodb', region_name='us-east-1')
        for path in sorted((ROOT / 'infra').glob('tabela_*.json')):
            db.create_table(**json.loads(path.read_text(encoding='utf-8')))
        sns = boto3.client('sns', region_name='us-east-1')
        os.environ['SNS_TOPIC_ARN'] = sns.create_topic(Name='sebo-notificacoes')['TopicArn']
        table = boto3.resource('dynamodb', region_name='us-east-1').Table('sebo-Livros')
        seeds = json.loads((ROOT / 'infra' / 'livros_seed.json').read_text(encoding='utf-8'), parse_float=Decimal)
        for item in seeds:
            table.put_item(Item=item)
        handlers = load_handlers()
        origin = f'http://127.0.0.1:{args.port}'

        class Handler(SimpleHTTPRequestHandler):
            def __init__(self, *a, **kw):
                super().__init__(*a, directory=str(ROOT / 'frontend'), **kw)

            def send_bytes(self, code, body, content_type='application/json; charset=utf-8'):
                self.send_response(code)
                self.send_header('Content-Type', content_type)
                self.send_header('Content-Length', str(len(body)))
                self.send_header('Cache-Control', 'no-store')
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.end_headers()
                self.wfile.write(body)

            def do_GET(self):
                path = urlparse(self.path).path
                if path == '/config.js':
                    config = {'URL_LISTAR': '/api/listar', 'URL_SOLICITAR': '/api/solicitar',
                              'URL_CADASTRAR': '/api/cadastrar', 'URL_EFETIVAR': '/api/efetivar',
                              'AMBIENTE': 'local'}
                    self.send_bytes(200, ('window.SEBO_CONFIG = ' + json.dumps(config) + ';').encode(),
                                    'application/javascript; charset=utf-8')
                elif path == '/api/listar':
                    self.invoke()
                elif path in ROUTES:
                    self.send_bytes(405, b'{"erro":"Use POST"}')
                else:
                    super().do_GET()

            def do_POST(self):
                if urlparse(self.path).path not in ROUTES or urlparse(self.path).path == '/api/listar':
                    self.send_bytes(404, b'{"erro":"Rota inexistente"}')
                    return
                if self.headers.get('Origin') not in (None, origin, f'http://localhost:{args.port}'):
                    self.send_bytes(403, b'{"erro":"Origem nao permitida"}')
                    return
                self.invoke()

            def invoke(self):
                parsed = urlparse(self.path)
                try:
                    length = int(self.headers.get('Content-Length', '0'))
                    if length < 0 or length > 16384:
                        self.send_bytes(413, b'{"erro":"Corpo muito grande"}')
                        return
                    body = self.rfile.read(length).decode('utf-8') if length else None
                    event = {'body': body, 'isBase64Encoded': False,
                             'queryStringParameters': {k: v[-1] for k, v in parse_qs(parsed.query).items()},
                             'requestContext': {'http': {'method': self.command}},
                             'headers': {'content-type': self.headers.get('Content-Type', '')}}
                    response = handlers[parsed.path](event, None)
                    self.send_bytes(response['statusCode'], response['body'].encode('utf-8'))
                except (ValueError, UnicodeError):
                    self.send_bytes(400, b'{"erro":"Requisicao invalida"}')
                except Exception as exc:
                    print(f'Falha local: {type(exc).__name__}: {exc}', flush=True)
                    self.send_bytes(500, b'{"erro":"Falha local; consulte o terminal"}')

            def log_message(self, fmt, *args):
                print(fmt % args, flush=True)

        server = HTTPServer(('127.0.0.1', args.port), Handler)
        print(f'LOCAL EMULADO: {origin} — dados em memória; nenhum e-mail real enviado.', flush=True)
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()


if __name__ == '__main__':
    main()
