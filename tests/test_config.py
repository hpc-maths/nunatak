"""Configuration cascade: site, project, flags, with increasing precedence."""

from pathlib import Path

from nunatak.config import load


def test_defaults_without_any_file(tmp_path):
    config, effective = load(tmp_path)
    assert config.runs_dir == ".nunatak"
    assert config.coverage_threshold == 0.8
    assert config.project_name is None
    assert effective["thresholds.coverage"] == 0.8


def test_project_overrides_site_and_flag_overrides_project(tmp_path):
    site = tmp_path / "site.toml"
    site.write_text(
        'name = "site-name"\nruns_dir = "/scratch/runs"\n[thresholds]\ncoverage = 0.9\n'
    )
    project_dir = tmp_path / "repo"
    project_dir.mkdir()
    (project_dir / "nunatak.toml").write_text('name = "project-name"\n')

    config, effective = load(project_dir, site_config=site)
    assert config.project_name == "project-name"
    assert config.runs_dir == "/scratch/runs"
    assert config.coverage_threshold == 0.9

    config, effective = load(project_dir, name="flag-name", site_config=site)
    assert config.project_name == "flag-name"
    assert effective["name"] == "flag-name"


def test_the_rank_threshold_is_tunable_never_silently(tmp_path):
    (tmp_path / "nunatak.toml").write_text("[sampling]\nrank_threshold = 16\n")
    config, effective = load(tmp_path)
    assert config.sampling_rank_threshold == 16
    assert effective["sampling.rank_threshold"] == 16


def test_the_fp_threshold_is_tunable_never_silently(tmp_path):
    (tmp_path / "nunatak.toml").write_text("[stacks]\nfp_threshold = 0.9\n")
    config, effective = load(tmp_path)
    assert config.stacks_fp_threshold == 0.9
    assert effective["stacks.fp_threshold"] == 0.9


def test_project_file_is_found_upward(tmp_path):
    (tmp_path / "nunatak.toml").write_text('name = "root"\n')
    nested = tmp_path / "a" / "b"
    nested.mkdir(parents=True)
    config, _ = load(nested)
    assert config.project_name == "root"


def test_tool_paths_are_recorded_in_the_effective_configuration(tmp_path):
    (tmp_path / "nunatak.toml").write_text('[tools]\nperf = "/opt/perf/bin/perf"\n')
    config, effective = load(tmp_path)
    assert config.tools["perf"] == "/opt/perf/bin/perf"
    assert effective["tools.perf"] == "/opt/perf/bin/perf"
