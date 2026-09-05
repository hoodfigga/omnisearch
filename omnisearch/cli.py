"""
Command-Line Interface (CLI) for Video Discovery Engine.
"""

from __future__ import annotations
import argparse
import asyncio
import json
import sys
from typing import List, Optional
from rich.console import Console
from rich.table import Table

from omnisearch.models.video import ItemType
from omnisearch.models.query import MatchMode, SearchOptions
from omnisearch.core.orchestrator import VideoDiscoveryOrchestrator


def parse_args():
    parser = argparse.ArgumentParser(
        description="OmniSearch CLI: Cross-platform everything search and direct file download engine."
    )
    parser.add_argument("query", help="Search query (supports 'quoted phrases', AND/OR/NOT, title:prefix)")
    parser.add_argument(
        "--mode",
        choices=["EXACT_MATCH", "TITLE_AND_METADATA", "TITLE_ONLY", "FLEXIBLE_MATCH", "SEMANTIC_EXPANSION"],
        default="EXACT_MATCH",
        help="Matching mode (default: EXACT_MATCH)",
    )
    parser.add_argument("--title-only", action="store_true", help="Restrict matching strictly to item title")
    parser.add_argument(
        "-t", "--type",
        help="Filter by item types (comma-separated: FILE, ARCHIVE, DOCUMENT, SOFTWARE, AUDIO, VIDEO, IMAGE, DATASET, WEB_PAGE)",
    )
    parser.add_argument(
        "-e", "--ext",
        help="Filter by file extensions (comma-separated: zip, rar, 7z, tar, gz, iso, pdf, exe, dmg, etc.)",
    )
    parser.add_argument("--sources", help="Comma-separated list of source IDs (e.g. open_web, file_hosts, youtube, peertube, ia)")
    parser.add_argument("--limit", type=int, default=25, help="Maximum number of results to return (default: 25)")
    parser.add_argument("--pages", type=int, default=3, help="Maximum pagination pages per source (default: 3)")
    parser.add_argument("--min-score", type=float, default=0.1, help="Minimum relevance score threshold")
    parser.add_argument("--json", action="store_true", help="Output results in structured machine-readable JSON format")
    return parser.parse_args()


async def run_cli():
    args = parse_args()
    console = Console()

    sources_list = [s.strip() for s in args.sources.split(",")] if args.sources else None

    item_types_list = None
    if args.type:
        item_types_list = []
        for t in args.type.split(","):
            cleaned = t.strip().upper()
            if cleaned:
                try:
                    item_types_list.append(ItemType(cleaned))
                except ValueError:
                    console.print(f"[bold yellow]Warning:[/bold yellow] Unknown item type: {t.strip()}")

    file_exts_list = None
    if args.ext:
        file_exts_list = [e.strip().lstrip(".").lower() for e in args.ext.split(",") if e.strip()]

    options = SearchOptions(
        match_mode=MatchMode(args.mode),
        title_only=args.title_only,
        sources=sources_list,
        item_types=item_types_list,
        file_extensions=file_exts_list,
        max_results=args.limit,
        max_pages_per_source=args.pages,
        min_score=args.min_score,
    )

    orchestrator = VideoDiscoveryOrchestrator()

    if not args.json:
        console.print(f"[bold blue]OmniSearch scanning across sources for:[/bold blue] [green]{args.query!r}[/green]")
        type_str = ", ".join(t.value for t in item_types_list) if item_types_list else "all"
        ext_str = ", ".join(file_exts_list) if file_exts_list else "all"
        console.print(f"Mode: [cyan]{args.mode}[/cyan] | Types: [cyan]{type_str}[/cyan] | Exts: [cyan]{ext_str}[/cyan] | Sources: [cyan]{args.sources or 'all'}[/cyan]\n")

    response = await orchestrator.search(args.query, options=options)

    if args.json:
        # Output clean machine-readable JSON
        json_output = response.model_dump_json(indent=2)
        print(json_output)
        return

    # Rich human-readable table output
    table = Table(title=f"Discovered Files & Resources ({len(response.results)} matches found in {response.metrics.duration_ms} ms)")
    table.add_column("Rank", justify="right", style="cyan", no_wrap=True)
    table.add_column("Score", justify="right", style="bold green", no_wrap=True)
    table.add_column("Type", style="bold magenta", no_wrap=True)
    table.add_column("Ext", style="yellow", no_wrap=True)
    table.add_column("Size", justify="right", style="white", no_wrap=True)
    table.add_column("Direct DL", justify="center", no_wrap=True)
    table.add_column("Platform", style="cyan", no_wrap=True)
    table.add_column("Title", style="bold white")
    table.add_column("URL / Download", style="blue")

    for v in response.results:
        direct_dl = "[bold green]YES[/bold green]" if v.download_url else "[dim]Page[/dim]"
        size_display = v.file_size_human or "-"
        ext_display = (v.file_extension or "-").upper()
        type_display = v.item_type.value if hasattr(v, "item_type") else "FILE"
        title_display = v.title[:55] + ("..." if len(v.title) > 55 else "")
        url_display = v.download_url or v.canonical_url

        table.add_row(
            str(v.rank or "-"),
            f"{v.relevance_score:.2f}",
            type_display,
            ext_display,
            size_display,
            direct_dl,
            v.platform,
            title_display,
            url_display,
        )

    console.print(table)
    console.print(f"\n[dim]Sources contacted: {', '.join(response.metrics.sources_contacted)} | Candidates: {response.metrics.candidates_retrieved} | Deduplicated: {response.metrics.duplicates_filtered}[/dim]")


def main():
    asyncio.run(run_cli())


if __name__ == "__main__":
    main()
