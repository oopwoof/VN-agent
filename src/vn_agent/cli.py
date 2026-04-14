"""CLI entry point for VN-Agent."""
from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.progress import Progress, SpinnerColumn, TextColumn

from vn_agent.agents.graph import create_pipeline
from vn_agent.agents.state import initial_state
from vn_agent.compiler.project_builder import build_project

_mock_patches: list = []


def _patch_mock_llm() -> None:
    """Replace ainvoke_llm in all agent modules with the canned mock."""
    from unittest.mock import patch

    from vn_agent.services.mock_llm import mock_ainvoke

    targets = [
        "vn_agent.agents.director.ainvoke_llm",
        "vn_agent.agents.writer.ainvoke_llm",
        "vn_agent.agents.reviewer.ainvoke_llm",
        "vn_agent.agents.structure_reviewer.ainvoke_llm",
        "vn_agent.agents.state_orchestrator.ainvoke_llm",
        "vn_agent.agents.summarizer.ainvoke_llm",
        "vn_agent.agents.character_designer.ainvoke_llm",
        "vn_agent.agents.scene_artist.ainvoke_llm",
    ]
    for target in targets:
        p = patch(target, side_effect=mock_ainvoke)
        p.start()
        _mock_patches.append(p)


def _unpatch_mock_llm() -> None:
    for p in _mock_patches:
        p.stop()
    _mock_patches.clear()

app = typer.Typer(
    name="vn-agent",
    help="Multi-agent AI visual novel generator",
    add_completion=False,
)

console = Console(highlight=False)


def setup_logging(verbose: bool = False) -> None:
    # Ensure UTF-8 output on Windows (non-destructive reconfigure)
    if sys.platform == "win32":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")  # type: ignore[union-attr]
        except AttributeError:
            pass  # not available in all environments (e.g. pytest capture)
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )


@app.command()
def generate(
    theme: str = typer.Argument(..., help="Story theme or premise"),
    output: Path = typer.Option(
        Path("./vn_output"),
        "--output", "-o",
        help="Output directory for the Ren'Py project",
    ),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Verbose logging"),
    text_only: bool = typer.Option(
        False,
        "--text-only",
        help="Skip image and music generation (text pipeline only)",
    ),
    max_scenes: int = typer.Option(10, "--max-scenes", help="Maximum number of scenes"),
    num_characters: int = typer.Option(3, "--characters", help="Number of characters"),
    resume: bool = typer.Option(False, "--resume", help="Resume from existing output directory"),
    mock: bool = typer.Option(
        False, "--mock",
        help="Use canned fixture responses (no API calls). For pipeline testing / offline dev.",
    ),
    stream: bool = typer.Option(
        False, "--stream",
        help="Stream LLM tokens to console in real-time.",
    ),
) -> None:
    """Generate a visual novel from a theme."""
    setup_logging(verbose)

    console.print("\n[bold blue]VN-Agent[/bold blue] - AI Visual Novel Generator")
    console.print(f"Theme: [italic]{theme}[/italic]\n")

    if mock:
        console.print("[dim]Mock mode: using fixture data, no API calls.[/dim]\n")
    if stream:
        console.print("[dim]Streaming mode: LLM tokens will display in real-time.[/dim]\n")

    script_checkpoint = output / "vn_script.json"
    if resume and script_checkpoint.exists():
        asyncio.run(_resume_async(output, text_only))
    else:
        asyncio.run(
            _generate_async(
                theme, output, text_only, max_scenes, num_characters,
                verbose, mock=mock, stream=stream,
            )
        )


async def _generate_async(
    theme: str,
    output: Path,
    text_only: bool,
    max_scenes: int = 10,
    num_characters: int = 3,
    verbose: bool = False,
    mock: bool = False,
    stream: bool = False,
) -> None:
    if mock:
        _patch_mock_llm()

    from vn_agent.observability.tracing import reset_trace
    trace = reset_trace()

    pipeline = create_pipeline()
    state = initial_state(
        theme=theme,
        output_dir=str(output),
        text_only=text_only,
        max_scenes=max_scenes,
        num_characters=num_characters,
    )

    step_labels = {
        "director": "Director: Planning story...",
        "writer": "Writer: Writing dialogue...",
        "reviewer": "Reviewer: Checking script...",
        "character_designer": "Character Designer: Creating characters...",
        "scene_artist": "Scene Artist: Generating backgrounds...",
        "music_director": "Music Director: Assigning BGM...",
    }

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Generating...", total=None)

        try:
            final_state = {}
            async for update in pipeline.astream(state, stream_mode="updates"):
                for node_name, output_chunk in update.items():
                    if node_name != "__end__":
                        label = step_labels.get(node_name, f"[{node_name}]...")
                        progress.update(task, description=label)
                    if isinstance(output_chunk, dict):
                        final_state.update(output_chunk)
        except Exception as e:
            import traceback
            _unpatch_mock_llm()
            console.print(f"\n[red]Error during generation: {e}[/red]")
            if verbose:
                console.print(traceback.format_exc())
            raise typer.Exit(1)

    _unpatch_mock_llm()
    script = final_state.get("vn_script")
    characters = final_state.get("characters", {})
    errors = final_state.get("errors", [])

    if errors:
        console.print("\n[yellow]Warnings:[/yellow]")
        for err in errors:
            console.print(f"  - {err}")

    if not script:
        console.print("[red]Generation failed: no script produced[/red]")
        raise typer.Exit(1)

    # Build Ren'Py project
    output.mkdir(parents=True, exist_ok=True)
    build_project(script, characters, output)

    # Token usage summary
    from vn_agent.services.token_tracker import tracker
    if tracker.calls:
        console.print(f"\n[dim]{tracker.summary()}[/dim]")

    # Trace summary + persist
    console.print(f"\n[dim]{trace.summary()}[/dim]")
    try:
        trace_path = trace.save(output)
        console.print(f"[dim]Trace saved to {trace_path}[/dim]")
    except Exception:
        pass

    # Summary
    console.print("\n[green][OK] Generation complete![/green]")
    console.print(f"  Title: [bold]{script.title}[/bold]")
    console.print(f"  Scenes: {len(script.scenes)}")
    console.print(f"  Characters: {len(characters)}")
    console.print(f"  Output: {output.resolve()}")
    console.print(f"\nRun with Ren'Py: [italic]renpy {output.resolve()}[/italic]\n")


async def _resume_async(
    output: Path,
    text_only: bool,
) -> None:
    """Resume generation from existing vn_script.json checkpoint."""
    import json

    from vn_agent.schema.character import CharacterProfile
    from vn_agent.schema.script import VNScript

    script_path = output / "vn_script.json"
    chars_path = output / "characters.json"

    try:
        script = VNScript.model_validate_json(script_path.read_text(encoding="utf-8"))
    except Exception as e:
        console.print(f"[red]Error loading checkpoint script: {e}[/red]")
        raise typer.Exit(1)

    characters: dict[str, CharacterProfile] = {}
    if chars_path.exists():
        try:
            raw = json.loads(chars_path.read_text(encoding="utf-8"))
            characters = {k: CharacterProfile.model_validate(v) for k, v in raw.items()}
        except Exception as e:
            console.print(f"[yellow]Warning: could not load characters checkpoint: {e}[/yellow]")

    console.print(f"Resuming from existing script: [bold]{script.title}[/bold]")

    if text_only:
        output.mkdir(parents=True, exist_ok=True)
        build_project(script, characters, output)
        console.print("\n[green][OK] Resume complete (text-only)![/green]")
        console.print(f"  Title: [bold]{script.title}[/bold]")
        console.print(f"  Scenes: {len(script.scenes)}")
        console.print(f"  Characters: {len(characters)}")
        console.print(f"  Output: {output.resolve()}")
        return

    from vn_agent.agents.character_designer import run_character_designer
    from vn_agent.agents.music_director import run_music_director
    from vn_agent.agents.scene_artist import run_scene_artist

    state: dict = {
        "vn_script": script,
        "characters": characters,
        "output_dir": str(output),
        "errors": [],
        "text_only": text_only,
    }

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console,
    ) as progress:
        task = progress.add_task("Resuming...", total=None)

        try:
            progress.update(task, description="Character Designer: Creating characters...")
            state.update(await run_character_designer(state))  # type: ignore[arg-type]

            progress.update(task, description="Scene Artist: Generating backgrounds...")
            state.update(await run_scene_artist(state))  # type: ignore[arg-type]

            progress.update(task, description="Music Director: Assigning BGM...")
            state.update(await run_music_director(state))  # type: ignore[arg-type]
        except Exception as e:
            console.print(f"\n[red]Error during resume: {e}[/red]")
            raise typer.Exit(1)

    final_script = state.get("vn_script", script)
    final_characters = state.get("characters", characters)
    errors = state.get("errors", [])

    if errors:
        console.print("\n[yellow]Warnings:[/yellow]")
        for err in errors:
            console.print(f"  - {err}")

    output.mkdir(parents=True, exist_ok=True)
    build_project(final_script, final_characters, output)

    console.print("\n[green][OK] Resume complete![/green]")
    console.print(f"  Title: [bold]{final_script.title}[/bold]")
    console.print(f"  Scenes: {len(final_script.scenes)}")
    console.print(f"  Characters: {len(final_characters)}")
    console.print(f"  Output: {output.resolve()}")
    console.print(f"\nRun with Ren'Py: [italic]renpy {output.resolve()}[/italic]\n")


@app.command()
def validate(
    script_path: Path = typer.Argument(..., help="Path to vn_script.json"),
) -> None:
    """Validate an existing VN script JSON file."""
    from vn_agent.agents.reviewer import _structural_check
    from vn_agent.schema.script import VNScript

    try:
        script = VNScript.model_validate_json(script_path.read_text(encoding="utf-8"))
        result = _structural_check(script)
        if result.passed:
            console.print("[green][OK] Script is valid[/green]")
        else:
            console.print("[red][X] Validation failed:[/red]")
            console.print(result.feedback)
            raise typer.Exit(1)
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")
        raise typer.Exit(1)


@app.command("dry-run")
def dry_run(
    theme: str = typer.Argument(..., help="Story theme or premise"),
    max_scenes: int = typer.Option(10, "--max-scenes"),
    num_characters: int = typer.Option(3, "--characters"),
    text_only: bool = typer.Option(False, "--text-only"),
    ping: bool = typer.Option(False, "--ping", help="Send a tiny probe call to verify API keys work"),
    output: Path = typer.Option(Path("./vn_output"), "--output", "-o"),
) -> None:
    """Preview what would be generated. Checks keys + estimates cost.

    With --ping, actually sends ≤$0.001 probe calls to verify credentials.
    Without --ping, purely offline: no API calls, no charges.
    """
    import asyncio

    from rich.table import Table

    from vn_agent.config import get_settings
    from vn_agent.services.preflight import check_readiness

    settings = get_settings()
    report = asyncio.run(check_readiness(
        settings,
        max_scenes=max_scenes,
        num_characters=num_characters,
        text_only=text_only,
        output_dir=output,
        ping=ping,
    ))

    # Main config table
    table = Table(title="VN-Agent Dry Run Preview", show_header=True, header_style="bold magenta")
    table.add_column("Setting", style="cyan", no_wrap=True)
    table.add_column("Value", style="white")
    table.add_row("Theme", theme[:60] + ("..." if len(theme) > 60 else ""))
    table.add_row("LLM Provider", settings.llm_provider)
    table.add_row("Director model", settings.llm_director_model)
    table.add_row("Writer model", settings.llm_writer_model)
    table.add_row("Reviewer model", settings.llm_reviewer_model)
    table.add_row("Max Scenes", str(max_scenes))
    table.add_row("Characters", str(num_characters))
    table.add_row("Text-Only Mode", "Yes" if text_only else "No")
    if not text_only:
        table.add_row("Image Provider", settings.image_provider)
        table.add_row("Image Model", settings.image_model)
    table.add_row("Output Dir", str(output))
    table.add_row("Estimated LLM Calls", str(report.estimated_llm_calls))
    if report.estimated_images:
        table.add_row("Estimated Images", str(report.estimated_images))
    console.print()
    console.print(table)

    # Cost breakdown table
    cost_table = Table(title="Cost Estimate (USD)", show_header=True, header_style="bold yellow")
    cost_table.add_column("Category", style="cyan")
    cost_table.add_column("Amount", style="white", justify="right")
    for label, amount in report.cost_breakdown.items():
        cost_table.add_row(label, f"${amount:.3f}")
    cost_table.add_row("[bold]Total[/bold]", f"[bold]${report.cost_estimate_usd:.3f}[/bold]")
    console.print()
    console.print(cost_table)

    # Status — ASCII only so legacy Windows GBK terminals don't crash
    console.print()
    if report.passed:
        console.print("[green][OK] Pre-flight: all checks passed[/green]")
    else:
        console.print("[red][X] Pre-flight: NOT READY[/red]")
    for err in report.errors:
        console.print(f"  [red]- {err}[/red]")
    for warn in report.warnings:
        console.print(f"  [yellow]- {warn}[/yellow]")
    console.print()


@app.command()
def compile(
    script_path: Path = typer.Argument(..., help="Path to vn_script.json"),
    characters_path: Path = typer.Option(None, "--characters", help="Path to characters.json"),
    output: Path = typer.Option(Path("./vn_output"), "--output", "-o"),
) -> None:
    """Compile an existing VN script JSON to a Ren'Py project."""
    import json

    from vn_agent.schema.character import CharacterProfile
    from vn_agent.schema.script import VNScript

    try:
        script = VNScript.model_validate_json(script_path.read_text(encoding="utf-8"))
    except Exception as e:
        console.print(f"[red]Error loading script: {e}[/red]")
        raise typer.Exit(1)

    characters: dict[str, CharacterProfile] = {}
    if characters_path and characters_path.exists():
        try:
            raw = json.loads(characters_path.read_text(encoding="utf-8"))
            characters = {k: CharacterProfile.model_validate(v) for k, v in raw.items()}
        except Exception as e:
            console.print(f"[yellow]Warning: could not load characters file: {e}[/yellow]")

    output.mkdir(parents=True, exist_ok=True)
    build_project(script, characters, output)
    console.print(f"[green][OK] Compiled to {output.resolve()}[/green]")


@app.command()
def regen(
    scene_id: str = typer.Argument(..., help="Scene id to regenerate (e.g. ch3_the_ascent)"),
    output: Path = typer.Option(..., "--output", "-o", help="Run directory with vn_script.json"),
    feedback: str = typer.Option("", "--feedback", "-f", help="Optional revision feedback"),
    recompile: bool = typer.Option(True, "--recompile/--no-recompile", help="Rebuild Ren'Py project after regen"),
) -> None:
    """Sprint 12-4: rewrite a single scene without re-running the pipeline.

    Loads vn_script.json from the run directory, walks state_writes up
    to the target scene to rebuild world_state, runs Writer just for
    that scene, persists the update, and (by default) recompiles the
    Ren'Py project so the change is visible without a separate step.
    """
    import asyncio as _asyncio

    from vn_agent.agents.local_regen import RegenError, regenerate_scene

    try:
        summary = _asyncio.run(regenerate_scene(output, scene_id, feedback))
    except RegenError as e:
        console.print(f"[red]Regen failed: {e}[/red]")
        raise typer.Exit(1)

    console.print(f"[green][OK] Regenerated scene '{scene_id}'[/green]")
    console.print(f"  Dialogue lines: {summary['old_dialogue_count']} → {summary['new_dialogue_count']}")
    console.print(f"  Wall time: {summary['wall_seconds']}s")
    if summary["state_writes_changed"]:
        console.print(
            "  [yellow]! state_writes changed — downstream scenes may "
            "be inconsistent. Consider regenerating them too.[/yellow]"
        )

    if recompile:
        import json as _json
        script_path = output / "vn_script.json"
        chars_path = output / "characters.json"
        from vn_agent.schema.character import CharacterProfile as _CP
        from vn_agent.schema.script import VNScript as _VN
        script = _VN.model_validate_json(script_path.read_text(encoding="utf-8"))
        characters: dict = {}
        if chars_path.exists():
            raw = _json.loads(chars_path.read_text(encoding="utf-8"))
            characters = {k: _CP.model_validate(v) for k, v in raw.items()}
        build_project(script, characters, output)
        console.print(f"[dim]Ren'Py rebuilt at {output}[/dim]")


eval_app = typer.Typer(help="Evaluation commands")
app.add_typer(eval_app, name="eval")


@eval_app.command("strategy")
def eval_strategy(
    corpus: Path = typer.Option(..., "--corpus", help="Path to final_annotations.csv"),
    sample: int = typer.Option(50, "--sample", help="Number of samples to evaluate (0=all)"),
    mock: bool = typer.Option(False, "--mock", help="Use keyword baseline instead of LLM"),
) -> None:
    """Evaluate strategy classification accuracy against COLX_523 corpus."""
    from vn_agent.eval.corpus import load_corpus
    from vn_agent.eval.strategy_eval import (
        evaluate_strategy_classification,
        format_report,
        keyword_classifier,
    )

    setup_logging()

    if not corpus.exists():
        console.print(f"[red]Corpus file not found: {corpus}[/red]")
        raise typer.Exit(1)

    sessions = load_corpus(corpus)
    console.print(f"Loaded {len(sessions)} sessions from corpus")

    if mock:

        async def classifier(text: str) -> str:
            return keyword_classifier(text)
    else:
        from vn_agent.config import get_settings
        from vn_agent.services.llm import ainvoke_llm

        settings = get_settings()

        async def classifier(text: str) -> str:
            response = await ainvoke_llm(
                "You are a narrative strategy classifier. Given a VN dialogue, "
                "classify its predominant narrative strategy as one of: "
                "accumulate, erode, rupture, reveal, contrast, weave. "
                "Respond with ONLY the strategy name.",
                text,
                model=settings.llm_reviewer_model,
                caller="eval/strategy",
            )
            content = response.content if hasattr(response, "content") else str(response)
            return content.strip().lower()

    metrics = asyncio.run(
        evaluate_strategy_classification(sessions, classifier, sample_size=sample)
    )

    console.print(f"\n{format_report(metrics)}")

    # Save results
    import json

    results_path = Path("eval_strategy_results.json")
    results_path.write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding="utf-8")
    console.print(f"\n[dim]Results saved to {results_path}[/dim]")


@eval_app.command("summary")
def eval_summary() -> None:
    """Display the most recent evaluation results."""
    import json

    results_path = Path("eval_strategy_results.json")
    if not results_path.exists():
        console.print("[yellow]No evaluation results found. Run 'vn-agent eval strategy' first.[/yellow]")
        raise typer.Exit(1)

    metrics = json.loads(results_path.read_text(encoding="utf-8"))
    from vn_agent.eval.strategy_eval import format_report

    console.print(f"\n{format_report(metrics)}")


if __name__ == "__main__":
    app()
