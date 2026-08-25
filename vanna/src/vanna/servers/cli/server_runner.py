"""CLI for the stripped Vanna kernel. StockJarvis boots via python -m app.main."""

import click


@click.command()
def main() -> None:
    click.echo("StockJarvis is started with: python -m app.main")
    click.echo("Set ANTHROPIC_API_KEY and DATABASE_URL in .env first.")


if __name__ == "__main__":
    main()
