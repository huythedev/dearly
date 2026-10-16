from pathlib import Path
import sys

# Permit both `pytest` from the repository root and `python -m pytest` in backend.
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))

from datetime import datetime, timezone
import pytest
from fastapi.testclient import TestClient
from server import create_app


@pytest.fixture
def env(tmp_path):
    clock=[datetime(2026,10,13,12,tzinfo=timezone.utc).timestamp()]
    app=create_app(tmp_path/'test.sqlite3',clock=lambda:clock[0])
    with TestClient(app) as client:
        yield client,app,clock
