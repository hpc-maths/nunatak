"""Domain-model invariants: Quality, identities, honest missing values."""

import pytest

from nunatak.pivot import (
    Ceiling,
    Hotspot,
    LogicalIdentity,
    Locus,
    Measurement,
    PhysicalIdentity,
    Quality,
    ResolutionLevel,
    hotspot_level,
    locus_level,
)


def cpu_locus() -> Locus:
    return Locus(node="n0", rank=0, thread=42)


def unresolved_hotspot() -> Hotspot:
    return Hotspot(
        logical_identity=LogicalIdentity(module="/usr/lib/libfoo.so"),
        resolution_level=ResolutionLevel.UNRESOLVED,
        physical_identity=PhysicalIdentity(module_id="abcd1234", offset=0x3A1C),
        offset=0x3A1C,
    )


class TestQuality:
    def test_worst_propagates_along_lineage(self):
        assert Quality.worst(Quality.MEASURED, Quality.MEASURED) is Quality.MEASURED
        assert Quality.worst(Quality.MEASURED, Quality.ESTIMATED) is Quality.ESTIMATED
        assert (
            Quality.worst(Quality.ESTIMATED, Quality.UNAVAILABLE, Quality.MEASURED)
            is Quality.UNAVAILABLE
        )


class TestMeasurement:
    def test_estimated_requires_a_reason(self):
        with pytest.raises(ValueError, match="motivated"):
            Measurement(
                hotspot=unresolved_hotspot(),
                locus=cpu_locus(),
                counter="cycles",
                value=1.0,
                unit="cycles",
                quality=Quality.ESTIMATED,
            )

    def test_measured_forbids_a_downgrade_reason(self):
        with pytest.raises(ValueError, match="measured"):
            Measurement(
                hotspot=unresolved_hotspot(),
                locus=cpu_locus(),
                counter="cycles",
                value=1.0,
                unit="cycles",
                quality=Quality.MEASURED,
                reason="multiplexed below the coverage threshold",
            )

    def test_unavailable_is_not_zero(self):
        with pytest.raises(ValueError, match="not even zero"):
            Measurement(
                hotspot=unresolved_hotspot(),
                locus=cpu_locus(),
                counter="flops_dp",
                value=0.0,
                unit="flop",
                quality=Quality.UNAVAILABLE,
            )

    def test_measured_requires_a_value(self):
        with pytest.raises(ValueError, match="numeric value"):
            Measurement(
                hotspot=unresolved_hotspot(),
                locus=cpu_locus(),
                counter="cycles",
                value=None,
                unit="cycles",
                quality=Quality.MEASURED,
            )

    def test_relative_error_decreases_in_sqrt_n(self):
        measurement = Measurement(
            hotspot=unresolved_hotspot(),
            locus=cpu_locus(),
            counter="cpu-clock",
            value=1e9,
            unit="ns",
            quality=Quality.MEASURED,
            sample_count=400,
        )
        assert measurement.relative_error == pytest.approx(0.05)
        no_samples = Measurement(
            hotspot=unresolved_hotspot(),
            locus=cpu_locus(),
            counter="cpu-clock",
            value=1e9,
            unit="ns",
            quality=Quality.MEASURED,
        )
        assert no_samples.relative_error is None


class TestHotspot:
    def test_unresolved_displays_module_plus_offset_never_a_neighbour(self):
        assert unresolved_hotspot().display_name == "libfoo.so+0x3a1c"

    def test_unresolved_carries_no_name(self):
        with pytest.raises(ValueError, match="no name"):
            Hotspot(
                logical_identity=LogicalIdentity(module="libfoo.so", name="main"),
                resolution_level=ResolutionLevel.UNRESOLVED,
            )

    def test_resolved_requires_a_name(self):
        with pytest.raises(ValueError, match="demangled name"):
            Hotspot(
                logical_identity=LogicalIdentity(module="libfoo.so"),
                resolution_level=ResolutionLevel.FUNCTION,
            )

    def test_offsets_are_module_relative(self):
        # The model has no field able to hold an absolute address; identity
        # offsets are relative to a module identity.
        identity = PhysicalIdentity(module_id="abcd", offset=0x10)
        assert identity.offset == 0x10
        assert identity.module_id == "abcd"


class TestLocus:
    def test_cpu_and_gpu_paths_are_exclusive(self):
        with pytest.raises(ValueError, match="CPU .* or GPU"):
            Locus(node="n0", thread=1, device=0)

    def test_gpu_stream_requires_a_device(self):
        with pytest.raises(ValueError, match="stream without a device"):
            Locus(node="n0", stream=7)


class TestCeiling:
    def test_estimated_ceiling_is_motivated(self):
        with pytest.raises(ValueError, match="motivated"):
            Ceiling(name="dp_flops", value=1e12, unit="flop/s", quality=Quality.ESTIMATED)
        ok = Ceiling(
            name="dp_flops",
            value=1e12,
            unit="flop/s",
            quality=Quality.ESTIMATED,
            reason="theoretical fallback: calibration kernel unavailable",
        )
        assert ok.reason is not None


class TestLayers:
    def test_a_measurement_without_hotspot_is_locus_level(self):
        aggregate = Measurement(
            hotspot=None,
            locus=cpu_locus(),
            counter="cycles",
            value=1e9,
            unit="count",
            quality=Quality.MEASURED,
        )
        assert locus_level([aggregate]) == [aggregate]
        assert hotspot_level([aggregate]) == []

    def test_the_two_layers_partition_the_measurements(self):
        sampled = Measurement(
            hotspot=unresolved_hotspot(),
            locus=cpu_locus(),
            counter="cycles",
            value=100.0,
            unit="count",
            quality=Quality.MEASURED,
            sample_count=10,
        )
        aggregate = Measurement(
            hotspot=None,
            locus=Locus(node="n0", rank=3),
            counter="cycles",
            value=1e9,
            unit="count",
            quality=Quality.MEASURED,
        )
        both = [sampled, aggregate]
        assert hotspot_level(both) == [sampled]
        assert locus_level(both) == [aggregate]

    def test_locus_level_still_validates_its_quality(self):
        with pytest.raises(ValueError, match="motivated"):
            Measurement(
                hotspot=None,
                locus=cpu_locus(),
                counter="cycles",
                value=1e9,
                unit="count",
                quality=Quality.ESTIMATED,
            )
