from pathlib import Path

import pytest
from fastapi.testclient import TestClient

import main
from main import app
from src.database import initialize_database


@pytest.fixture
def client(tmp_path, monkeypatch):
    # Point the app's storage at a throwaway database so tests never touch data/movies.db
    db_path = tmp_path / "movies.db"
    initialize_database(db_path)
    monkeypatch.setattr(main.storage, "db_path", db_path)
    with TestClient(app) as test_client:
        yield test_client


@pytest.fixture
def sample_csv_bytes():
    filepath = Path("fixtures") / "sample_movies.csv"
    return filepath.read_bytes()


@pytest.fixture
def uploaded_movies(client, sample_csv_bytes):
    response = client.post(
        "/upload",
        files={
            "file": (
                "sample_movies.csv",
                sample_csv_bytes,
                "text/csv"
            )
        }
    )
    assert response.status_code == 200
    return response.json()


@pytest.fixture
def processing_body():
    return {
        "validation": {
            "required_columns": ["title", "rating"],
            "numeric_columns": ["release_year", "rating"]
        },
        "processing": {
            "remove_duplicates": True,
            "missing": {
                "enabled": True,
                "axis": "rows"
            },
            "outliers": {
                "enabled": False,
                "columns": [],
                "method": "iqr",
                "threshold": 1.5
            }
        }
    }
