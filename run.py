#!/usr/bin/env python3
"""
One-click Python launcher for OmniSearch Universal Discovery Dashboard.
"""

import os
import sys
import webbrowser
import threading
import time
import uvicorn

try:
    from rich.console import Console
    from rich.panel import Panel
    from rich.text import Text
    USE_RICH = True
except ImportError:
    USE_RICH = False


def open_browser(url: str):
    time.sleep(1.2)
    try:
        webbrowser.open(url)
    except Exception:
        pass


def main():
    host = "0.0.0.0"
    port = 8000
    local_url = f"http://localhost:{port}"
    api_docs = f"http://localhost:{port}/docs"

    if USE_RICH:
        console = Console()
        text = Text()
        text.append("\n  🚀  OmniSearch Discovery Engine is Live!\n\n", style="bold green")
        text.append("  🌐  Dashboard:  ", style="bold white")
        text.append(f"{local_url}\n", style="bold cyan underline")
        text.append("  📡  API Docs:   ", style="bold white")
        text.append(f"{api_docs}\n", style="bold blue underline")
        text.append("  🔍  Network:    ", style="bold white")
        text.append(f"http://127.0.0.1:{port}\n\n", style="cyan")
        text.append("  Press Ctrl+C to stop the server.\n", style="dim")

        panel = Panel(text, title="[bold magenta]OmniSearch Discovery Engine[/bold magenta]", border_style="blue")
        console.print(panel)
    else:
        print("\n" + "=" * 60)
        print("  🚀  OmniSearch Discovery Engine is Live!")
        print("=" * 60)
        print(f"  🌐  Dashboard:  {local_url}")
        print(f"  📡  API Docs:   {api_docs}")
        print(f"  🔍  Network:    http://127.0.0.1:{port}")
        print("=" * 60)
        print("  Press Ctrl+C to stop the server.\n")

    # Open browser automatically in background
    threading.Thread(target=open_browser, args=(local_url,), daemon=True).start()

    uvicorn.run("omnisearch.api.app:app", host=host, port=port, log_level="info")


if __name__ == "__main__":
    main()
