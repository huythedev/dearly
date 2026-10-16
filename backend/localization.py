"""English source messages with optional Vietnamese response translations."""
import json
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import JSONResponse


VIETNAMESE = json.loads(Path(__file__).with_name('translations.vi.json').read_text(encoding='utf-8'))


def response_language(header: str) -> str:
    choices = []
    for index, entry in enumerate(header.split(',')):
        parts = entry.strip().lower().split(';')
        language = parts[0].split('-')[0]
        quality = 1.0
        for parameter in parts[1:]:
            if parameter.strip().startswith('q='):
                try:
                    quality = float(parameter.strip()[2:])
                except ValueError:
                    quality = 0.0
        if language in ('en', 'vi') and 0 < quality <= 1:
            choices.append((quality, -index, language))
    return max(choices)[2] if choices else 'en'


class RequestError(HTTPException):
    def __init__(self, message: str, status: int = 400, **parameters):
        self.message = message
        self.parameters = parameters
        super().__init__(status, message.format(**parameters))


def error_response(message: str, status: int, *, language: str = '', headers=None, **parameters):
    code = response_language(language)
    template = VIETNAMESE.get(message, message) if code == 'vi' else message
    return JSONResponse({'detail': template.format(**parameters)}, status_code=status,
                        headers={**(headers or {}), 'Content-Language': code,
                                 'Cache-Control': 'no-store', 'Vary': 'Accept-Language'})
