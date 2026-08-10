"""Theoretical peaks: detection, table lookup, and estimated Ceilings.

The x86 fixture is the verbatim identification block of the AMD EPYC
7702 corpus machine; the others are the identification lines the Linux
kernel prints for those parts.
"""

from nunatak.calibration import theory
from nunatak.pivot import Allocation, Machine, Quality

EPYC_7702 = """\
processor\t: 0
vendor_id\t: AuthenticAMD
cpu family\t: 23
model\t\t: 49
model name\t: AMD EPYC 7702 64-Core Processor
"""

XEON_GOLD = """\
processor\t: 0
vendor_id\t: GenuineIntel
cpu family\t: 6
model\t\t: 85
model name\t: Intel(R) Xeon(R) Gold 6248 CPU @ 2.50GHz
"""

GRAVITON2 = """\
processor\t: 0
BogoMIPS\t: 243.75
CPU implementer\t: 0x41
CPU architecture: 8
CPU variant\t: 0x3
CPU part\t: 0xd0c
"""


def machine(**overrides) -> Machine:
    fields = {
        "system": "Linux",
        "kernel": "6.14.0",
        "architecture": "x86_64",
        "cpu_model": "AMD EPYC 7702 64-Core Processor",
        "logical_cores": 128,
        "allocation": Allocation(visible_cores=8),
    }
    fields.update(overrides)
    return Machine(**fields)


class TestDetection:
    def test_the_corpus_machine_is_zen2(self):
        microarchitecture = theory.x86_microarchitecture(EPYC_7702)
        assert microarchitecture.name == "zen2"
        assert microarchitecture.dp_flops_per_cycle == 16

    def test_a_cascade_lake_xeon_reaches_avx512_width(self):
        microarchitecture = theory.x86_microarchitecture(XEON_GOLD)
        assert microarchitecture.name == "skylake-sp"
        assert microarchitecture.dp_flops_per_cycle == 32

    def test_a_neoverse_n1_is_found_through_its_midr(self):
        microarchitecture = theory.arm_microarchitecture(GRAVITON2)
        assert microarchitecture.name == "neoverse-n1"
        assert microarchitecture.dp_flops_per_cycle == 8

    def test_an_unlisted_part_yields_none_never_a_guess(self):
        unknown = EPYC_7702.replace("AuthenticAMD", "CentaurHauls")
        assert theory.x86_microarchitecture(unknown) is None
        assert theory.arm_microarchitecture(EPYC_7702) is None

    def test_apple_silicon_is_recognized_from_its_brand_string(self):
        darwin = machine(
            system="Darwin", architecture="arm64", cpu_model="Apple M2 Pro"
        )
        assert theory.detect(darwin).name == "apple-m"
        intel_mac = machine(system="Darwin", cpu_model="Intel(R) Core(TM) i7")
        assert theory.detect(intel_mac) is None


class TestFrequency:
    def test_the_rated_maximum_wins(self, tmp_path):
        rated = tmp_path / "cpuinfo_max_freq"
        rated.write_text("3350000\n")
        assert theory.frequency(maximum=rated, cpuinfo=tmp_path / "x") == (
            3.35e9,
            None,
        )

    def test_the_brand_string_frequency_is_second(self, tmp_path):
        cpuinfo = tmp_path / "cpuinfo"
        cpuinfo.write_text(XEON_GOLD)
        assert theory.frequency(maximum=tmp_path / "x", cpuinfo=cpuinfo) == (
            2.5e9,
            None,
        )

    def test_an_observed_frequency_carries_its_caveat(self, tmp_path):
        cpuinfo = tmp_path / "cpuinfo"
        cpuinfo.write_text(EPYC_7702 + "cpu MHz\t\t: 1996.249\ncpu MHz\t\t: 2600.0\n")
        hertz, caveat = theory.frequency(maximum=tmp_path / "x", cpuinfo=cpuinfo)
        assert hertz == 2.6e9
        assert "not a rated maximum" in caveat

    def test_nothing_exposed_means_no_frequency(self, tmp_path):
        assert (
            theory.frequency(maximum=tmp_path / "x", cpuinfo=tmp_path / "y") is None
        )


class TestCeilings:
    ZEN2 = theory.MicroArchitecture("zen2", 16, 32)

    def test_the_peaks_scale_to_the_allocation(self):
        dp, sp = theory.ceilings(machine(), self.ZEN2, (2.0e9, None))
        assert dp.name == "flops_dp"
        assert dp.value == 8 * 2.0e9 * 16
        assert dp.quality is Quality.ESTIMATED
        assert "nunatak calibrate" in dp.reason
        assert sp.name == "flops_sp"
        assert sp.value == 2 * dp.value

    def test_the_cgroup_quota_caps_the_cores(self):
        limited = machine(
            allocation=Allocation(visible_cores=8, cpu_quota=2.0)
        )
        (dp, _) = theory.ceilings(limited, self.ZEN2, (2.0e9, None))
        assert dp.value == 2 * 2.0e9 * 16

    def test_unknown_pieces_yield_no_ceiling_never_an_extrapolation(self):
        assert theory.ceilings(machine(), None, (2.0e9, None)) == ()
        assert theory.ceilings(machine(), self.ZEN2, None) == ()
        bare = machine(logical_cores=None, allocation=Allocation())
        assert theory.ceilings(bare, self.ZEN2, (2.0e9, None)) == ()

    def test_the_observed_frequency_caveat_reaches_the_reason(self):
        (dp, _) = theory.ceilings(
            machine(), self.ZEN2, (2.0e9, "observed frequency, not a rated maximum")
        )
        assert "not a rated maximum" in dp.reason
