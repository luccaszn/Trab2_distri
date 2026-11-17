from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
REQUIRED = ('README.md', 'docs/instalacao.md', 'docs/operacao.md', 'docs/relatorio.md',
            'docs/diagramas.md', 'docs/prints_necessarios.md', 'docs/problemas.md')


def test_documentos_obrigatorios():
    for name in REQUIRED:
        assert (ROOT / name).is_file(), name


def test_relatorio_identidade_e_limites_honestos():
    report = (ROOT / 'docs/relatorio.md').read_text(encoding='utf-8')
    for text in ('Enzo Abate', '2312936', 'Lucca Sznaider', '2220504', 'O que funcionou',
                 'O que não funcionou', 'Divisão de trabalho', 'Diagrama em blocos',
                 'Diagrama de sequência', 'Layer', 'AWS', 'não validado'):
        assert text in report, text


def test_diagramas():
    text = (ROOT / 'docs/diagramas.md').read_text(encoding='utf-8')
    assert text.count('```mermaid') >= 2
    assert 'flowchart' in text and 'sequenceDiagram' in text


def test_sem_valores_de_credenciais_nos_arquivos_entregaveis():
    patterns = [re.compile(r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b'),
                re.compile(r'(?i)aws_secret_access_key\s*=\s*[\"\']?[A-Za-z0-9/+=]{30,}')]
    for path in ROOT.rglob('*'):
        if not path.is_file() or any(part in {'.git', '.venv', 'build', '__pycache__', '.pytest_cache'} for part in path.parts):
            continue
        if path.suffix not in {'.md', '.py', '.json', '.js', '.html', '.env', '.sh', '.txt'}:
            continue
        text = path.read_text(encoding='utf-8', errors='ignore')
        for pattern in patterns:
            assert not pattern.search(text), str(path)
