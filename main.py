import argparse
import sys
import io

# Ensure UTF-8 output on Windows consoles to prevent cp1252 charmap errors with emojis
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except AttributeError:
        pass

from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown
from src.graph import run_shopping_agent

console = Console(force_terminal=True, legacy_windows=False)


def print_banner():
    console.print(Panel.fit(
        "[bold cyan]🇧🇩 Bangladesh AI Shopping Decision Agent[/bold cyan]\n"
        "[dim]Powered by LangGraph + Gemini + DuckDuckGo + Jina AI Reader[/dim]\n"
        "[italic green]Specialized for Star Tech, Ryans, Daraz, Pickaboo & BD Retail[/italic green]",
        border_style="cyan"
    ))


def display_results(result: dict):
    req = result.get("requirements")
    if req:
        req_table = Table(title="📋 Parsed Requirements", border_style="blue")
        req_table.add_column("Category", style="cyan")
        req_table.add_column("Max Budget", style="green")
        req_table.add_column("Purposes", style="yellow")
        req_table.add_column("Language", style="magenta")
        budget_display = f"{req.budget_max:,.0f} BDT" if req.budget_max else "Flexible"
        req_table.add_row(req.category, budget_display, ", ".join(req.usage_purposes), req.detected_language)
        console.print(req_table)
        console.print()

    recommendations = result.get("recommendations", [])
    if recommendations:
        console.print("[bold yellow]🛒 Ranked Product Recommendations:[/bold yellow]\n")
        for card in recommendations:
            p = card.product
            price_display = f"৳{p.price:,.0f}" if p.price else "Visit Link"
            specs_summary = "\n".join(f"• [bold]{k}:[/bold] {v}" for k, v in p.specs.items()) or "Standard Specs"
            
            why_buy_text = "\n".join(f"[green]+ {r}[/green]" for r in card.why_buy)
            why_not_text = "\n".join(f"[red]- {r}[/red]" for r in card.why_not_buy)

            card_content = (
                f"[bold white]{p.name}[/bold white]\n"
                f"[bold cyan]Store:[/bold cyan] {p.store}   |   [bold green]Price:[/bold green] {price_display}   |   [bold yellow]Rating:[/bold yellow] {card.score}/10\n"
                f"[bold cyan]URL:[/bold cyan] [link={p.url}]{p.url}[/link]\n\n"
                f"[bold underline]Specifications:[/bold underline]\n{specs_summary}\n\n"
                f"[bold green]Why Buy:[/bold green]\n{why_buy_text}\n\n"
                f"[bold red]Why NOT Buy:[/bold red]\n{why_not_text}\n\n"
                f"[dim yellow]BD Market Note: {card.bangladesh_note}[/dim yellow]"
            )

            console.print(Panel(
                card_content,
                title=f"#{card.rank} {card.verdict}",
                border_style="green" if card.rank == 1 else "blue"
            ))
    else:
        console.print(Markdown(result.get("final_answer", "No recommendations found.")))


def main():
    parser = argparse.ArgumentParser(description="Bangladesh AI Shopping Agent CLI")
    parser.add_argument("--query", "-q", type=str, help="Shopping query (e.g. 'gaming laptop under 120k bdt')")
    args = parser.parse_args()

    print_banner()

    query = args.query
    if not query:
        console.print("\n[bold]Sample Queries:[/bold]")
        console.print("1. [dim]I need a gaming laptop under 120000 BDT in Bangladesh[/dim]")
        console.print("2. [dim]Suggest best phone under 45k taka with great camera[/dim]")
        console.print("3. [dim]amar 20k er moddhe programming er jonno monitor lagbe[/dim]\n")
        try:
            query = console.input("[bold cyan]Enter your shopping goal: [/bold cyan]").strip()
        except (KeyboardInterrupt, EOFError):
            console.print("\n[dim]Cancelled.[/dim]")
            sys.exit(0)

    if not query:
        console.print("[red]No query provided. Exiting.[/red]")
        sys.exit(1)

    console.print(f"\n[bold green]➜ Processing:[/bold green] [italic]\"{query}\"[/italic]...\n")

    result = run_shopping_agent(query)
    display_results(result)


if __name__ == "__main__":
    main()

