"""Machine identity, allocation shape and profile cache."""

import dataclasses
import json

from nunatak import machine as machine_module
from nunatak.pivot import Allocation, Ceiling, Machine, Quality
from nunatak.pivot.persistence import machine_from_dict, machine_to_dict


def sample_machine(**overrides) -> Machine:
    fields = {
        "system": "Linux",
        "kernel": "6.14.0-27-generic",
        "architecture": "x86_64",
        "cpu_model": "AMD EPYC 7702",
        "logical_cores": 128,
        "allocation": Allocation(
            visible_cores=8,
            affinity_mask=(0, 1, 2, 3, 4, 5, 6, 7),
            cpu_quota=None,
            memory_limit_bytes=None,
        ),
    }
    fields.update(overrides)
    return Machine(**fields)


class TestAllocation:
    def cgroup(self, tmp_path, cpu_max=None, memory_max=None):
        proc_self = tmp_path / "cgroup"
        proc_self.write_text("0::/user.slice/job\n")
        directory = tmp_path / "sys" / "user.slice" / "job"
        directory.mkdir(parents=True, exist_ok=True)
        if cpu_max is not None:
            (directory / "cpu.max").write_text(cpu_max)
        if memory_max is not None:
            (directory / "memory.max").write_text(memory_max)
        return machine_module.allocation(
            proc_self=proc_self, cgroup_root=tmp_path / "sys"
        )

    def test_a_cpu_quota_is_reported_in_cores(self, tmp_path):
        assert self.cgroup(tmp_path, cpu_max="200000 100000\n").cpu_quota == 2.0

    def test_an_unbounded_quota_is_none_not_a_number(self, tmp_path):
        allocation = self.cgroup(tmp_path, cpu_max="max 100000\n")
        assert allocation.cpu_quota is None

    def test_the_memory_cap_is_reported_in_bytes(self, tmp_path):
        allocation = self.cgroup(tmp_path, memory_max="8589934592\n")
        assert allocation.memory_limit_bytes == 8589934592
        assert self.cgroup(tmp_path, memory_max="max\n").memory_limit_bytes is None

    def test_without_a_unified_hierarchy_the_bounds_are_unknown(self, tmp_path):
        allocation = machine_module.allocation(
            proc_self=tmp_path / "absent", cgroup_root=tmp_path
        )
        assert allocation.cpu_quota is None
        assert allocation.memory_limit_bytes is None
        # The affinity side does not depend on cgroups.
        assert allocation.visible_cores


class TestIdentity:
    def test_identical_nodes_share_one_identity(self):
        assert machine_module.identity(sample_machine()) == machine_module.identity(
            sample_machine()
        )

    def test_a_different_share_of_the_same_node_is_another_machine(self):
        half = sample_machine(
            allocation=Allocation(visible_cores=4, affinity_mask=(0, 1, 2, 3))
        )
        assert machine_module.identity(half) != machine_module.identity(
            sample_machine()
        )

    def test_the_placement_of_the_cores_matters(self):
        # Cores 0-7 and cores 8-15 see different caches and NUMA nodes.
        elsewhere = sample_machine(
            allocation=Allocation(
                visible_cores=8, affinity_mask=(8, 9, 10, 11, 12, 13, 14, 15)
            )
        )
        assert machine_module.identity(elsewhere) != machine_module.identity(
            sample_machine()
        )

    def test_a_kernel_update_does_not_change_the_machine(self):
        updated = sample_machine(kernel="6.15.0-1-generic")
        assert machine_module.identity(updated) == machine_module.identity(
            sample_machine()
        )

    def test_ceilings_are_the_content_never_the_key(self):
        calibrated = dataclasses.replace(
            sample_machine(),
            ceilings=(
                Ceiling(
                    name="flops_dp",
                    value=1.2e12,
                    unit="flop/s",
                    quality=Quality.MEASURED,
                ),
            ),
        )
        assert machine_module.identity(calibrated) == machine_module.identity(
            sample_machine()
        )


class TestCache:
    def calibrated(self) -> Machine:
        return dataclasses.replace(
            sample_machine(),
            ceilings=(
                Ceiling(
                    name="dram_bandwidth",
                    value=3.2e11,
                    unit="byte/s",
                    quality=Quality.MEASURED,
                ),
            ),
        )

    def test_a_stored_profile_loads_back_for_the_same_identity(self, tmp_path):
        machine_module.store(self.calibrated(), tmp_path)
        loaded = machine_module.load(sample_machine(), tmp_path)
        assert loaded == self.calibrated()

    def test_an_unknown_machine_has_no_profile(self, tmp_path):
        assert machine_module.load(sample_machine(), tmp_path) is None

    def test_a_profile_from_other_calibration_kernels_is_stale(self, tmp_path):
        path = machine_module.store(self.calibrated(), tmp_path)
        payload = json.loads(path.read_text())
        payload["kernel_version"] = machine_module.KERNEL_VERSION - 1
        path.write_text(json.dumps(payload))
        assert machine_module.load(sample_machine(), tmp_path) is None

    def test_a_corrupt_profile_is_ignored_not_fatal(self, tmp_path):
        path = machine_module.store(self.calibrated(), tmp_path)
        path.write_text("not json")
        assert machine_module.load(sample_machine(), tmp_path) is None

    def test_the_cache_honors_xdg_cache_home(self, tmp_path, monkeypatch):
        monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
        assert machine_module.cache_directory() == tmp_path / "nunatak" / "machines"


class TestSerializedForm:
    def test_the_machine_dict_round_trips(self):
        machine = sample_machine()
        assert machine_from_dict(machine_to_dict(machine)) == machine

    def test_a_snapshot_written_before_the_allocation_shape_reads_back(self):
        # The manifest of a Run written by an older nunatak has no
        # allocation entry: absent is not zero.
        data = machine_to_dict(sample_machine())
        del data["allocation"]
        machine = machine_from_dict(data)
        assert machine.allocation == Allocation()


class TestSnapshot:
    def test_the_snapshot_carries_the_allocation_shape(self):
        from tests.support import ScriptedExecutor

        snapshot = machine_module.snapshot(ScriptedExecutor())
        assert snapshot.allocation.visible_cores
        assert snapshot.logical_cores
