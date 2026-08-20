"""Theoretical peaks per microarchitecture: the last rung of the ladder.

The table holds what a core can retire per cycle - a few dozen entries
that evolve slowly - and is crossed with what the system exposes at run
time: the microarchitecture identifiers, the frequency, and the
allocation shape. A theoretical peak is systematically unreachable in
practice (turbo, throttling, cgroup limits), so it only ever yields
Ceilings of Quality `estimated`, with the reason.

An unknown microarchitecture yields no Ceiling, never an extrapolation:
a wrong ceiling labeled `estimated` still bends every classification
built on it. Memory bandwidth has no theoretical entry at all - it
depends on the DIMM population, which nothing exposes reliably - and
only exists once the calibration kernel has measured it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from nunatak.machine import allocated_cores
from nunatak.pivot import Ceiling, Machine, Quality

_CPUINFO = Path("/proc/cpuinfo")
_MAX_FREQUENCY = Path("/sys/devices/system/cpu/cpu0/cpufreq/cpuinfo_max_freq")


@dataclass(frozen=True)
class MicroArchitecture:
    """What one core can retire per cycle, an FMA counting as two FLOPs.

    Values are the microarchitecture's maximum (the widest SKU): a
    theoretical Ceiling is an upper bound, and a lower-tier SKU under it
    is exactly what the estimated Quality announces.
    """

    name: str
    dp_flops_per_cycle: float
    sp_flops_per_cycle: float


# x86 entries keyed by (vendor, family, model range). Model ranges follow
# the vendor's numbering; a family listed with None covers all models.
_X86 = [
    ("AuthenticAMD", 23, range(0x00, 0x30), MicroArchitecture("zen", 8, 16)),
    ("AuthenticAMD", 23, range(0x30, 0x100), MicroArchitecture("zen2", 16, 32)),
    ("AuthenticAMD", 25, range(0x00, 0x10), MicroArchitecture("zen3", 16, 32)),
    ("AuthenticAMD", 25, range(0x10, 0x20), MicroArchitecture("zen4", 16, 32)),
    ("AuthenticAMD", 25, range(0x20, 0x60), MicroArchitecture("zen3", 16, 32)),
    ("AuthenticAMD", 25, range(0x60, 0x80), MicroArchitecture("zen4", 16, 32)),
    ("AuthenticAMD", 25, range(0xA0, 0xB0), MicroArchitecture("zen4", 16, 32)),
    ("AuthenticAMD", 26, None, MicroArchitecture("zen5", 32, 64)),
    ("GenuineIntel", 6, [0x55], MicroArchitecture("skylake-sp", 32, 64)),
    ("GenuineIntel", 6, [0x6A, 0x6C], MicroArchitecture("icelake-sp", 32, 64)),
    ("GenuineIntel", 6, [0x8F], MicroArchitecture("sapphire-rapids", 32, 64)),
    ("GenuineIntel", 6, [0xCF], MicroArchitecture("emerald-rapids", 32, 64)),
    ("GenuineIntel", 6, [0xAD], MicroArchitecture("granite-rapids", 32, 64)),
    (
        "GenuineIntel",
        6,
        [0x3C, 0x3D, 0x3F, 0x45, 0x46, 0x47, 0x4F, 0x56],
        MicroArchitecture("haswell/broadwell", 16, 32),
    ),
    (
        "GenuineIntel",
        6,
        [0x4E, 0x5E, 0x8E, 0x9E, 0xA5, 0xA6, 0xA7],
        MicroArchitecture("skylake", 16, 32),
    ),
    (
        "GenuineIntel",
        6,
        [0x97, 0x9A, 0xB7, 0xBA, 0xBF],
        MicroArchitecture("alderlake/raptorlake", 16, 32),
    ),
]

# ARM entries keyed by (implementer, part), from the MIDR register that
# the kernel exposes in /proc/cpuinfo.
_ARM = {
    (0x41, 0xD0C): MicroArchitecture("neoverse-n1", 8, 16),
    (0x41, 0xD40): MicroArchitecture("neoverse-v1", 16, 32),
    (0x41, 0xD49): MicroArchitecture("neoverse-n2", 8, 16),
    (0x41, 0xD4F): MicroArchitecture("neoverse-v2", 16, 32),
}

# Apple performance cores carry four 128-bit NEON pipes; every M
# generation so far keeps that shape.
_APPLE = MicroArchitecture("apple-m", 16, 32)


def _cpuinfo_field(text: str, field: str) -> str | None:
    """First value of `field` in /proc/cpuinfo text, None when absent."""
    match = re.search(rf"^{re.escape(field)}\s*:\s*(.+)$", text, re.MULTILINE)
    return match.group(1).strip() if match else None


def identify(text: str | None) -> MicroArchitecture | None:
    """The table entry for an identification text, whatever machine is
    asking: an x86 cpuinfo names a `vendor_id`, an aarch64 one a `CPU
    implementer`, so the text dispatches itself. This is the entry point
    for identifications that crossed the execution boundary - a replayed
    Machine snapshot legitimately describes the replaying host, and only
    the recorded text says what the tools actually ran on."""
    if not text:
        return None
    if _cpuinfo_field(text, "vendor_id") is not None:
        return x86_microarchitecture(text)
    if _cpuinfo_field(text, "CPU implementer") is not None:
        return arm_microarchitecture(text)
    return None


def x86_microarchitecture(text: str) -> MicroArchitecture | None:
    """The table entry for an x86 /proc/cpuinfo, None when not listed."""
    vendor = _cpuinfo_field(text, "vendor_id")
    family = _cpuinfo_field(text, "cpu family")
    model = _cpuinfo_field(text, "model")
    if vendor is None or family is None or model is None:
        return None
    for entry_vendor, entry_family, models, microarchitecture in _X86:
        if (
            vendor == entry_vendor
            and int(family) == entry_family
            and (models is None or int(model) in models)
        ):
            return microarchitecture
    return None


def arm_microarchitecture(text: str) -> MicroArchitecture | None:
    """The table entry for an aarch64 /proc/cpuinfo, None when not listed."""
    implementer = _cpuinfo_field(text, "CPU implementer")
    part = _cpuinfo_field(text, "CPU part")
    if implementer is None or part is None:
        return None
    return _ARM.get((int(implementer, 16), int(part, 16)))


def detect(machine: Machine, cpuinfo: Path = _CPUINFO) -> MicroArchitecture | None:
    """The microarchitecture this Machine runs on, None when the table
    does not list it - in which case no Ceiling is produced, ever."""
    if machine.system == "Darwin":
        if machine.cpu_model and machine.cpu_model.startswith("Apple M"):
            return _APPLE
        return None
    try:
        text = cpuinfo.read_text()
    except OSError:
        return None
    if machine.architecture in ("x86_64", "amd64"):
        return x86_microarchitecture(text)
    if machine.architecture == "aarch64":
        return arm_microarchitecture(text)
    return None


def frequency(
    maximum: Path = _MAX_FREQUENCY, cpuinfo: Path = _CPUINFO
) -> tuple[float, str | None] | None:
    """The core frequency in Hz and an honesty caveat, None when nothing
    is exposed.

    In order: the rated maximum from cpufreq, the frequency printed in
    the brand string, and finally the highest currently observed
    frequency - the latter is not a rated maximum, and the caveat says
    so in the Ceiling's reason.
    """
    try:
        return int(maximum.read_text().strip()) * 1e3, None
    except (OSError, ValueError):
        pass
    try:
        text = cpuinfo.read_text()
    except OSError:
        return None
    brand = _cpuinfo_field(text, "model name") or ""
    match = re.search(r"@\s*([\d.]+)\s*GHz", brand)
    if match:
        return float(match.group(1)) * 1e9, None
    observed = [
        float(m.group(1))
        for m in re.finditer(r"^cpu MHz\s*:\s*([\d.]+)$", text, re.MULTILINE)
    ]
    if observed:
        return max(observed) * 1e6, "observed frequency, not a rated maximum"
    return None


def ceilings(
    machine: Machine,
    microarchitecture: MicroArchitecture | None,
    clock: tuple[float, str | None] | None,
) -> tuple[Ceiling, ...]:
    """The estimated FLOP/s Ceilings of `machine`, scaled to its
    allocation; empty when the microarchitecture, the frequency or the
    core count is unknown - absence, never extrapolation."""
    cores = allocated_cores(machine)
    if microarchitecture is None or clock is None or cores is None:
        return ()
    hertz, caveat = clock
    reason = (
        f"theoretical peak of {microarchitecture.name}: {cores:g} cores x "
        f"{hertz / 1e9:.2f} GHz x {{flops:g}} FLOP/cycle; run `nunatak calibrate` "
        "for a measured Ceiling"
    )
    if caveat is not None:
        reason += f" ({caveat})"
    return tuple(
        Ceiling(
            name=name,
            value=cores * hertz * flops_per_cycle,
            unit="flop/s",
            quality=Quality.ESTIMATED,
            reason=reason.format(flops=flops_per_cycle),
        )
        for name, flops_per_cycle in (
            ("flops_dp", microarchitecture.dp_flops_per_cycle),
            ("flops_sp", microarchitecture.sp_flops_per_cycle),
        )
    )


def theoretical_ceilings(machine: Machine) -> tuple[Ceiling, ...]:
    """The estimated Ceilings of the Machine this process runs on."""
    return ceilings(machine, detect(machine), frequency())
