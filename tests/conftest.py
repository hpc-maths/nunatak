import pytest


@pytest.fixture(autouse=True)
def isolated_site_config(monkeypatch, tmp_path_factory):
    """Keep the developer's /etc/nunatak.toml out of every test."""
    missing = tmp_path_factory.mktemp("site") / "nunatak.toml"
    monkeypatch.setenv("NUNATAK_SITE_CONFIG", str(missing))


@pytest.fixture(autouse=True)
def isolated_machine_cache(monkeypatch, tmp_path_factory):
    """Keep the developer's Machine profiles out of every test - and every
    test's calibration out of the developer's cache."""
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path_factory.mktemp("cache")))
