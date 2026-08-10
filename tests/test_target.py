"""Seeing the real target binary through launchers."""

import os
import stat

from nunatak.target import real_target


def executable(tmp_path, name):
    path = tmp_path / name
    path.write_text("#!/bin/sh\nexit 0\n")
    path.chmod(path.stat().st_mode | stat.S_IXUSR)
    return str(path)


def test_a_plain_command_is_its_own_target(tmp_path):
    assert real_target(["./solver", "--steps", "10"]) == "./solver"


def test_the_target_behind_mpirun_is_the_binary_not_mpirun(tmp_path):
    solver = executable(tmp_path, "solver")
    assert real_target(["mpirun", "-n", "256", solver]) == solver


def test_environment_assignments_and_nested_launchers_are_skipped(tmp_path):
    solver = executable(tmp_path, "solver")
    command = ["env", "OMP_NUM_THREADS=8", "numactl", "--interleave=all", solver, "input.nml"]
    assert real_target(command) == solver


def test_launcher_without_resolvable_target_gives_none(tmp_path):
    assert real_target(["mpirun", "-n", "4", str(tmp_path / "missing")]) is None
