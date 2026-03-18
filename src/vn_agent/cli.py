"""CLI entry point for VN-Agent."""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path

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

console = Console()


def setup_logging(verbose: bool = False) -> None:
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
) -> None:
    """Generate a visual novel from a theme."""
    setup_logging(verbose)

    console.print(f"\n[bold blue]VN-Agent[/bold blue] - AI Visual Novel Generator")
    console.print(f"Theme: [italic]{theme}[/italic]\n")

    asyncio.run(_generate_async(theme, output, text_only, max_scenes, num_characters))


async def _generate_async(
    theme: str,
    output: Path,
    text_only: bool,
    max_scenes: int = 10,
    num_characters: int = 3,
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
            console.print(f"\n[red]Error during generation: {e}[/red]")
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


if __name__ == "__main__":
    app()
