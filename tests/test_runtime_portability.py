import io
import sqlite3
import uuid

import pytest
from marshmallow import ValidationError

from app import paths
from app.main import DB_USERS_PATH, config, flask_app
from app import runtime
from app.runtime import select_available_port
from app.services.cheminformatics import find_job_dir, get_or_create_job_dir
from app.services.models import verify_model_checkpoint
from app.tasks.task_schemas import TaskSubmitSchema


def test_dynamic_port_selection_skips_occupied_port(monkeypatch):
    monkeypatch.setattr(runtime, "is_port_available", lambda _host, port: port == 7862)
    assert select_available_port("127.0.0.1", preferred=7860, attempts=10) == 7862


def test_explicit_platform_port_is_preserved():
    assert select_available_port("127.0.0.1", requested="9123") == 9123


def test_job_paths_do_not_depend_on_current_working_directory(tmp_path, monkeypatch):
    configured_jobs = tmp_path / "configured-jobs"
    monkeypatch.setattr(paths, "JOBS_DIR", configured_jobs)
    monkeypatch.chdir(tmp_path)

    user_id = str(uuid.uuid4())
    job_id = str(uuid.uuid4())
    created = get_or_create_job_dir(user_id, job_id)

    assert created == str(configured_jobs / user_id / job_id)
    assert find_job_dir(user_id, job_id) == created


def test_model_readiness_verifies_digest():
    assert verify_model_checkpoint() is True


def test_nested_task_params_are_sanitized_and_bounded():
    schema = TaskSubmitSchema()
    data = schema.load({
        "task_type": "optimize_3d",
        "params": {"smiles": "CCO", "force_field": "MMFF94"},
    })
    schema.validate_params(data)
    assert data["params"] == {"smiles": "CCO", "force_field": "MMFF94"}

    oversized = {
        "task_type": "optimize_3d",
        "params": {"smiles": "C" * 2001},
    }
    oversized_data = schema.load(oversized)
    with pytest.raises(ValidationError):
        schema.validate_params(oversized_data)


def test_uploaded_filename_is_sanitized_in_response():
    flask_app.config["TESTING"] = True
    flask_app.config["SECRET_KEY"] = "runtime-portability-test-secret"
    username = f"portable_{uuid.uuid4().hex[:10]}"
    password = "portable-password-123"

    with flask_app.test_client() as client:
        assert client.post(
            "/api/auth/register", json={"username": username, "password": password}
        ).status_code == 200
        assert client.post(
            "/api/auth/login", json={"username": username, "password": password}
        ).status_code == 200
        content = b"HEADER    TEST PDB\nATOM      1  N   ALA A   1       0.000   0.000   0.000  1.00 10.00           N\n"
        response = client.post(
            "/api/pdb/upload",
            data={"file": (io.BytesIO(content), "<img src=x onerror=alert(1)>.pdb")},
            content_type="multipart/form-data",
        )
        assert response.status_code == 200
        returned_name = response.get_json()["filename"]
        assert "<" not in returned_name
        assert ">" not in returned_name

    import sqlite3

    with sqlite3.connect(DB_USERS_PATH) as connection:
        connection.execute("DELETE FROM users WHERE username = ?", (username,))
        connection.commit()


def test_disabled_optional_capabilities_are_reported_and_enforced(monkeypatch):
    monkeypatch.setattr(config, "GNINA_ENABLED", False)
    monkeypatch.setattr(config, "REGISTRATION_ENABLED", False)
    flask_app.config["TESTING"] = True

    with flask_app.test_client() as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.get_json()["capabilities"] == {
            "gnina": False,
            "registration": False,
        }
        registration = client.post(
            "/api/auth/register",
            json={"username": "disabled_user", "password": "password-long-enough"},
        )
        assert registration.status_code == 403


def test_embedding_is_origin_allowlisted_and_uses_partitioned_cookie(monkeypatch):
    allowed_origins = "https://huggingface.co https://prawin.app https://www.prawin.app"
    monkeypatch.setattr(config, "FRAME_ANCESTORS", allowed_origins)
    monkeypatch.setattr(config, "REGISTRATION_ENABLED", True)
    monkeypatch.setitem(flask_app.config, "SESSION_COOKIE_SECURE", True)
    monkeypatch.setitem(flask_app.config, "SESSION_COOKIE_SAMESITE", "None")
    monkeypatch.setitem(flask_app.config, "SESSION_COOKIE_PARTITIONED", True)

    username = f"embed_{uuid.uuid4().hex[:10]}"
    password = "embedded-password-123"

    try:
        with flask_app.test_client() as client:
            page = client.get("/")
            assert page.status_code == 200
            assert "X-Frame-Options" not in page.headers
            assert f"frame-ancestors {allowed_origins}" in page.headers[
                "Content-Security-Policy"
            ]

            assert client.post(
                "/api/auth/register",
                json={"username": username, "password": password},
            ).status_code == 200
            login = client.post(
                "/api/auth/login",
                json={"username": username, "password": password},
            )
            cookie = login.headers.get("Set-Cookie", "")
            assert login.status_code == 200
            assert "Secure" in cookie
            assert "SameSite=None" in cookie
            assert "Partitioned" in cookie
    finally:
        with sqlite3.connect(DB_USERS_PATH) as connection:
            connection.execute("DELETE FROM users WHERE username = ?", (username,))
            connection.commit()
