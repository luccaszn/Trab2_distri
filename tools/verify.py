"""Verificação reproduzível LOCAL. Nunca habilita testes contra a AWS real."""
import ast
import os
from pathlib import Path
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def main():
    (ROOT / 'build').mkdir(exist_ok=True)
    env = os.environ.copy()
    env.pop('RUN_E2E', None)
    env.pop('RUN_E2E_WRITES', None)
    env['PYTHONIOENCODING'] = 'utf-8'
    commands = [
        [sys.executable, '-m', 'pytest', 'tests', '-q', '--basetemp=' + str(ROOT / 'build' / 'pytest'), '--junitxml=build/pytest.xml'],
        ['node', '--test', 'frontend/util.test.js'],
        ['node', '--check', 'frontend/app.js'],
        ['node', '--check', 'frontend/util.js'],
        ['bash', 'scripts/run.sh', 'package'],
    ]
    for file in ['deploy.sh', 'seed.sh', 'reset_dados.sh', 'scripts/check_env.sh', 'scripts/run.sh']:
        commands.append(['bash', '-n', file])
    chunks = ['VERIFICAÇÃO LOCAL — AWS EMULADA; NÃO É RESULTADO DE DEPLOY OU ENTREGA SNS\n']
    failed = False
    for command in commands:
        result = subprocess.run(command, cwd=ROOT, env=env, capture_output=True, text=True, encoding='utf-8', errors='replace')
        block = '$ ' + ' '.join(command) + '\n' + result.stdout + result.stderr + f'\nExit: {result.returncode}\n'
        chunks.append(block)
        print(block, flush=True)
        failed |= result.returncode != 0
    for directory in ('lambdas', 'layers', 'scripts', 'tools'):
        for source in (ROOT / directory).rglob('*.py'):
            ast.parse(source.read_text(encoding='utf-8'), filename=str(source), feature_version=(3, 12))
    chunks.append('Parsing das fontes Python com gramática 3.12: OK. Execução local em Python ' + sys.version.split()[0] + '.\n')
    if (ROOT / 'build' / 'pytest.xml').exists():
        suites = ET.parse(ROOT / 'build' / 'pytest.xml').getroot().findall('testsuite')
        counts = {key: sum(int(suite.get(key, '0')) for suite in suites) for key in ('tests', 'failures', 'errors', 'skipped')}
        counts['passed'] = counts['tests'] - counts['failures'] - counts['errors'] - counts['skipped']
        chunks.append('Resumo pytest real: ' + str(counts) + '\n')
        print(chunks[-1])
    (ROOT / 'docs' / 'resultados_testes.txt').write_text('\n'.join(chunks), encoding='utf-8')
    return int(failed)


if __name__ == '__main__':
    raise SystemExit(main())
