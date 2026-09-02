# Profile a job on a scheduler

A profiled job is the job you already submit with `nunatak run --` in
front of its launch line. What moves is the preparation: the login node
has the compilers and the route out, the compute nodes have the counters,
and three of the steps below belong on one side of that line rather than
the other.

## Prepare on the login node

`doctor` builds the two pieces a run refuses to build - the network probe
and mpiP, against the site's own MPI - and caches both per stack:

```sh
nunatak doctor
```

A `missing` row names what the job will lack instead of failing.
[The site's MPI stack](../../deployment/mpi-stack.md) is where those two
pieces are provided, and the
[degradation catalogue](../../reference/degradations.md) says what each
name costs.

Answer the consent question here too, if the run is to explain itself: a
batch job has no terminal to be asked on, and no answer is inferred for
it. [Get advice on your
Hotspots](../explanations/get-advice-on-your-hotspots.md) has the
exchange.

## Write the Runs where you can read them back

A Run is one self-sufficient directory. Under a job's working directory
it is one `scp` from the login node; under `$SCRATCH` it is already
there:

```toml
# nunatak.toml, beside the application
runs_dir = "/scratch/me/runs"
```

`-o <dir>` overrides that per run, for a job that wants its own id in the
path.

## The job script

The launch line is the only line that changes:

```sh
#!/bin/bash
#SBATCH --job-name=solver-profile
#SBATCH --nodes=2
#SBATCH --ntasks-per-node=64
#SBATCH --time=00:20:00
#SBATCH --output=solver-profile-%j.log

module load openmpi/5.0.7
source /opt/nunatak/bin/activate

nunatak run --name solver-2n -- srun ./solver --input case.nml
```

`--name` is what makes the Run legible three weeks later: a directory
called `solver-2n-20260901-132849` says what it holds, a timestamp alone
does not. `srun` is recognised as a launcher, so both collection layers
run inside the ranks - every rank counts, and sampling narrows to rank 0
plus the first rank of each node beyond 64 ranks.
[Profile an MPI job](../mpi/profile-an-mpi-job.md) moves that threshold.

**Ask for the shape you profile.** Hardware plus allocation shape is what
identifies a Machine, so the ceilings measured by a two-node job are the
ones a two-node job reuses, and a single-node calibration is not the
envelope of the job above.

## Leave the calibration inside the allocation

The first run on an unknown Machine measures its ceilings before the
application launches, and the network probe goes out through the
allocation's own launcher. Inside the job is the only moment the node and
the interconnect are yours. Both results are cached, and no later Run on
that Machine pays for them again.

At the head of a large job that is up to 60 seconds of every reserved
core, so spend it in a small job of the same shape instead:

```sh
nunatak calibrate
```

`--no-calibrate` skips the calibration and the probe together: the Run
then keeps theoretical ceilings and has no memory-bandwidth ceiling at
all. [Calibrate the Machine](../machine/calibrate-the-machine.md) is the
subject.

## Read the job log

nunatak writes its own lines on stderr and leaves stdout to the
application, so `--output` and `--error` split the two if you want the
application's output alone. Outside a terminal there is no colour, no
progress bar and no line rewriting; every line carries an ISO timestamp
instead, and reads the same under `tail -f` and in a file reopened three
weeks later:

```
2026-09-01T13:28:47+02:00 call stacks: fp: frame pointers kept in 91% of prologues (206 probed across 28 modules)
2026-09-01T13:28:49+02:00 launching ranks (each one counting; sampling narrows to rank 0 plus one rank per node beyond 64 ranks): srun ./solver --input case.nml
```

Progress is announced at the steps that happen - the calibration, each
pass, the retrieval of every rank, the analysis - and never as a time
remaining, which nothing here can predict. The log then closes on the
summary, on the degradations again (their first announcement scrolled
past before the application started) and on the paths of the Run and of
its report.

## Explain from the login node afterwards

A compute node with no route out cannot reach the model, so the
explanation attempted at the end of the run fails by naming itself, with
the command to replay already in it:

```
degraded [explanation-unavailable]: Node.js or pi not usable: no LLM explanations for this Run - run `nunatak explain /scratch/me/runs/solver-2n-20260901-132849` from a login node where pi is installed
```

Replay it where pi is, then fold the advice into the page:

```sh
nunatak explain /scratch/me/runs/solver-2n-20260901-132849
nunatak report /scratch/me/runs/solver-2n-20260901-132849
```

## Chain the job's own work behind the profile

The application's exit code passes through, so the rest of the script
behaves as it did unprofiled:

```sh
nunatak run -- srun ./solver && ./post_process
```

`--strict` is what changes that: a named degradation then exits 121,
which is what [a CI wants](gate-performance-in-ci.md) and what a
production job does not.
