"""mpiP: locating the library, preloading it, parsing its report.

The fixture is the verbatim report of mpiP 3.5.0 (built with gcc 14 /
Open MPI 5.0.7 on the EPYC 7702 runner) for a 4-rank workload doing 50
Allreduce rounds plus rank-to-0 Sends: distinguishable per-rank times
and volumes, real formatting quirks included.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

from nunatak.cli import doctor
from nunatak.collect import mpip
from nunatak.config import Config
from nunatak.ingestion import mpip_report
from nunatak.pivot import Quality

FIXTURE = Path(__file__).parent / "fixtures" / "mpi_workload.4.2586003.1.mpiP"
REPO_ROOT = Path(__file__).resolve().parents[1]


class TestLocate:
    def test_the_configured_path_wins_when_it_exists(self, tmp_path):
        library = tmp_path / "libmpiP.so"
        library.write_text("")
        config = Config(tools={"mpip": str(library)})
        assert mpip.locate(config, environment={}) == str(library)

    def test_a_configured_path_that_does_not_exist_is_not_trusted(self, tmp_path):
        config = Config(tools={"mpip": str(tmp_path / "missing.so")})
        assert mpip.locate(config, environment={}) is None

    def test_ld_library_path_is_how_a_module_exposes_the_site_build(self, tmp_path):
        (tmp_path / "libmpiP.so").write_text("")
        environment = {"LD_LIBRARY_PATH": f"/nowhere{os.pathsep}{tmp_path}"}
        assert mpip.locate(Config(), environment) == str(tmp_path / "libmpiP.so")

    def test_without_any_copy_there_is_nothing(self):
        assert mpip.locate(Config(), environment={}) is None


class TestDoctor:
    def test_an_mpi_launch_without_mpip_is_told_before_the_run(self, tmp_path):
        check = doctor._mpi_analysis(Config(tools={"mpip": str(tmp_path / "no.so")}))
        assert check.status == "missing"
        assert check.degradation.name == "mpi-analysis-unavailable"

    def test_a_located_library_reports_ok(self, tmp_path):
        library = tmp_path / "libmpiP.so"
        library.write_text("")
        check = doctor._mpi_analysis(Config(tools={"mpip": str(library)}))
        assert check.status == "ok"
        assert check.detail == str(library)


class TestParser:
    def test_the_verbatim_report_parses_completely(self):
        report = mpip_report.parse(FIXTURE.read_text())
        assert report.version == "3.5.0"
        assert report.nodes == {0: "ci-github", 1: "ci-github", 2: "ci-github", 3: "ci-github"}
        assert report.app_time[0] == 0.451
        assert report.mpi_time[0] == 0.429
        assert report.mpi_time[3] == 0.396
        # Per-rank sent bytes accumulate over callsites: every rank did
        # the Allreduce, ranks 1-3 each added their Send.
        assert report.sent_bytes[0] == 4.194e08
        assert report.sent_bytes[1] == 4.194e08 + 1.638e06

    def test_a_text_that_is_not_a_report_says_so(self):
        assert mpip_report.parse("not a report") is None

    def test_only_the_3x_format_is_parsed(self):
        assert mpip_report.supports("3.5.0")
        assert not mpip_report.supports("4.0")


class TestIngest:
    def test_the_report_becomes_locus_level_measurements(self, tmp_path):
        (tmp_path / FIXTURE.name).write_text(FIXTURE.read_text())
        measurements, degradations, version = mpip_report.ingest_mpip(
            tmp_path, expected=True
        )
        assert degradations == []
        assert version == "3.5.0"
        assert all(m.hotspot is None for m in measurements)
        assert all(m.quality is Quality.MEASURED for m in measurements)
        by_counter = {}
        for measurement in measurements:
            by_counter.setdefault(measurement.counter, []).append(measurement)
        assert set(by_counter) == {"app_time", "mpi_time", "mpi_sent_bytes"}
        mpi_times = {m.locus.rank: m.value for m in by_counter["mpi_time"]}
        assert mpi_times[0] == 0.429e9
        assert all(m.unit == "ns" for m in by_counter["mpi_time"])
        assert all(m.locus.node == "ci-github" for m in measurements)

    def test_a_preloaded_run_without_report_is_declared(self, tmp_path):
        measurements, degradations, version = mpip_report.ingest_mpip(
            tmp_path, expected=True
        )
        assert measurements == []
        assert version is None
        (degradation,) = degradations
        assert degradation.name == "mpi-report-missing"

    def test_a_run_that_never_preloaded_has_no_mpi_layer(self, tmp_path):
        assert mpip_report.ingest_mpip(tmp_path, expected=False) == ([], [], None)

    def test_an_unknown_report_format_is_declared_not_guessed(self, tmp_path):
        (tmp_path / "app.4.1.1.mpiP").write_text(
            "@ mpiP\n@ Version                  : 4.0.1\n"
        )
        measurements, degradations, version = mpip_report.ingest_mpip(
            tmp_path, expected=True
        )
        assert measurements == []
        assert version is None
        (degradation,) = degradations
        assert degradation.name == "ingestion-unsupported"


class TestShimPreload:
    def test_the_application_sees_mpip_and_its_output_directory(self, tmp_path):
        witness = tmp_path / "environment.json"
        collect = tmp_path / "collect"
        environment = dict(os.environ)
        environment["PYTHONPATH"] = str(REPO_ROOT)
        environment["PATH"] = str(tmp_path)  # no perf: the bare ladder
        environment["OMPI_COMM_WORLD_RANK"] = "1"
        environment["OMPI_COMM_WORLD_SIZE"] = "128"
        environment["OMPI_COMM_WORLD_LOCAL_RANK"] = "1"
        environment["LD_PRELOAD"] = "/site/libpreexisting.so"
        probe = (
            "import json, os, sys; "
            f"json.dump({{'LD_PRELOAD': os.environ.get('LD_PRELOAD'), "
            f"'MPIP': os.environ.get('MPIP')}}, open({str(witness)!r}, 'w'))"
        )
        outcome = subprocess.run(
            [
                sys.executable, "-m", "nunatak.rank",
                "--directory", str(collect),
                "--preload", "/opt/mpiP/lib/libmpiP.so",
                "--", sys.executable, "-c", probe,
            ],
            env=environment,
            capture_output=True,
            text=True,
        )
        assert outcome.returncode == 0, outcome.stderr
        seen = json.loads(witness.read_text())
        # Appended, never written over: the site's preload survives.
        assert seen["LD_PRELOAD"] == "/opt/mpiP/lib/libmpiP.so:/site/libpreexisting.so"
        assert seen["MPIP"] == f"-f {collect}"
