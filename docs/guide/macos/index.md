# macOS

nunatak runs on macOS, and the platform takes two things away: there is
no event-triggered sampling and no per-Hotspot counter event. What
remains is a time profile with call stacks, the machine code of the hot
loops, measured ceilings, and energy - which is enough to find where the
time goes and not enough to place a Hotspot on a roofline.

The recipe is the same one command as everywhere; what differs is what
comes back. The page after it says what temporal sampling can and cannot
answer, and why the missing pieces are named rather than approximated.

```{toctree}
:maxdepth: 1

profile-on-macos
what-temporal-sampling-can-say
```
