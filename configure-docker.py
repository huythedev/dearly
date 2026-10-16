"""Interactive, dependency-free Docker configuration for Windows/macOS/Linux."""
import argparse
import re
from pathlib import Path
from urllib.parse import urlsplit


def port(value):
    if not re.fullmatch(r'[0-9]{1,5}', value) or not 1 <= int(value) <= 65535:
        raise ValueError('Use a port between 1 and 65535.')
    return str(int(value))


def backend_address(value):
    parsed = urlsplit(value if '://' in value else 'http://' + value)
    try:
        valid = (parsed.scheme in ('http', 'https') and parsed.hostname and parsed.port
                 and not parsed.username and not parsed.password and parsed.path in ('', '/')
                 and not parsed.query and not parsed.fragment
                 and re.fullmatch(r'[A-Za-z0-9_.:\[\]/-]+', value))
    except ValueError:
        valid = False
    if not valid:
        raise ValueError('Use IP:port or http[s]://host:port, without paths, credentials, or queries.')
    return value.rstrip('/')


def read_values(text):
    return {key.strip(): value.strip().strip('\"\'') for line in text.splitlines()
            if not line.lstrip().startswith('#') and '=' in line
            for key, value in [line.split('=', 1)]}


def update_values(text, values):
    seen = set()
    lines = []
    for line in text.splitlines():
        key = line.split('=', 1)[0].strip() if '=' in line and not line.lstrip().startswith('#') else ''
        if key in values:
            lines.append(f'{key}={values[key]}'); seen.add(key)
        else:
            lines.append(line)
    lines.extend(f'{key}={value}' for key, value in values.items() if key not in seen)
    return '\n'.join(lines) + '\n'


def ask(label, default, validate):
    while True:
        value = input(f'{label} [{default}]: ').strip() or default
        try:
            return validate(value)
        except ValueError as error:
            print(error)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--env-file', type=Path, default=Path(__file__).resolve().with_name('.env'))
    args = parser.parse_args()
    text = args.env_file.read_text(encoding='utf-8') if args.env_file.exists() else ''
    previous = read_values(text)
    print('Frontend and backend are separate containers. Enter the backend address reachable from the frontend container.')
    print('Compose: backend:8000. Another host: 192.168.1.20:9000. Docker host: host.docker.internal:9000.')
    try:
        values = {
            'DEARLY_FRONTEND_PORT': ask('Frontend published port', previous.get('DEARLY_FRONTEND_PORT', '8080'), port),
            'DEARLY_BACKEND_PORT': ask('Backend published port', previous.get('DEARLY_BACKEND_PORT', previous.get('DEARLY_PORT', '8000')), port),
            'DEARLY_BACKEND_ADDRESS': ask('Backend IP/hostname:port', previous.get('DEARLY_BACKEND_ADDRESS', 'backend:' + previous.get('DEARLY_BACKEND_LISTEN_PORT', '8000')), backend_address),
        }
    except (EOFError, KeyboardInterrupt):
        print('\nConfiguration cancelled; no file was changed.')
        return 2
    args.env_file.write_text(update_values(text, values), encoding='utf-8')
    print(f'Configuration saved to {args.env_file}.')
    print('Start both: docker compose up -d --build')
    print('Or start independently: docker compose up -d --build frontend  /  docker compose up -d --build backend')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
