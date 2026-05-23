"""pytest 配置：使用临时数据库"""

import os
import sys
import tempfile

import pytest

# 保证 backend 在 import 路径中
BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..", "backend")
sys.path.insert(0, BACKEND_DIR)


@pytest.fixture()
def test_db(monkeypatch):
    """为每个测试使用独立 SQLite 文件"""
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr("main.DB_PATH", path)
    import main

    main.init_db()
    yield path
    try:
        os.remove(path)
    except OSError:
        pass


@pytest.fixture()
def client(test_db):
    from fastapi.testclient import TestClient
    import main

    return TestClient(main.app)
