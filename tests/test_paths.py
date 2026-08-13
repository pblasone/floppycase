from pathlib import Path

from floppycase.paths import Paths


def test_resolve_and_ensure(tmp_path):
    paths = Paths.resolve(tmp_path / "FloppyCase")
    paths.ensure()
    for directory in paths.all_dirs():
        assert directory.is_dir()


def test_config_file_suffix(tmp_path):
    paths = Paths.resolve(tmp_path)
    assert paths.config_file("a500").name == "a500.uae"
    assert paths.config_file("a500.uae").name == "a500.uae"


def test_env_override(tmp_path, monkeypatch):
    monkeypatch.setenv("FLOPPYCASE_HOME", str(tmp_path / "custom"))
    paths = Paths.resolve()
    assert paths.base == Path(tmp_path / "custom")


def test_legacy_env_override(tmp_path, monkeypatch):
    monkeypatch.delenv("FLOPPYCASE_HOME", raising=False)
    monkeypatch.setenv("EASYAMIGA_HOME", str(tmp_path / "legacy"))
    paths = Paths.resolve()
    assert paths.base == Path(tmp_path / "legacy")
