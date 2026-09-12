import json
import pathlib

import pytest
from fastapi.testclient import TestClient

from spur_api.main import create_app
from spur_api.store import InMemoryStore

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"


@pytest.fixture
def line4_project_dict():
    with open(FIXTURES / "line4_project.json") as f:
        return json.load(f)


@pytest.fixture
def client(monkeypatch):
    # Fresh store per test so runs/projects don't leak across tests -
    # the app module holds a process-wide singleton (Phase 1 only; Phase 2
    # replaces this with a real per-request DB session).
    import spur_api.store as store_module

    fresh_store = InMemoryStore()
    monkeypatch.setattr(store_module, "store", fresh_store)

    app = create_app()
    return TestClient(app)
