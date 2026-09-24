from functools import lru_cache

from fastapi import APIRouter

from spur.catalog import Catalog, catalog

router = APIRouter(prefix="/v1/catalog", tags=["catalog"])


@lru_cache(maxsize=1)
def _catalog() -> Catalog:
    # Only changes with the installed spur version, so build it once per process.
    return catalog()


@router.get("")
def get_catalog() -> Catalog:
    """Every component, jitter and collection type a project may use, with the
    parameters each takes (name, type, whether it is required, its default and a
    description). What an editor needs to offer the right choices."""
    return _catalog()
