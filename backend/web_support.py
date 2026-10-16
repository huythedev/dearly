"""Same-origin browser sessions and optional Vite build hosting."""
from pathlib import Path
from urllib.parse import urlsplit

from fastapi import Request
from fastapi.responses import FileResponse, JSONResponse
from starlette.datastructures import Headers
from starlette.requests import HTTPConnection
from starlette.staticfiles import StaticFiles
from localization import error_response

COOKIE = 'dearly_session'


def same_origin(connection: HTTPConnection) -> bool:
    origin = connection.headers.get('origin')
    if not origin:
        return connection.headers.get('sec-fetch-site') != 'cross-site'
    try:
        parsed = urlsplit(origin)
    except ValueError:
        return False
    return (parsed.scheme in ('http', 'https') and not parsed.username and not parsed.password
            and parsed.netloc.lower() == connection.headers.get('host', '').lower()
            and parsed.path in ('', '/') and not parsed.query and not parsed.fragment)


class BrowserSession:
    """Keep existing bearer APIs; cookies require a same-origin custom-header write."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope['type'] != 'http' or not scope['path'].startswith('/v1/'):
            return await self.app(scope, receive, send)
        request = Request(scope)
        headers = Headers(scope=scope)
        browser = headers.get('x-dearly-client') == 'web'
        cookie = request.cookies.get(COOKIE)
        unsafe = scope['method'] not in ('GET', 'HEAD', 'OPTIONS')
        use_cookie = bool(cookie and not headers.get('authorization'))
        if unsafe and (browser or use_cookie) and (not browser or not same_origin(request)):
            response = error_response('A same-origin browser request is required.', 403,
                                      language=headers.get('accept-language', ''))
            return await response(scope, receive, send)
        if use_cookie and len(cookie) <= 128:
            scope = {**scope, 'headers': [*scope['headers'], (b'authorization', ('Bearer ' + cookie).encode('ascii', errors='ignore'))]}
        await self.app(scope, receive, send)


def browser_session(data: dict, request: Request, status_code: int = 200):
    if request.headers.get('x-dearly-client') != 'web':
        return JSONResponse(data, status_code, headers={'Cache-Control': 'no-store'})
    response = JSONResponse({k: v for k, v in data.items() if k != 'token'}, status_code,
                            headers={'Cache-Control': 'no-store'})
    # TLS may terminate at Cloudflare; a checked, same-host Origin also identifies HTTPS.
    secure = request.url.scheme == 'https' or request.headers.get('origin', '').startswith('https://')
    response.set_cookie(COOKIE, data['token'], httponly=True, secure=secure, samesite='strict', path='/')
    return response


def mount_web(app, directory: Path):
    """Never let SPA fallbacks swallow API typos or expose repository/runtime files."""
    directory = directory.resolve()
    if (directory / 'assets').is_dir():
        app.mount('/assets', StaticFiles(directory=directory / 'assets'), name='web-assets')

    @app.get('/{web_path:path}', include_in_schema=False)
    def web(web_path: str):
        reserved = {'v1', 'ws', 'health', 'docs', 'openapi.json', 'assets'}
        if web_path.split('/')[0] in reserved or any(p.startswith('.') for p in web_path.split('/') if p):
            return JSONResponse({'detail': 'Not found.'}, 404)
        target = (directory / web_path).resolve()
        if not target.is_relative_to(directory):
            return JSONResponse({'detail': 'Not found.'}, 404)
        if not target.is_file():
            if Path(web_path).suffix:
                return JSONResponse({'detail': 'Not found.'}, 404)
            target = directory / 'index.html'
        return FileResponse(target, headers={
            'Cache-Control': 'no-cache', 'X-Content-Type-Options': 'nosniff',
            'Referrer-Policy': 'no-referrer',
            'Content-Security-Policy': "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; "
                                       "img-src 'self' data:; connect-src 'self'; base-uri 'none'; "
                                       "frame-ancestors 'none'; form-action 'self'",
        })
