"""Empacota os arquivos versionados/staged; exclui credenciais e artefatos locais."""
import hashlib
from pathlib import Path
import re
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DENIED_PARTS = {'.git', '.venv', '__pycache__', '.pytest_cache', 'node_modules', 'build'}
DENIED_FILES = {'config.env', '.env', 'frontend/config.js'}
TEXT_EXTENSIONS = {'.py', '.sh', '.js', '.html', '.json', '.md', '.txt', '.ini', '.css'}


def main():
    files = subprocess.check_output(['git', 'ls-files', '-z'], cwd=ROOT).decode('utf-8').split('\0')
    selected = []
    for name in sorted(filter(None, files)):
        relative = Path(name)
        if relative.is_absolute() or '..' in relative.parts or set(relative.parts) & DENIED_PARTS or name in DENIED_FILES:
            raise RuntimeError('Arquivo local/sensível está no índice Git: ' + name)
        source = ROOT / relative
        if source.is_symlink() or not source.resolve().is_relative_to(ROOT):
            raise RuntimeError('Symlink recusado: ' + name)
        if source.suffix in TEXT_EXTENSIONS:
            content = source.read_text(encoding='utf-8')
            if re.search(r'\b(?:AKIA|ASIA)[A-Z0-9]{16}\b', content):
                raise RuntimeError('Possível credencial em: ' + name)
        selected.append((name, source))
    required = {'README.md', 'docs/relatorio-completo.pdf', 'docs/relatorio.md', 'docs/resultados_testes.txt',
                'frontend/index.html', 'infra/tabela_interesses.json', 'tools/dev_server.py'}
    assert required <= {name for name, _ in selected}
    (ROOT / 'build').mkdir(exist_ok=True)
    target = ROOT / 'build' / 'SeboNaNuvem_EnzoAbate_LuccaSznaider.zip'
    with zipfile.ZipFile(target, 'w', zipfile.ZIP_DEFLATED) as archive:
        for name, source in selected:
            archive.write(source, 'SeboNaNuvem/' + name)
    with zipfile.ZipFile(target) as archive:
        assert archive.testzip() is None
        assert len(archive.namelist()) == len(selected)
        for name, source in selected:
            assert archive.read('SeboNaNuvem/' + name) == source.read_bytes(), name
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    print(f'ZIP verificado: {target}\nArquivos: {len(selected)}\nBytes: {target.stat().st_size}\nSHA-256: {digest}')


if __name__ == '__main__':
    main()
