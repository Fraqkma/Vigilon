from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from fastapi.testclient import TestClient

from app import db


def recovery_database(monkeypatch, tmp_path, role=db.Role.ADMIN, active=True):
    engine = create_engine(f"sqlite:///{tmp_path / 'recovery.sqlite'}")
    db.Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(db, "Session", sessions)
    with sessions.begin() as session:
        session.add(db.User(
            username="configured-admin",
            password_hash=PasswordHasher().hash("old-password-that-is-long"),
            role=role,
            active=active,
        ))
    return engine, sessions


def test_reset_changes_only_the_configured_active_admin(monkeypatch, tmp_path):
    engine, sessions = recovery_database(monkeypatch, tmp_path)
    hasher = PasswordHasher()

    db.reset_admin_password(
        "configured-admin", "new-password-that-is-long", "configured-admin", hasher.hash
    )

    with sessions() as session:
        user = session.scalar(select(db.User).where(db.User.username == "configured-admin"))
        assert hasher.verify(user.password_hash, "new-password-that-is-long")
        with pytest.raises(VerifyMismatchError):
            hasher.verify(user.password_hash, "old-password-that-is-long")
    engine.dispose()


def test_reset_rejects_username_mismatch_and_short_password(monkeypatch, tmp_path):
    engine, _ = recovery_database(monkeypatch, tmp_path)
    hasher = PasswordHasher()

    for username, password, message in (
        ("other-admin", "new-password-that-is-long", "exactly match"),
        ("configured-admin", "too-short", "at least 12 characters"),
    ):
        try:
            db.reset_admin_password(username, password, "configured-admin", hasher.hash)
        except ValueError as exc:
            assert message in str(exc)
        else:
            raise AssertionError("Unsafe password reset was accepted")

    with engine.connect() as connection:
        assert connection.exec_driver_sql(
            "select count(*) from users where username='configured-admin'"
        ).scalar_one() == 1
    engine.dispose()


def test_reset_rejects_missing_inactive_or_non_admin_account(monkeypatch, tmp_path):
    engine, sessions = recovery_database(monkeypatch, tmp_path, role=db.Role.OPERATOR)

    try:
        db.reset_admin_password(
            "configured-admin", "new-password-that-is-long", "configured-admin", PasswordHasher().hash
        )
    except ValueError as exc:
        assert "active administrator" in str(exc)
    else:
        raise AssertionError("Non-admin password reset was accepted")

    with sessions.begin() as session:
        session.delete(session.scalar(select(db.User)))
    try:
        db.reset_admin_password(
            "configured-admin", "new-password-that-is-long", "configured-admin", PasswordHasher().hash
        )
    except ValueError as exc:
        assert "does not exist" in str(exc)
    else:
        raise AssertionError("Missing account reset was accepted")
    engine.dispose()


def test_reset_rejects_inactive_admin(monkeypatch, tmp_path):
    engine, _ = recovery_database(monkeypatch, tmp_path, active=False)
    with pytest.raises(ValueError, match="active administrator"):
        db.reset_admin_password(
            "configured-admin", "new-password-that-is-long", "configured-admin", PasswordHasher().hash
        )
    engine.dispose()


def test_reset_command_requires_identity_and_reads_passwords_hidden(monkeypatch, tmp_path, capsys):
    engine, sessions = recovery_database(monkeypatch, tmp_path)
    from app import commands
    from app.db import DATABASE_URL
    import sys

    monkeypatch.setenv("VIGILON_ADMIN_USERNAME", "configured-admin")
    monkeypatch.setattr(sys, "argv", ["commands.py", "reset-admin-password"])
    target = "SQLite " + str(Path(DATABASE_URL.split("sqlite:///", 1)[1]).resolve())
    answers = iter((target, "configured-admin"))
    monkeypatch.setattr("builtins.input", lambda prompt: next(answers))
    passwords = iter(("new-password-from-hidden-prompt", "new-password-from-hidden-prompt"))
    monkeypatch.setattr(commands.getpass, "getpass", lambda prompt: next(passwords))

    commands.main()

    output = capsys.readouterr().out
    assert "password updated" in output
    assert "new-password-from-hidden-prompt" not in output
    with sessions() as session:
        user = session.scalar(select(db.User).where(db.User.username == "configured-admin"))
        assert PasswordHasher().verify(user.password_hash, "new-password-from-hidden-prompt")
    engine.dispose()


def test_reset_command_refuses_mismatched_database_target(monkeypatch, tmp_path):
    engine, sessions = recovery_database(monkeypatch, tmp_path)
    from app import commands
    import sys

    monkeypatch.setenv("VIGILON_ADMIN_USERNAME", "configured-admin")
    monkeypatch.setattr(sys, "argv", ["commands.py", "reset-admin-password"])
    monkeypatch.setattr("builtins.input", lambda prompt: "different database")
    monkeypatch.setattr(commands.getpass, "getpass", lambda prompt: pytest.fail("Password prompt must not open"))
    with pytest.raises(SystemExit, match="Database target confirmation"):
        commands.main()
    with sessions() as session:
        user = session.scalar(select(db.User).where(db.User.username == "configured-admin"))
        assert PasswordHasher().verify(user.password_hash, "old-password-that-is-long")
    engine.dispose()


def test_login_session_logout_and_role_restrictions_use_an_isolated_database(monkeypatch, tmp_path):
    from app import main

    engine = create_engine(f"sqlite:///{tmp_path / 'auth.sqlite'}")
    db.Base.metadata.create_all(engine)
    sessions = sessionmaker(engine, expire_on_commit=False)
    monkeypatch.setattr(main, "Session", sessions)
    monkeypatch.setenv("VIGILON_COOKIE_SECURE", "false")
    with sessions.begin() as session:
        session.add_all([
            db.User(username="test-admin", password_hash=PasswordHasher().hash("isolated-admin-password"), role=db.Role.ADMIN),
            db.User(username="test-operator", password_hash=PasswordHasher().hash("isolated-operator-password"), role=db.Role.OPERATOR),
        ])

    admin = TestClient(main.app)
    rejected = admin.post("/api/auth/login", json={"username": "test-admin", "password": "incorrect-password"})
    assert rejected.status_code == 401 and rejected.json()["detail"] == "Invalid credentials"
    login = admin.post("/api/auth/login", json={"username": "test-admin", "password": "isolated-admin-password"})
    assert login.status_code == 200 and login.json()["username"] == "test-admin"
    identity = admin.get("/api/auth/session")
    assert identity.status_code == 200 and identity.json()["authenticated"] is True
    assert identity.json()["role"] == "ADMIN"
    assert admin.get("/api/plans").status_code == 200

    operator = TestClient(main.app)
    assert operator.post("/api/auth/login", json={"username": "test-operator", "password": "isolated-operator-password"}).status_code == 200
    assert operator.post("/api/plans", json={"name": "Not allowed"}).status_code == 403

    assert admin.post("/api/auth/logout").status_code == 200
    assert admin.get("/api/auth/session").json()["authenticated"] is False
    assert admin.get("/api/plans").status_code == 401
    engine.dispose()
