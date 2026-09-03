# The three reading levels

A report answers three questions of different sizes: what is worth
looking at, how the Hotspots compare, and what is happening inside one
of them. Each level answers one of them, and the page never shows two of
them at once.

## The page is one file, and it stays one file

`report.html` carries its own style, its own script and all its data -
no CDN, no font, no request of any kind. It opens on a login node with
no server, travels in an email, and still reads in ten years out of an
archive. That is a product invariant rather than an optimisation, and it
is what lets this documentation publish a real one instead of a
screenshot.

## Synthesis, inventory, detail

The **synthesis** opens the page: how many Hotspots stand above the
statistical floor and what share of the time they hold, then one finding
per Hotspot in decreasing order, each with its verdict, the evidence
behind it, and the reasons for any downgrade. It closes on *what this
report does not say*.

The **inventory** lists every Hotspot above the floor, one row each,
sortable by any numeric column and filterable by regime, by estimated
Quality or by missing source. It is where Hotspots are compared to each
other, which the synthesis deliberately does not do.

The **detail** is one Hotspot: its roofline, its source annotated with
samples per line, the facts of its hot loop, and its advice. It
substitutes the inventory rather than opening beside it, since two levels
visible at once is two levels read badly, and the way back is explicit.

## The roofline is drawn for one Hotspot at a time

The chart lives at the third level, and it carries this Hotspot's point,
the machine's compute peak, its bandwidth diagonal, and the other
placeable Hotspots as pale points for scale. A roofline of everything at
once is a scatter plot: what the chart is for is the distance between one
measured rate and what the machine allows at that intensity, and that
distance is a statement about one Hotspot.

The geometry is checked rather than trusted - the memory diagonal stops
at the ridge point instead of crossing the peak, which is a unit-tested
invariant, because the prototype got it wrong in a way no code review
would have caught.

A Hotspot that cannot be placed says so where the chart was expected,
never as a blank:

```
main cannot be placed on the roofline: no flops_dp raw counter in this Run.
```

## Two registers, two channels

Quality is a colour and a shape; the resolution level is neutral text.
They are never encoded the same way, because they answer different
questions - one about a number's uncertainty, the other about a Hotspot's
identity - and a reader who confuses them looks for a counter problem
where a name failed. The
[keystone page](../reading-what-nunatak-tells-you.md) has the four
registers side by side.

An estimated value carries its reason with it, in the finding and in the
detail. An empty cell means the quantity is unavailable for that Hotspot,
not that it is zero, and the inventory says exactly that under its last
row: a table of numbers with holes in it is read as zeros by anyone not
warned.

## The absences are part of the report

*What this report does not say* is a section, not a footnote. It names
the degradations of the Run - what was lost, and the way forward - along
with the share of time below the statistical floor and the share
attributed to no name at all.

The advice panel does the same at the third level. Where no model
answered, the panel says so and says what to run:

```
No advice generated for this Run. Generate it with nunatak explain from a
machine with network access, then regenerate this report.
```

## Which Run are you reading

The header names the Run, the command and the machine, and a drawer
unfolds the rest: the code state, the collectors with their versions, the
observed dependencies, and the effective configuration, meaning the
thresholds that actually applied. Never a dialog, never in the main
view.

That drawer is where "a recorded variation is no longer a hidden
variation" becomes something you can click. A threshold can be tuned; it
cannot be tuned silently.

## The comparison page reads the same way

`compare.html` has the same three levels. The synthesis is the total
sampled time before and after, the change, whether it clears the sampling
error, and a one-line census - `1 improved · 1 regressed · 0 unchanged
within their error · 1 appeared or vanished`. The inventory is one row
per logical function, inlining included, with each side's time, the
change and the verdict; functions below 1% of both Runs are folded away,
and the page says so, because inlining makes symbols come and go.

The detail substitutes the table the same way, and it is where the
verdict stops being an adjective:

```
The difference (0.292 s) exceeds the combined sampling error of its two
sides (±0.0792 s): significant.
```

Each side shows its own sample count and its own error, so a reader can
see that "significant" is arithmetic rather than opinion. A reader who
knows how to read a report knows how to read this.
