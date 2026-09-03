# What makes a delta real

Two Runs are two measurements, not two truths. A diff between them has
four ways of misleading its reader: comparing the wrong things,
comparing everything, reporting a change smaller than the uncertainty it
was measured with, and staying silent about what makes the two Runs
different in the first place.

## The unit is the function you edit

A row is a logical function, inlining included: the pair (function,
source file), never the physical symbol. Optimise a function and the
next build inlines it: the symbol leaves the binary and its time melts
into its caller, so a symbol-grained diff announces the disappearance of
the code you just improved and a regression in whatever called it.

Where sampling recorded address detail, each innermost inline frame
contributes its own time under its own name, and that is what carries a
function through the build that inlined it. A Hotspot without that
detail contributes under its logical identity, and an unresolved one
under its module's base name, which two Runs of the same binary still
match on.

The module is deliberately not part of the key. The binary was rebuilt
between the two Runs, so its path and its build-id name a file rather
than the code, and the pair (function, file) names what a human edits.

## Under one percent of both Runs, nothing is reported

An entity holding less than 1% of the sampled time on both sides is
folded away. Inlining makes symbols come and go on every rebuild, and a
diff of a real application drowned in that churn hides the regression it
exists to show.

An entity present on one side only survives the floor and is shown as
such - `vanished (was 2.42 s)`, or `appeared at` its new time - with no
percentage beside it, because a change needs two sides. A vanished row is
the expected shape of a successful inlining, not a warning.

## A difference smaller than its own error is not a difference

Each side's time comes from a finite number of samples, so it carries an
error that falls as 1/sqrt(n): a Hotspot sampled 2500 times knows its
time to about 2%. The two sides' errors combine, the difference is held
against that combination, and below it the row reads `not a difference`
rather than a percentage a reader would act on.

The practice this refuses is the one every profiler comparison invites:
quoting a percentage without the uncertainty it was measured with. Two
Runs of the same unchanged binary disagree by 1.3% on one kernel of
`examples/stencil`, and [that pair](compare-two-runs.md) is worth
measuring once per machine. A 3% gain between two Hotspots carrying 10%
error is not a gain.

The verdict travels with the number rather than in prose around it: the
terminal writes it on the row, and `--json` carries it as a boolean, so a
performance gate never reimplements the statistics.

## What is not comparable is declared, and diffed anyway

Four differences between two Runs make their times not directly
comparable, and each rides above the diff as a named finding: two
Machines, two commands, two rank topologies, two time bases. The diff is
printed under them and the exit code stays 0.

Declining to diff would be the harmful move. A reader who is refused
subtracts the two numbers in a spreadsheet, where none of the four
findings exists, and a comparison across two Machines then looks exactly
like a comparison on one. Naming the obstacle above the numbers is what
lets a reader decide the numbers are worth reading.

The exit code is part of the same argument: a comparison informs, and
what counts as a regression - which function, how much, how many times
in a row - belongs to whoever reads it.
