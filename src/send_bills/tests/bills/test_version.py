from send_bills.bills.templatetags.version import version


def test_version_tag_uses_runtime_env(monkeypatch):
    monkeypatch.setenv("VERSION", "1.2.3")

    assert version() == "1.2.3"


def test_version_tag_falls_back_to_unknown(monkeypatch):
    monkeypatch.delenv("VERSION", raising=False)

    assert version() == "unknown"


def test_version_tag_treats_empty_env_as_unknown(monkeypatch):
    monkeypatch.setenv("VERSION", "")

    assert version() == "unknown"
