# Kernel permissions

Profiling reads hardware counters, and the kernel decides who may. On a
machine your users do not administer, that decision is yours.

## What nunatak needs

[`perf`](https://perfwiki.github.io/main/) needs
`kernel.perf_event_paranoid` at 2 or below. That is the whole
requirement.

| Level | What nunatak can do |
|---|---|
| 3 and above | nothing. `perf_event_open` is denied even on the user's own processes, and every run declares `cpu-collection-unavailable` |
| 2 | everything nunatak needs: samples, hardware counters, call stacks, all in user space |
| 1, 0, -1 | more than nunatak asks for |

Ubuntu ships 4. Debian ships 3 on some kernels. Both forbid a user from
profiling their own program, which is why a fresh cluster image usually
measures nothing until this is set.

```sh
sysctl kernel.perf_event_paranoid          # read it
sysctl -w kernel.perf_event_paranoid=2     # until reboot
echo 'kernel.perf_event_paranoid = 2' > /etc/sysctl.d/60-perf.conf   # persistent
```

The kernel documents this setting in three places that contradict one
another, and the perf wiki in a fourth that is inverted with respect to
them. The table above is nunatak's own reading, and the only claim it
makes is about nunatak.

## Without lowering it globally

`CAP_PERFMON` on the perf binary grants the same access to whoever runs
it, without changing the machine's default:

```sh
setcap cap_perfmon,cap_sys_ptrace,cap_syslog+ep $(which perf)
```

Prefer this where a shared machine's default must stay strict. nunatak
does not care which of the two answers: `nunatak doctor` reports the
level it found and whether sampling actually works, having tried it
rather than deduced it.

## What nunatak does not need

`kernel.kptr_restrict` can stay as it is. It hides kernel symbol
addresses, and nunatak leaves kernel samples unresolved by design: an
address it cannot attribute to a physical function is displayed as
`module+0x...` rather than named after a neighbour. Relaxing it would
change nothing about a nunatak profile.

## What scales with the number of ranks

An MPI run samples inside the ranks, so its demand on the kernel grows
with them. Three limits are worth knowing before a large job fails with
a resource error rather than a permission one:

| Limit | Why it grows |
|---|---|
| `kernel.perf_event_mlock_kb` | each sampling rank locks a ring buffer |
| `ulimit -l` | the same memory, counted against the user's locked-memory limit |
| open file descriptors | one per event per rank |

Above `sampling.rank_threshold` ranks (64 by default) nunatak samples
rank 0 plus the first rank of each node, so the demand stops growing
with the job. Below it, every rank samples, and a 128-way run on one node
opens 128 sampling sessions.

## If you are not the administrator

`doctor` prints the level it found and the remedy in the same line, so
the request to your support team writes itself:

```
missing  cpu-collector  perf 6.8 found, but kernel.perf_event_paranoid=4
                        forbids unprivileged profiling
                        -> ask for kernel.perf_event_paranoid<=2 or the
                           CAP_PERFMON capability
```

The run proceeds meanwhile, and the Run carries the degradation by name.
