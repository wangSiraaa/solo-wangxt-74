import os

os.environ["DATABASE_URL"] = "sqlite+pysqlite:///:memory:"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.database import get_session
from app.main import app
from app.models import Base


@pytest.fixture()
def env():
    """每个用例一套全新内存库 + 已注入依赖的 TestClient。"""
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    TestingSession = sessionmaker(bind=engine, autoflush=True, expire_on_commit=False)
    Base.metadata.create_all(engine)
    session = TestingSession()

    def override():
        yield session

    app.dependency_overrides[get_session] = override
    with TestClient(app) as client:
        yield client, session
    app.dependency_overrides.clear()


def make_founder(client, name, generation=0):
    r = client.post("/api/germplasm", json={"name": name, "generation": generation})
    assert r.status_code == 201, r.text
    return r.json()


def make_mating(client, **kw):
    r = client.post("/api/matings", json=kw)
    assert r.status_code == 201, r.text
    return r.json()


def make_trial_with_plots(client, family_code):
    r = client.post("/api/trials", json={"name": "测试圃", "season": "2026-春"})
    assert r.status_code == 201, r.text
    tid = r.json()["id"]
    plots = []
    for label, rep in (("A-1", 1), ("A-2", 2)):
        r = client.post(
            f"/api/trials/{tid}/plots",
            json={"label": label, "replicate": rep, "family_code": family_code},
        )
        assert r.status_code == 201, r.text
        plots.append(r.json())
    return tid, plots
