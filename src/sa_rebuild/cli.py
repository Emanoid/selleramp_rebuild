"""Typer CLI: run | resume | status | cache."""
from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table

from . import state as state_mod
from .cache import Cache
from .config import AppConfig
from .csv_io import read_input
from .logging_setup import setup as setup_logging
from .paths import cache_dir, output_dir
from .runner import iter_process

app = typer.Typer(add_completion=False, help="SellerAmp-style FBA sourcing calculator (Keepa).")
console = Console()


def _process(
    cfg: AppConfig,
    rs: state_mod.RunState,
    inputs_by_row_id: dict,
    include_descriptions: bool,
    variations_fetch_max: int,
) -> int:
    setup_logging("INFO")
    for ev in iter_process(
        cfg, rs, inputs_by_row_id,
        include_descriptions=include_descriptions,
        variations_fetch_max=variations_fetch_max,
    ):
        if ev.kind == "row_done":
            console.log(
                f"[{ev.rows_done}/{ev.rows_total}] {ev.last_message} | tokens~{ev.tokens_left}"
            )
        elif ev.kind == "row_error":
            console.log(f"[red]error[/red] {ev.last_message}")
        elif ev.kind == "paused":
            console.print(f"[yellow]{ev.last_message}[/yellow]")
            console.print("Resume with: [bold]sa-rebuild resume[/bold]")
            return 0
        elif ev.kind == "finished":
            console.print(f"[green]{ev.last_message}[/green]")
    return 0


@app.command()
def run(
    input: Path = typer.Option(..., "--input", "-i", exists=True, readable=True),
    output: Path = typer.Option(None, "--output", "-o"),
    config: Path = typer.Option("config.yaml", "--config", "-c"),
    variations: int = typer.Option(
        None, "--variations",
        help="Fetch up to N sibling ASINs per variation parent for viable_variations + parent_monthly_sales. Costs ~7 tokens per sibling. Overrides config.",
    ),
    descriptions: bool = typer.Option(
        True, "--descriptions/--no-descriptions",
        help="Include the column-help row as the second line of the report CSV.",
    ),
):
    """Process an input CSV start-to-finish."""
    cfg = AppConfig.load(config)
    if not cfg.keepa_api_key:
        console.print("[red]KEEPA_API_KEY missing.[/red] Set it in .env or environment.")
        raise typer.Exit(2)

    if output is None:
        ts = time.strftime("%Y%m%dT%H%M%S")
        output = output_dir() / f"report_{ts}.csv"

    rows = read_input(input)
    if not rows:
        console.print("[red]No usable rows in input CSV.[/red]")
        raise typer.Exit(2)

    var_max = variations if variations is not None else cfg.variations.fetch_max

    rs = state_mod.RunState.new(
        input_csv=str(input),
        output_csv=str(output),
        row_ids=[r.row_id for r in rows],
        config_path=str(config),
    )
    state_mod.save(rs)
    inputs_by_row_id = {r.row_id: r for r in rows}
    console.print(
        f"Run id: [bold]{rs.run_id}[/bold] | rows: {rs.rows_total} | "
        f"variations: {var_max} | output: {output}"
    )
    sys.exit(_process(cfg, rs, inputs_by_row_id, descriptions, var_max))


@app.command()
def resume(
    run_id: Optional[str] = typer.Option(None, "--run-id"),
    config: Optional[Path] = typer.Option(None, "--config", "-c"),
    variations: int = typer.Option(None, "--variations"),
    descriptions: bool = typer.Option(True, "--descriptions/--no-descriptions"),
):
    """Resume the last (or named) run."""
    rs = state_mod.load(run_id) if run_id else state_mod.load_last()
    if rs is None:
        console.print("[red]No prior run found.[/red]")
        raise typer.Exit(2)
    cfg_path = config or Path(rs.config_path or "config.yaml")
    cfg = AppConfig.load(cfg_path)
    if not cfg.keepa_api_key:
        console.print("[red]KEEPA_API_KEY missing.[/red]")
        raise typer.Exit(2)
    rows = read_input(rs.input_csv)
    inputs_by_row_id = {r.row_id: r for r in rows}
    var_max = variations if variations is not None else cfg.variations.fetch_max
    console.print(
        f"Resuming run [bold]{rs.run_id}[/bold] — "
        f"{rs.rows_done}/{rs.rows_total} done, {len(rs.remaining_row_ids)} remaining"
    )
    sys.exit(_process(cfg, rs, inputs_by_row_id, descriptions, var_max))


@app.command()
def status():
    """Show last-run progress."""
    rs = state_mod.load_last()
    if rs is None:
        console.print("No prior run.")
        return
    table = Table(title=f"Last run: {rs.run_id}")
    table.add_column("field")
    table.add_column("value")
    table.add_row("started_at", rs.started_at)
    table.add_row("last_updated_at", rs.last_updated_at)
    table.add_row("input_csv", rs.input_csv)
    table.add_row("output_csv", rs.output_csv)
    table.add_row("rows_done", f"{rs.rows_done}/{rs.rows_total}")
    table.add_row("rows_remaining", str(len(rs.remaining_row_ids)))
    table.add_row("tokens_left_snapshot", str(rs.tokens_left_snapshot))
    table.add_row("errors", str(len(rs.errors)))
    console.print(table)


cache_app = typer.Typer(help="Manage on-disk Keepa response cache.")
app.add_typer(cache_app, name="cache")


@cache_app.command("clear")
def cache_clear(older_than_hours: int = typer.Option(0, "--older-than-hours")):
    """Clear cache entries older than N hours (default: all expired)."""
    cache = Cache(cache_dir() / "keepa.sqlite")
    removed = cache.clear_older_than(older_than_hours * 3600)
    cache.close()
    console.print(f"Removed {removed} cache entries.")


if __name__ == "__main__":
    app()
