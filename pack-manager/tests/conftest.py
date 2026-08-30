import pytest

from pack_manager.assets import AssetStore
from pack_manager.db import Database


@pytest.fixture
def asset_store(tmp_path):
    database = Database(tmp_path / "manager.sqlite3")
    database.initialize()
    return AssetStore(tmp_path / "data", database, max_bytes=1024)
