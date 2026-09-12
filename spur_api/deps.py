from spur_api import store as store_module
from spur_api.store import InMemoryStore


def get_store() -> InMemoryStore:
    # Looked up as a module attribute (not imported by value) so tests can
    # swap `spur_api.store.store` for a fresh instance per test.
    return store_module.store
