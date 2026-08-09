import pytest


@pytest.fixture(autouse=True)
def isolated_site_config(monkeypatch, tmp_path_factory):
    """Keep the developer's /etc/nunatak.toml out of every test."""
    missing = tmp_path_factory.mktemp("site") / "nunatak.toml"
    monkeypatch.setenv("NUNATAK_SITE_CONFIG", str(missing))
