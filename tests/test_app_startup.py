import os


def test_app_imports_with_required_settings(monkeypatch):
    monkeypatch.setenv("PESC_LOGIN", "79001234567")
    monkeypatch.setenv("PESC_PASSWORD", "password")
    monkeypatch.setenv("DATA_DIR", os.devnull)

    from portal.main import app

    assert app.title == "ikus.pesc.ru API"
