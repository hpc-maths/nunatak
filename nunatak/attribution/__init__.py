"""Attribution: from module-relative addresses to named Hotspots.

Where the measured pivot records that time was spent at `(module, offset)`,
attribution says what that address is: the physical function, its source
position, and the frames inlined into it - kept as internal detail of the
Hotspot, never as units of analysis. It works on the distinct addresses
left by the aggregation, never on the sample stream.
"""

from nunatak.attribution.symbolizer import (
    AttributionChain,
    Frame,
    ModuleSymbolization,
    Symbolizer,
    locate,
)

__all__ = [
    "AttributionChain",
    "Frame",
    "ModuleSymbolization",
    "Symbolizer",
    "locate",
]
