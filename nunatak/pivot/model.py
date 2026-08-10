"""Domain model of the measured pivot.

The vocabulary is bound to the reference glossary (`CONTEXT.md`): the same
words are used in the code, the interface and the documentation, and the
terms it proscribes appear nowhere.

The pivot holds measured data only; the Diagnostic, the roofline placement
and any aggregate across Loci are recomputed on demand and never
persisted: storing a conclusion would freeze a question that has not
been asked yet.
"""

from __future__ import annotations

import enum
import math
from dataclasses import dataclass, field


class Quality(enum.Enum):
    """Confidence label of a Measurement or a Ceiling.

    "measured" comes from a raw counter or a successful Calibration;
    "estimated" results from a motivated downgrade or a theoretical model;
    "unavailable" states that a missing quantity is not zero.
    """

    MEASURED = "measured"
    ESTIMATED = "estimated"
    UNAVAILABLE = "unavailable"

    @staticmethod
    def worst(*qualities: Quality) -> Quality:
        """Propagate Quality along a lineage: the worst of the inputs.

        The Quality of a derived metric is never set by hand: it is always
        computed from the Qualities of its inputs.
        """
        order = [Quality.MEASURED, Quality.ESTIMATED, Quality.UNAVAILABLE]
        return max(qualities, key=order.index)


class ResolutionLevel(enum.Enum):
    """How far the attribution of a Hotspot could go.

    Distinct from Quality: when attribution fails, the Measurement stays
    exact - that time really was spent at that address - and it is the
    identity that degrades, not the value.
    """

    LINE = "line"
    FUNCTION = "function"
    SYMBOL = "symbol"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True)
class PhysicalIdentity:
    """Physical identity of a native Hotspot: `(build-id | LC_UUID, offset)`.

    Aggregates inside a Run and validates cross-Pass merges: raw counters
    from two Passes may only combine when the module is identical in both.
    Only native code has one. No absolute address is ever stored: the offset
    is relative to the module, so ASLR and function reordering cannot split
    a Hotspot.
    """

    module_id: str
    offset: int


@dataclass(frozen=True)
class LogicalIdentity:
    """Logical identity of a Hotspot: `(module, demangled name, source file)`.

    Used for display, for the language model, and to compare Runs. The
    declaration line is an attribute of the Hotspot, never part of this key.
    """

    module: str
    name: str | None = None
    source_file: str | None = None


@dataclass(frozen=True)
class Hotspot:
    """The atomic unit of analysis: CPU function, GPU kernel or Python frame.

    `offset` is a display and disambiguation detail for unresolved Hotspots;
    lines and the inlining chain, internal details of the Hotspot, arrive
    with the attribution chain.
    """

    logical_identity: LogicalIdentity
    resolution_level: ResolutionLevel
    physical_identity: PhysicalIdentity | None = None
    offset: int | None = None

    def __post_init__(self) -> None:
        if self.resolution_level is ResolutionLevel.UNRESOLVED:
            if self.logical_identity.name is not None:
                raise ValueError("an unresolved Hotspot carries no name")
        elif self.logical_identity.name is None:
            raise ValueError(
                f"resolution level '{self.resolution_level.value}' requires a demangled name"
            )

    @property
    def display_name(self) -> str:
        """The name shown to the user, `module+0x3a1c` when unresolved.

        An address in a gap between symbols is never attached to the
        neighbouring symbol: naming the gap after its neighbour would be a
        confident lie.
        """
        if self.logical_identity.name is not None:
            return self.logical_identity.name
        offset = self.offset
        if self.physical_identity is not None:
            offset = self.physical_identity.offset
        module = self.logical_identity.module.rsplit("/", 1)[-1]
        return module if offset is None else f"{module}+{offset:#x}"


@dataclass(frozen=True)
class Locus:
    """A point of the execution topology: node > MPI rank > thread on CPU,
    node > device > stream on GPU."""

    node: str
    rank: int | None = None
    thread: int | None = None
    device: int | None = None
    stream: int | None = None

    def __post_init__(self) -> None:
        if self.thread is not None and (self.device is not None or self.stream is not None):
            raise ValueError("a Locus is either CPU (thread) or GPU (device, stream)")
        if self.stream is not None and self.device is None:
            raise ValueError("a GPU stream without a device is meaningless")


@dataclass(frozen=True)
class Measurement:
    """A raw-counter value for one (Hotspot, Locus) couple.

    It carries what is needed to judge its own solidity: its number of
    samples, its coverage ratio when counters were multiplexed, and its Pass
    of origin. An estimated value always carries the reason of its
    downgrade; "unavailable" has no value, because unavailable is not zero.
    """

    hotspot: Hotspot
    locus: Locus
    counter: str
    value: float | None
    unit: str
    quality: Quality
    reason: str | None = None
    sample_count: int | None = None
    coverage: float | None = None
    pass_index: int = 0

    def __post_init__(self) -> None:
        if self.quality is Quality.ESTIMATED and self.reason is None:
            raise ValueError("a downgrade to 'estimated' is always motivated")
        if self.quality is Quality.MEASURED and self.reason is not None:
            raise ValueError("a measured value carries no downgrade reason")
        if self.quality is Quality.UNAVAILABLE:
            if self.value is not None:
                raise ValueError("'unavailable' is not a value, not even zero")
        elif self.value is None:
            raise ValueError(f"a {self.quality.value} Measurement requires a numeric value")

    @property
    def relative_error(self) -> float | None:
        """Sampling error, decreasing in 1/sqrt(n)."""
        if not self.sample_count:
            return None
        return 1.0 / math.sqrt(self.sample_count)


@dataclass(frozen=True)
class InlineFrame:
    """One step of a persisted inlining chain: a name, a source position.

    An inline frame is nothing but a line come from another file: it is an
    internal detail of the Hotspot, never a unit of analysis. `line` is
    where the sampled address falls, `declaration_line` where the function
    starts; both are None, and the file with them, when the module carried
    no debug information.
    """

    function: str
    file: str | None = None
    line: int | None = None
    declaration_line: int | None = None


@dataclass(frozen=True)
class AddressDetail:
    """The internal detail of a named Hotspot at one sampled address: the
    inlining chain seen there and the weight it carries.

    Frames are innermost first, the physical function last. Weights are
    aggregated over Loci: the per-line view says where time goes inside a
    function, imbalance stays at the Measurement grain. This is what lets
    a report ventilate a Hotspot by line and by inline frame - and build
    the transverse per-inline-frame view, the only view stable across a
    recompilation - on a machine where the binary and the symbolizer no
    longer exist.
    """

    hotspot: Hotspot
    offset: int
    counter: str
    value: float
    frames: tuple[InlineFrame, ...]
    sample_count: int | None = None
    pass_index: int = 0


@dataclass(frozen=True)
class SourceExtract:
    """An embedded source extract for one named Hotspot - never a whole
    file: the body of the physical function and its hot inline frames,
    a few context lines around.

    `file` is the path DWARF recorded (the identity), `resolved_path`
    where the text was actually read. When `text` is None, `reason` says
    why the source is absent - not found, ambiguous - so the report can
    say it instead of silently showing nothing. Embedding the text keeps
    the Run self-sufficient: it is readable in six months, on a machine
    where the source tree no longer exists, and its size stays bounded.
    """

    hotspot: Hotspot
    file: str
    resolved_path: str | None = None
    start_line: int | None = None
    end_line: int | None = None
    text: str | None = None
    truncated: bool = False
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.text is None and self.reason is None:
            raise ValueError("an absent source extract always carries its reason")
        if self.text is not None and self.reason is not None:
            raise ValueError("an embedded source extract carries no absence reason")


@dataclass(frozen=True)
class Event:
    """A timestamped fact with a duration: GPU kernel launch, MPI call.

    The Event stream feeds the report timeline and the network analysis; it
    is distinct from the aggregated Measurements.
    """

    locus: Locus
    kind: str
    name: str
    start_ns: int
    duration_ns: int
    pass_index: int = 0
    attributes: tuple[tuple[str, str], ...] = ()


@dataclass(frozen=True)
class Collector:
    """An external tool orchestrated during a Pass, with its detected version."""

    tool: str
    version: str


@dataclass(frozen=True)
class Pass:
    """One execution of the application within a single Run."""

    index: int
    exit_code: int
    collectors: tuple[Collector, ...] = ()
    start: str | None = None
    end: str | None = None


@dataclass(frozen=True)
class Ceiling:
    """An upper performance bound of the Machine, reachable in practice.

    Carries a Quality like a Measurement does: "measured" from a successful
    Calibration, "estimated" when theoretical or measured under suspicious
    conditions.
    """

    name: str
    value: float
    unit: str
    quality: Quality
    reason: str | None = None

    def __post_init__(self) -> None:
        if self.quality is Quality.ESTIMATED and self.reason is None:
            raise ValueError("an estimated Ceiling is always motivated")


@dataclass(frozen=True)
class Machine:
    """The hardware a Run executes on, carrier of the roofline Ceilings.

    Its identity is not a node - the node is a Locus level - but a couple
    hardware + allocation shape. Every Run embeds a complete snapshot of its
    Machine in its manifest.
    """

    system: str
    kernel: str
    architecture: str
    cpu_model: str | None = None
    logical_cores: int | None = None
    ceilings: tuple[Ceiling, ...] = ()


@dataclass
class Provenance:
    """What allows a Run to be explained without replaying it.

    Best-effort and descriptive, never certifying: it records what it
    observes and never blocks a Run. The effective configuration includes
    the thresholds that drive Quality: a threshold can be tuned, it cannot
    be tuned silently.
    """

    commit: str | None = None
    dirty_tree: bool | None = None
    dependencies: dict[str, str] = field(default_factory=dict)
    effective_configuration: dict[str, object] = field(default_factory=dict)


@dataclass(frozen=True)
class Degradation:
    """A missing capability, named, announced before the run, with the way
    forward. Never a refusal: a missing capability removes measurements,
    it does not prevent the run."""

    name: str
    message: str
    remedy: str | None = None


@dataclass
class Run:
    """A profiling session: the persisted container of the measured pivot.

    A Run is a single directory, whatever the number of ranks: a directory
    survives scp, archiving and being attached to a ticket. It contains no
    analysis output and no Explanation.
    """

    name: str
    created: str
    command: list[str]
    exit_code: int
    machine: Machine
    provenance: Provenance
    passes: list[Pass] = field(default_factory=list)
    degradations: list[Degradation] = field(default_factory=list)
    measurements: list[Measurement] = field(default_factory=list)
    events: list[Event] = field(default_factory=list)
    address_details: list[AddressDetail] = field(default_factory=list)
    source_extracts: list[SourceExtract] = field(default_factory=list)
