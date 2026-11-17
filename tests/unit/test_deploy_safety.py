import importlib.util
import io
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / 'scripts'))


def module():
    import sebo_deploy
    return sebo_deploy


def test_package_is_deterministic_and_excludes_vendor_cache(tmp_path):
    m = module()
    (tmp_path / 'app.py').write_text('x = 1\n')
    for directory in ['__pycache__', 'boto3', 'botocore', '.git']:
        (tmp_path / directory).mkdir()
        (tmp_path / directory / 'bad.py').write_text('bad')
    first = m.package_python(tmp_path)
    assert first == m.package_python(tmp_path)
    assert zipfile.ZipFile(io.BytesIO(first)).namelist() == ['app.py']


@pytest.mark.parametrize('name', ['other-table', 'sebo-', 'sebo-../evil', 'arn:aws:iam::1:role/LabRole'])
def test_scope_rejects_unowned_names(name):
    with pytest.raises(ValueError):
        module().scoped(name)


def test_reset_requires_confirmation_before_any_client_call():
    class NoCalls:
        def __getattr__(self, name):
            raise AssertionError('AWS call before confirmation')
    with pytest.raises(ValueError, match='confirm'):
        module().reset_data(NoCalls(), confirm=False)


def test_secret_config_rejected(tmp_path):
    config = tmp_path / 'config.env'
    config.write_text('AWS_SECRET_ACCESS_KEY=do-not-store\n')
    with pytest.raises(ValueError, match='permitida'):
        module().load_config(config)
