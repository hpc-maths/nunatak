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


@pytest.fixture(autouse=True)
def stub_report_assets(monkeypatch, tmp_path_factory):
    """Make the compiled report app deterministically present: tests must
    not depend on whether this checkout ever built report-app/."""
    assets = tmp_path_factory.mktemp("assets")
    (assets / "report.js").write_text('console.log("stub bundle")')
    (assets / "report.css").write_text("body { color: inherit }")
    monkeypatch.setattr("nunatak.report.html.ASSETS", assets)
