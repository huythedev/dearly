import importlib.util
import os
from pathlib import Path
import shutil
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('docker_config', ROOT / 'configure-docker.py')
config = importlib.util.module_from_spec(spec)
spec.loader.exec_module(config)


def test_setup_preserves_existing_settings_and_handles_separate_ports(tmp_path):
    destination = tmp_path / '.env'
    destination.write_text('# Existing operator settings\nOTHER_KEY=keep-me\nDEARLY_PORT=8000\n')
    result = subprocess.run([sys.executable, str(ROOT / 'configure-docker.py'), '--env-file', str(destination)],
                            input='9080\n9100\n192.168.1.20:9100\n', text=True, capture_output=True)
    assert result.returncode == 0, result.stderr
    values = config.read_values(destination.read_text())
    assert values['OTHER_KEY'] == 'keep-me' and values['DEARLY_PORT'] == '8000'
    assert values['DEARLY_FRONTEND_PORT'] == '9080' and values['DEARLY_BACKEND_PORT'] == '9100'
    assert values['DEARLY_BACKEND_ADDRESS'] == '192.168.1.20:9100'
    assert '# Existing operator settings' in destination.read_text()


def test_setup_cancel_is_atomic(tmp_path):
    destination = tmp_path / '.env'
    destination.write_text('OTHER_KEY=keep-me\n')
    result = subprocess.run([sys.executable, str(ROOT / 'configure-docker.py'), '--env-file', str(destination)],
                            input='9080\n', text=True, capture_output=True)
    assert result.returncode == 2 and destination.read_text() == 'OTHER_KEY=keep-me\n'


@pytest.fixture
def startup(tmp_path):
    if shutil.which('sh') is None:
        pytest.skip('Frontend container entrypoint requires a POSIX shell.')
    binary = tmp_path / 'bin'; binary.mkdir()
    nginx = binary / 'nginx'; nginx.write_text('#!/bin/sh\nexit 0\n'); nginx.chmod(0o755)
    subst = binary / 'envsubst'
    subst.write_text(f'#!{sys.executable}\nimport os,re,sys\nprint(re.sub(r"\\$\\{{([A-Z_]+)\\}}", lambda m: os.environ.get(m[1],m[0]), sys.stdin.read()),end="")\n')
    subst.chmod(0o755)
    destination = tmp_path / 'nginx.conf'

    def run(address, *, listen='8080', input=None):
        env = {**os.environ, 'PATH': str(binary) + os.pathsep + os.environ['PATH'],
               'DEARLY_BACKEND_ADDRESS': address, 'DEARLY_FRONTEND_LISTEN_PORT': listen,
               'DEARLY_NGINX_TEMPLATE': str(ROOT / 'web/docker/nginx.conf.template'),
               'DEARLY_NGINX_CONFIG': str(destination)}
        result = subprocess.run(['sh', str(ROOT / 'web/docker/entrypoint.sh')], env=env,
                                input=input, text=True, capture_output=True)
        return result, destination.read_text() if destination.exists() else ''
    return run


def test_frontend_startup_prompts_for_backend_and_preserves_nginx_variables(startup):
    result, rendered = startup('', listen='9081', input='192.168.1.20:9100\n')
    assert result.returncode == 0, result.stderr
    assert 'Backend address' in result.stderr
    assert 'listen 9081;' in rendered and 'http://192.168.1.20:9100' in rendered
    assert 'Host $http_host' in rendered and 'Upgrade $http_upgrade' in rendered
    assert '${DEARLY_' not in rendered


def test_frontend_supports_dns_https_and_ipv6_without_rebuilding(startup):
    for address in ('backend:9001', 'https://api.example.com:443/', '[::1]:8000'):
        result, rendered = startup(address)
        assert result.returncode == 0, result.stderr
        assert address.rstrip('/') in rendered


@pytest.mark.parametrize('address', ['', 'backend', 'backend:0', 'backend:65536', 'http://backend:80/path',
                                     'https://user:secret@backend:443', 'backend:80;return 200',
                                     'backend:80\nmalicious:90', 'ftp://backend:80', 'backend:80?token=secret'])
def test_frontend_rejects_invalid_or_injectable_upstreams(startup, address):
    result, _ = startup(address, input='')
    assert result.returncode != 0


def test_frontend_rejects_invalid_listen_port(startup):
    assert startup('backend:8000', listen='0')[0].returncode != 0
    assert startup('backend:8000', listen='8080;')[0].returncode != 0
