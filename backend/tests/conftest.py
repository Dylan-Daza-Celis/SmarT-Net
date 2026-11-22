import os
import sys
from pathlib import Path
from uuid import uuid4
import pytest
from sqlalchemy import create_engine, event
from sqlalchemy.orm import sessionmaker
from alembic import command
from alembic.config import Config
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ["JWT_SECRET"] = "test-only-secret-" + "x" * 40
os.environ["DATABASE_URL"] = "sqlite://"
from app import database, security, main
from app.models import User

@pytest.fixture
def api(tmp_path, monkeypatch, request):
    # TEST_DATABASE_URL debe apuntar únicamente a una BD PostgreSQL desechable.
    url = os.environ.get("TEST_DATABASE_URL", "sqlite:///" + str(tmp_path / "test.db"))
    engine = create_engine(url, connect_args={"check_same_thread": False} if url.startswith("sqlite") else {})
    schema = "test_" + uuid4().hex
    if engine.dialect.name == "postgresql":
        with engine.begin() as db:
            db.exec_driver_sql(f'CREATE SCHEMA "{schema}"')
        @event.listens_for(engine, "connect")
        def search_path(connection, record):
            with connection.cursor() as cursor:
                cursor.execute(f'SET search_path TO "{schema}"')
            connection.commit()
        engine.dispose()
    else:
        @event.listens_for(engine, "connect")
        def foreign_keys(connection, record):
            connection.execute("PRAGMA foreign_keys=ON")
    session = sessionmaker(bind=engine)
    monkeypatch.setattr(database, "engine", engine)
    for module in (database, security, main):
        monkeypatch.setattr(module, "Session", session)
    config = Config(str(Path(__file__).resolve().parents[1] / "alembic.ini"))
    command.upgrade(config, getattr(request, "param", "head"))
    main.app.state.abuse.reset()
    with session.begin() as db:
        for role in ("administrador", "analista", "observador"):
            db.add(User(username=role, role=role, password_hash=security.password_hasher.hash("test-password-123")))
    try:
        with TestClient(main.app,base_url='http://localhost') as client:
            yield client, session, config
    finally:
        if engine.dialect.name == "postgresql":
            with engine.begin() as db:
                db.exec_driver_sql(f'DROP SCHEMA "{schema}" CASCADE')
        engine.dispose()

@pytest.fixture
def headers(api):
    client, _, _ = api
    def for_role(role):
        response = client.post("/api/auth/login", json={"username": role, "password": "test-password-123"})
        assert response.status_code == 200
        return {"Authorization": "Bearer " + response.json()["access_token"]}
    return for_role

@pytest.fixture
def batch():
    import json
    return json.loads((Path(__file__).resolve().parents[2] / "examples/eventos_demo.json").read_text(encoding="utf-8"))
