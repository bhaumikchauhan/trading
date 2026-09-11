import typer

from ..config import load_pattern_config, load_smoothing_config
from ..data import candle_db
from ..paths import PROJECT_ROOT
from ..patterns import find_candidates
from ..pivots import zigzag_pivots
from ..viz import plot_pivots

app = typer.Typer(add_completion=False)


@app.callback()
def _main() -> None:
    """Chart pattern detection CLI.

    Exists so Typer keeps requiring `scan` as an explicit subcommand name — with
    a single @app.command() and no callback, Typer silently flattens the app and
    treats a typed subcommand name as a positional argument instead.
    """


@app.command()
def scan(
    symbols: list[str] = typer.Argument(..., help="Symbols to scan, e.g. RELIANCE TCS"),
    start: str = typer.Option("2020-01-01", help="Start date, YYYY-MM-DD"),
    end: str | None = typer.Option(None, help="End date, YYYY-MM-DD (defaults to latest available)"),
    pattern: str = typer.Option("double_top", help="Pattern name to scan for"),
    min_confidence: float = typer.Option(0.0, help="Only show candidates at or above this confidence"),
    save_charts: bool = typer.Option(True, help="Save a QA chart per symbol under output/charts/"),
) -> None:
    """Scan symbols for pattern candidates against real historical data (candle_db),
    printing each match's pivots and confidence so results can be checked by eye —
    this is a manual-verification tool, not the labeled-dataset backtest harness
    planned in functional-spec.md section 8.
    """
    smoothing_cfg = load_smoothing_config()
    pattern_cfg = load_pattern_config(pattern)
    charts_dir = PROJECT_ROOT / "output" / "charts"

    for symbol in symbols:
        df = candle_db.get_history(symbol, start=start, end=end)
        if df.empty:
            typer.echo(f"\n{symbol}: no data found")
            continue

        df = df.set_index("timestamp")[["open", "high", "low", "close", "volume"]]
        pivots = zigzag_pivots(df["close"], threshold_pct=smoothing_cfg.zigzag.threshold_pct)
        candidates = [
            c
            for c in find_candidates(pattern, pivots, pattern_cfg)
            if c.confidence_score >= min_confidence
        ]
        candidates.sort(key=lambda c: c.confidence_score, reverse=True)

        typer.echo(
            f"\n{symbol}: {len(df)} bars, {len(pivots)} pivots, "
            f"{len(candidates)} {pattern} candidate(s)"
        )
        for i, candidate in enumerate(candidates, start=1):
            typer.echo(f"  candidate #{i}  confidence={candidate.confidence_score:.2f}")
            for p in candidate.pivots:
                typer.echo(f"    {p.type:<6} {p.timestamp.date()}  {p.price:.2f}")
            metrics = ", ".join(f"{k}={v:.2f}" for k, v in candidate.metrics.items())
            typer.echo(f"    metrics: {metrics}")

        if save_charts:
            charts_dir.mkdir(parents=True, exist_ok=True)
            save_path = charts_dir / f"{symbol}_{pattern}.png"
            plot_pivots(
                df,
                pivots,
                candidates=candidates,
                title=f"{symbol} {pattern}",
                save_path=str(save_path),
            )
            typer.echo(f"  chart saved: {save_path}")


if __name__ == "__main__":
    app()
