# Resolution levels

Every Hotspot declares how far its attribution reached. The level is a
statement about identity, displayed as neutral text beside the name.

| Value | Meaning | The way forward |
|---|---|---|
| `line` | a source file and a line, from debug information | nothing to do |
| `function` | a name from the symbol table of a binary built without `-g` | recompile with `-g` |
| `symbol` | a name from the dynamic symbols of a stripped module | install the debuginfo package |
| `unresolved` | no symbol covers the address; displayed `module+0x3a1c` | none, and often none is wanted |

`function` and `symbol` describe the same thing to a reader - a name
without a source position - and they call for different actions, which is
why they are two levels and not one.

An address is attributed only to a symbol that contains it, inside
`[address, address + size)`. An address in the gap between two symbols
stays `unresolved` rather than being named after the symbol that precedes
it. Kernel and vdso addresses stay unresolved by design.

A resolution level is not [Quality](quality.md). A failed attribution
loses the name, never the measurement: that time really was spent at that
address, and the value stays `measured`.
