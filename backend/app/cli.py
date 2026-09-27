"""CLI: `tracker ingest`, `tracker rebuild`, `tracker pair`."""
from __future__ import annotations

import asyncio

import typer

from app.services.ingest import ingest_all

app_cli = typer.Typer(help="claude-tracker — ingest JSONL transcripts into SQLite cache.")


@app_cli.command()
def ingest(
    since_hours: int | None = typer.Option(
        None, "--since", help="Only files modified within this many hours."
    ),
    rebuild: bool = typer.Option(False, "--rebuild", help="Clear cache and re-ingest everything."),
) -> None:
    """Walk ~/.claude/projects/**/*.jsonl and upsert summaries + events."""
    result = asyncio.run(ingest_all(since_hours=since_hours, rebuild=rebuild))
    typer.echo(
        f"new={result['new']} updated={result['updated']} skipped={result['skipped']} "
        f"events={result['events']} in {result['elapsed_s']}s"
    )


@app_cli.command()
def rebuild() -> None:
    """Drop the cache and re-ingest everything."""
    result = asyncio.run(ingest_all(rebuild=True))
    typer.echo(f"rebuilt: {result}")


@app_cli.command()
def pair() -> None:
    """Print the shared pairing token.

    In LAN_MODE, `/api/auth/pairing` refuses to hand this out over HTTP
    (Host-based trust is off — see app.security), so pairing a phone
    happens out-of-band instead: run this on the machine running the
    backend (bare-metal via `make pair`, Docker via `make docker-pair`),
    which builds the full `http://<lan-ip>:<port>/?pair=<token>` link.
    """
    from app.security import get_token

    typer.echo(get_token())


if __name__ == "__main__":
    app_cli()
