# 0006. The HTML report: three reading levels, and the roofline at the third

*Recorded 2026-08-09.*

## Context and decision

The report is the only place where the user meets the whole of the work:
the measured pivot, the deterministic Diagnostic, the LLM's Explanation,
and every form of incompleteness accumulated along the way. The question
was not which views to offer, since the list was known, but what the
report opens on, because that choice governs everything else.

Three variants were built on the same data set and compared on screen
(branch `prototype/rapport-html`, commit `6c5ec2f`): the roofline as the
front door, a written synthesis, a dense inventory. The decision is none
of the three but their composition, in three reading levels:

1. A written synthesis opens the report: findings in natural language,
   ordered by share of the time, each with its quantified evidence. It
   ends on a section called "what this report does not say".
2. A dense inventory lists every Hotspot, sortable and filterable, with
   Quality and resolution level in columns of their own.
3. The detail of one Hotspot, opened from either, is where the roofline
   lives.

The roofline is therefore not the front door, it is the reward for
drilling down. That move, which looked cosmetic, fixes a real defect: a
global roofline has to mix CPU and GPU, whose Ceilings have nothing to do
with each other, or impose a device selector. Contextualised on one
Hotspot, the device becomes implicit and the chart is correct by
construction. It shows the Ceilings, the selected Hotspot highlighted,
and the other Hotspots of the same device as pale points for scale.

## Options considered

- The roofline as the front door (variant A): the expected gesture from a
  roofline tool, dropped because it forces the question "and everything
  with no arithmetic intensity?" to be answered by a side rail, and
  because it mixes two sets of Ceilings or imposes a selector.
- The synthesis alone (variant B): the most readable, dropped on its own
  because a user looking for a specific Hotspot has no way to find it.
- The inventory alone (variant C): the most complete, dropped on its own
  because it does not say where to begin, which is exactly what the user
  came for.
- Inventory and detail side by side, in two panes: tried, then abandoned
  after looking at it. Side by side does not reduce scrolling, it narrows
  both: the table loses its columns and the detail grows longer. The real
  cause of the scrolling was not the page layout but the detail stacked
  in a single column.
- The detail as an overlay (drawer or modal): dropped in favour of
  substitution, which stays printable, introduces no scrolling trap and
  needs no z-order management.
- Tabs inside the detail (roofline / source / facts): dropped once the
  detail moved to two columns, at which point they became one more
  navigation for content that now fits on screen.

## Consequences

### The structure

The three levels substitute for one another, they never coexist. The
inventory and the detail occupy the same area; one scrolls in a single
content at a time. Going back is an explicit button, and `Escape`.

The detail spreads over two columns as soon as it has the room: on the
left the roofline, the metrics, the deterministic facts and the
Explanation; on the right the annotated source, the ventilation by inline
frame and the unfoldable assembler. That is what halves its height and
lets it fit on screen.

Every finding in the synthesis carries direct access to its Hotspot and
its roofline. The synthesis contains no chart: it asserts and cites its
numbers, the chart is at the next level.

Every area is set on one measure. A table spread across the full width of
a large screen separates the name from its numbers and breaks reading;
the space recovered carries a share-of-time bar, which turns emptiness
into information.

### The visual vocabulary of uncertainty

Uncertainty is what the report has to make legible above all, and it
rests on one rule: two registers, two visual channels, never confused.

Quality is carried by colour and shape - measured solid, estimated
hatched, unavailable as a dotted outline. The same encoding applies
everywhere: the dot in a table, the share-of-time bar, the point on the
roofline. An estimated Hotspot is a dotted circle there, a measured one a
solid disc.

The resolution level is carried by a neutral text label (line, function,
symbol, unresolved), with no colour. It does not say the same thing as
Quality and must not look like it: when attribution fails the Measurement
stays exact, and it is the identity that degrades.

A motivated downgrade displays its reason, not only its label:
"downgraded to estimated: counters multiplexed, coverage 63% below the
80% threshold". The label without the reason is useless.

### Making incompleteness legible without drowning the user

A section called "what this report does not say" closes the synthesis and
gathers what is missing: unattributable time, the "others" aggregate and
its statistical floor, estimated Ceilings, kernels without `-lineinfo`,
and unsampled ranks. Gathering those admissions in one named place makes
them legible; scattering them in footnotes would make them invisible.

A Hotspot that cannot be placed on the roofline says so where the reader
expects it. When the user opens an unresolved Hotspot or the "others"
aggregate, the chart is replaced by a box explaining why, instead of
vanishing silently or showing an empty chart. It is variant A's "off the
roofline" rail, better placed.

An absent quantity is written unavailable, never zero and never an empty
cell with no explanation. The table says so explicitly: an empty column
means the quantity is unavailable for that Hotspot, not that it is zero.

The sampling coverage - which ranks, what fraction of GPU launches, what
multiplexing rate - is stated at the head of the synthesis, not relegated
to an appendix. And the LLM's Explanation is always in a distinct frame,
labelled "advice, generated by a model, not reproducible". When it is
absent, the report says why: no source, below the statistical floor,
unresolved Hotspot.

### Modes and drawers

`--no-source` keeps the line numbers and the per-line sample
distribution, the hot line included, and replaces the code text with an
ellipsis. The report stays useful - one still knows where the time goes -
without a line of code leaving the machine.

The Provenance - commit, patch, compilation options, LLVM version and
`-mcpu`, MPI stack, loaded libraries with their build-ids - is a drawer
unfolding from the header, never a dialog and never in the main view. The
assembler is an unfoldable block in the detail, with the reminder that it
is consultable here but never sent to the model.

The comparison view follows the same structure: a synthesis of the
differences, then an inventory of the Hotspots compared by logical
identity, inlining included, then the detail of one difference. It was
not prototyped and remains to be specified at implementation time.

### What the prototype corrected, and that was visible only on screen

The first version of the chart was not a roofline: the memory diagonals
crossed the compute ceiling instead of stopping at the ridge. A roofline
is the envelope `min(compute peak, bandwidth x intensity)`, and the error
only appeared at render time.

A chart with fluid width carries its typography with it and becomes
disproportionate: it must be bounded to its natural size. Labels
necessarily cross lines in a log-log plane, and a halo in the background
colour keeps them readable without moving the line. As for the
Provenance, an `alert()` blocks the page; a drawer is the right answer,
and not only for technical reasons.
