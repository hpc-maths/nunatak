# What the Run keeps of your code

A Run is one directory that survives `scp`, an archive and a ticket, and
a report is read where the repository is not. So the code a report shows
has to travel with it - and no more of the code than that.

## Extracts, never files

What is embedded is the body of the physical function, the bodies of its
hot inline frames, and three lines of context around each: one extract
per `(Hotspot, file)` couple, capped at 200 lines with the truncation
marked. A whole file would carry code that never ran, and a repository
copied into a Run would stop being a measurement.

The true end of a function is not in the line table, so an extract runs
from the earliest declaration it saw to the last sampled line. Inlining
spreads one Hotspot over several files - a routine inlined from a header
belongs to that header - which is why there is one extract per file the
Hotspot's addresses reach, and why the one displayed is the file the
Hotspot is named after: the sampled line numbers shown beside the text
are that file's.

## Three steps, and then a refusal

A file named by DWARF is searched in this order, and the first hit wins:

| Step | What it tries |
|---|---|
| the recorded path | the absolute path the compiler wrote, as it is |
| the source map | `--source-map OLD=NEW` and `[source_map]`, longest prefix first |
| the basename | one file of that name under the git top level, else the working directory |

The search skips hidden directories and the Runs themselves. When it
finds several files of the right name, nunatak does not choose: the
Hotspot keeps its measurements and loses its text, and the reason names
how many candidates there were and where it looked.

Choosing would be the same mistake as naming an address after its
neighbouring symbol. A reader shown `solver.c` from the wrong subtree
reads lines that never ran, believes them, and optimises them.

## An extract is refused when the file has moved on

DWARF 5 line tables can carry an MD5 checksum of each source file as the
compiler read it. When that fingerprint is present and disagrees with
the file on disk, the extract is refused with that reason and the text
is neither shown nor sent to the model: you edited the file since the
build, and its line numbers no longer point at the code that ran.

Absent fingerprint, no verdict. gcc emits none, so refusing on a guess
would punish every gcc build for a mismatch that may not exist. The
guarantee is therefore exact and narrow. A mismatch is caught when the
compiler made it catchable, and the report says which extracts carry that
assurance.

The checksums are read by the `llvm-dwarfdump` that sits beside the
located `llvm-symbolizer`. On the fallback path there is no dwarfdump,
nothing is fingerprinted, and every extract is accepted as gcc's already
are - which is one of the two capabilities `llvm-missing` declares lost.

## What `--no-source` leaves behind

`--no-source` embeds no text at all, and everything that is not text
stays: the line numbers, the per-line distribution of the samples, the
loop facts, every Measurement. A Hotspot without an extract is still
placed on the roofline and still classified.

What it does cost is the Explanation. Deprived of the code, the model
produces generalities, so a Run without source gets no advice rather
than vague advice - the same rule that withholds a Hotspot whose file
could not be found.
