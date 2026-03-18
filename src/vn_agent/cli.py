"""CLI entry point for VN-Agent."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

import sys
import typer
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.logging import RichHandler

from vn_agent.agents.state import initial_state
from vn_agent.agents.graph import create_pipeline
from vn_agent.compiler.project_builder import build_project

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
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
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
) -> None:
    """Generate a visual novel from a theme."""
    setup_logging(verbose)

    console.print(f"\n[bold blue]VN-Agent[/bold blue] - AI Visual Novel Generator")
    console.print(f"Theme: [italic]{theme}[/italic]\n")

    script_checkpoint = output / "vn_script.json"
    if resume and script_checkpoint.exists():
        asyncio.run(_resume_async(output, text_only))
    else:
        asyncio.run(_generate_async(theme, output, text_only, max_scenes, num_characters, verbose))


async def _generate_async(
    theme: str,
    output: Path,
    text_only: bool,
    max_scenes: int = 10,
    num_characters: int = 3,
    verbose: bool = False,
) -> None:
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
            console.print(f"\n[red]Error during generation: {e}[/red]")
            if verbose:
                console.print(traceback.format_exc())
            raise typer.Exit(1)

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

    # Summary
    console.print(f"\n[green]✓ Generation complete![/green]")
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
    from vn_agent.schema.script import VNScript
    from vn_agent.schema.character import CharacterProfile

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
        console.print(f"\n[green]✓ Resume complete (text-only)![/green]")
        console.print(f"  Title: [bold]{script.title}[/bold]")
        console.print(f"  Scenes: {len(script.scenes)}")
        console.print(f"  Characters: {len(characters)}")
        console.print(f"  Output: {output.resolve()}")
        return

    from vn_agent.agents.character_designer import run_character_designer
    from vn_agent.agents.scene_artist import run_scene_artist
    from vn_agent.agents.music_director import run_music_director

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
            state.update(await run_character_designer(state))

            progress.update(task, description="Scene Artist: Generating backgrounds...")
            state.update(await run_scene_artist(state))

            progress.update(task, description="Music Director: Assigning BGM...")
            state.update(await run_music_director(state))
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

    console.print(f"\n[green]✓ Resume complete![/green]")
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
    from vn_agent.schema.script import VNScript
    from vn_agent.agents.reviewer import _structural_check

    try:
        script = VNScript.model_validate_json(script_path.read_text(encoding="utf-8"))
        result = _structural_check(script)
        if result.passed:
            console.print(f"[green]✓ Script is valid[/green]")
        else:
            console.print(f"[red]✗ Validation failed:[/red]")
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
) -> None:
    """Preview what would be generated without calling any APIs."""
    import os
    from rich.table import Table
    from vn_agent.config import get_settings

    settings = get_settings()

    # Check API key availability
    provider = settings.llm_provider
    if provider == "anthropic":
        api_key_present = bool(
            settings.anthropic_api_key or os.environ.get("ANTHROPIC_API_KEY", "")
        )
        api_key_label = "ANTHROPIC_API_KEY"
    else:
        api_key_present = bool(
            settings.openai_api_key or os.environ.get("OPENAI_API_KEY", "")
        )
        api_key_label = "OPENAI_API_KEY"

    image_enabled = not text_only and provider == "openai"

    # Estimated API calls: director + writer*scenes + reviewer + (char_designer + scene_artist if not text_only)
    estimated_llm_calls = 1 + max_scenes + 1  # director, writer per scene, reviewer
    if not text_only:
        estimated_llm_calls += num_characters  # character designer
        estimated_llm_calls += max_scenes  # scene artist

    table = Table(title="VN-Agent Dry Run Preview", show_header=True, header_style="bold magenta")
    table.add_column("Setting", style="cyan", no_wrap=True)
    table.add_column("Value", style="white")

    table.add_row("Theme", theme[:60] + ("..." if len(theme) > 60 else ""))
    table.add_row("Provider", f"{provider}")
    table.add_row("Model", settings.llm_model)
    table.add_row("Max Scenes", str(max_scenes))
    table.add_row("Characters", str(num_characters))
    table.add_row("Music Strategy", settings.music_strategy)
    table.add_row("Text-Only Mode", "Yes" if text_only else "No")
    table.add_row("Image Generation", "Disabled" if text_only else "Enabled")
    table.add_row("Estimated LLM Calls", str(estimated_llm_calls))
    table.add_row(
        api_key_label,
        "[green]set[/green]" if api_key_present else "[red]NOT SET[/red]",
    )

    console.print()
    console.print(table)

    console.print("\n[bold]What would happen:[/bold]")
    console.print(f"  [cyan]1.[/cyan] Director plans a story with up to {max_scenes} scenes and {num_characters} characters")
    console.print(f"  [cyan]2.[/cyan] Writer generates dialogue for each scene")
    console.print(f"  [cyan]3.[/cyan] Reviewer validates the script")
    if not text_only:
        console.print(f"  [cyan]4.[/cyan] Character Designer creates visual profiles for {num_characters} characters (parallel)")
        console.print(f"  [cyan]5.[/cyan] Scene Artist generates backgrounds for unique scenes (parallel)")
        console.print(f"  [cyan]6.[/cyan] Music Director assigns BGM tracks")
    else:
        console.print(f"  [cyan]4.[/cyan] Music Director assigns BGM tracks")
        console.print(f"  [dim](Image generation skipped — text-only mode)[/dim]")
    console.print(f"  [cyan]→[/cyan] Ren'Py project compiled to output directory\n")

    if not api_key_present:
        console.print(f"[yellow]Warning: {api_key_label} is not set. Generation will fail without it.[/yellow]")


@app.command()
def compile(
    script_path: Path = typer.Argument(..., help="Path to vn_script.json"),
    characters_path: Path = typer.Option(None, "--characters", help="Path to characters.json"),
    output: Path = typer.Option(Path("./vn_output"), "--output", "-o"),
) -> None:
    """Compile an existing VN script JSON to a Ren'Py project."""
    from vn_agent.schema.script import VNScript
    from vn_agent.schema.character import CharacterProfile
    import json

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
    console.print(f"[green]✓ Compiled to {output.resolve()}[/green]")


if __name__ == "__main__":
    app()
