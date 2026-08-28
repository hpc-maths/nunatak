"""explain: generate or regenerate the Explanations of a Run.

Separated from `run` by necessity, not comfort: measurement executes in
a job, on compute nodes that generally have no network egress - this
verb is what runs from a login node afterwards. It reads the Run back,
rebuilds the prompts (a pure function of the pivot), obtains consent
when source would leave the machine, asks the model in parallel, and
writes the advice next to the pivot - never inside it. Regenerating is
a real operation: after a declined first attempt, a model change, or a
nunatak upgrade.
"""

from __future__ import annotations

from pathlib import Path

from nunatak import analysis, corpus
from nunatak.cli.report import most_recent_run
from nunatak.cli.run import project_name, repository_root
from nunatak.collect.execution import Executor, SubprocessExecutor
from nunatak.config import load
from nunatak.console import Console
from nunatak.exit_codes import FAILURE_BEFORE_LAUNCH
from nunatak.explain import consent, prompt, store
from nunatak.explain import pi as pi_tool
from nunatak.explain.generate import Failure, generate
from nunatak.pivot import Degradation, read_run


def attempt(run, diagnostics, directory, executor, config, console, cwd):
    """`run` tries the Explanation and never depends on it.

    Returns the named degradation when the attempt could not deliver,
    None otherwise - including when there is nothing to explain: a Run
    without an eligible Hotspot loses nothing, so no tool is probed and
    nothing is declared. Every degradation names the exact command to
    replay from a login node, because the usual reason to be here is a
    compute node with no network egress.
    """
    asked, _ = prompt.requests(run, diagnostics)
    if not asked:
        return None
    replay = f"nunatak explain {directory}"
    located = pi_tool.locate(executor, config)
    if located is None:
        return Degradation(
            name="explanation-unavailable",
            message="Node.js or pi not usable: no LLM explanations for this Run",
            remedy=f"run `{replay}` from a login node where pi is installed",
        )
    who = pi_tool.identity(executor)
    project = project_name(config, run.command, repository_root(executor, cwd))
    allowed, why = consent.obtain(who, project, console)
    if not allowed:
        return Degradation(
            name="explanation-withheld",
            message=why,
            remedy=f"run `{replay}` from a terminal to grant consent",
        )
    recipient = consent.recipient(who)
    console.info(
        f"asking {recipient} for {len(asked)} explanation(s), in parallel; "
        "tens of seconds per Hotspot"
    )

    on_token = console.live if console.is_terminal and len(asked) == 1 else None

    def progress(outcome):
        """One line per completed call; the streamed text is its own."""
        if on_token is not None:
            console.live_done()
        if isinstance(outcome, Failure):
            console.error(f"{outcome.hotspot.display_name}: {outcome.error}")
        elif on_token is None:
            console.info(f"{outcome.hotspot.display_name}: advice received")

    explanations, failures = generate(
        executor, located, asked, on_done=progress, on_token=on_token
    )
    if not explanations:
        first = failures[0].error if failures else "no answer"
        return Degradation(
            name="explanation-unavailable",
            message=f"the model could not be reached: {first}",
            remedy=f"run `{replay}` from a login node",
        )
    console.info(f"Explanations: {store.write(directory, explanations)}")
    return None


def execute(args, console: Console) -> int:
    """`nunatak explain [<run>] [--model <pattern>]`. Returns 0 when the
    advice is written or legitimately withheld, 125 when nothing could
    be generated at all."""
    cwd = Path.cwd()
    config, _ = load(cwd)
    if args.run:
        directory = Path(args.run)
    else:
        runs_dir = Path(config.runs_dir)
        if not runs_dir.is_absolute():
            runs_dir = cwd / runs_dir
        found = most_recent_run(runs_dir)
        if found is None:
            console.error(f"no Run under {runs_dir}; run `nunatak run` first")
            return FAILURE_BEFORE_LAUNCH
        directory = found

    try:
        run = read_run(directory)
    except (ValueError, OSError) as error:
        console.error(str(error))
        return FAILURE_BEFORE_LAUNCH

    if args.replay is not None:
        executor: Executor = corpus.ReplayExecutor(Path(args.replay))
    elif args.record:
        executor = corpus.RecordingExecutor(SubprocessExecutor(), Path(args.record))
    else:
        executor = SubprocessExecutor()

    located = pi_tool.locate(executor, config)
    if located is None:
        path = config.tools.get("pi", "pi")
        console.error(
            f"Node.js or pi not usable at '{path}': install pi "
            "(npm install -g @earendil-works/pi-coding-agent) "
            "or set tools.pi in nunatak.toml"
        )
        return FAILURE_BEFORE_LAUNCH

    asked, withheld = prompt.requests(run, analysis.diagnose(run))
    for entry in withheld:
        console.info(
            f"withheld: {entry.hotspot.display_name} - {entry.reason}"
        )
    if not asked:
        console.info("no Hotspot is eligible for an explanation in this Run")
        return 0

    who = pi_tool.identity(executor, model_flag=args.model)
    project = project_name(config, run.command, repository_root(executor, cwd))
    allowed, why = consent.obtain(
        who, project, console, model_flag=args.model
    )
    if not allowed:
        console.warning(f"explanations withheld: {why}")
        return 0

    recipient = consent.recipient(who, args.model)
    console.info(
        f"asking {recipient} for {len(asked)} explanation(s), in parallel; "
        "tens of seconds per Hotspot"
    )

    # One request on a terminal streams the answer as the model writes
    # it; several run in parallel, whose interleaving would be soup.
    on_token = console.live if console.is_terminal and len(asked) == 1 else None

    def progress(outcome):
        """One line per completed call; the streamed text is its own."""
        if on_token is not None:
            console.live_done()
        if isinstance(outcome, Failure):
            console.error(f"{outcome.hotspot.display_name}: {outcome.error}")
        elif on_token is None:
            console.info(f"{outcome.hotspot.display_name}: advice received")

    explanations, failures = generate(
        executor, located, asked, model=args.model, on_done=progress,
        on_token=on_token,
    )

    if args.record:
        corpus.write_meta(
            Path(args.record),
            ["explain", *(["--model", args.model] if args.model else [])],
            [{"tool": "pi", "version": located.version}],
        )

    if not explanations:
        console.error("no explanation was generated; the errors above say why")
        return FAILURE_BEFORE_LAUNCH
    path = store.write(directory, explanations)
    console.info(f"Explanations: {path}")
    console.info(
        f"regenerate the report to include them: nunatak report {directory}"
    )
    return 0
