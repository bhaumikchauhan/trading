import csv
from pathlib import Path

import typer

from ..config import load_pattern_config, load_smoothing_config
from ..custom_logger import logger
from ..data import candle_db
from ..paths import PROJECT_ROOT
from ..patterns import Candidate, find_candidates, list_registered_patterns
from ..pivots import zigzag_pivots
from ..viz import plot_pivots

app = typer.Typer(add_completion=False)

ALL_SYMBOLS_FILE = PROJECT_ROOT / "data" / "all_symbols.csv"
CSV_FIELDNAMES = [
    "symbol",
    "pattern",
    "candidate_number",
    "confidence_score",
    "start_date",
    "end_date",
    "pivots",
    "metrics",
]


@app.callback()
def _main() -> None:
    """Chart pattern detection CLI.

    Exists so Typer keeps requiring `scan` as an explicit subcommand name — with
    a single @app.command() and no callback, Typer silently flattens the app and
    treats a typed subcommand name as a positional argument instead.
    """


def _load_all_symbols(path: Path = ALL_SYMBOLS_FILE) -> list[str]:
    with open(path, encoding="utf-8") as f:
        return [line.strip() for line in f if line.strip()]


def _format_pivots(candidate: Candidate) -> str:
    return " | ".join(f"{p.type}@{p.timestamp.date()}@{p.price:.2f}" for p in candidate.pivots)


def _format_metrics(candidate: Candidate) -> str:
    return ", ".join(f"{k}={v:.2f}" for k, v in candidate.metrics.items())


def _output_stem(symbols: list[str], patterns_scanned: list[str], pattern_option: str) -> str:
    symbol_part = symbols[0] if len(symbols) == 1 else str(len(symbols))
    pattern_part = pattern_option if len(patterns_scanned) == 1 else "mul_pattern"
    return f"{symbol_part}_{pattern_part}"


@app.command()
def scan(
    symbols: list[str] | None = typer.Argument(
        None, help="Symbols to scan, e.g. RELIANCE TCS. Omit when using --all-symbols."
    ),
    all_symbols: bool = typer.Option(
        False, "--all-symbols", help=f"Scan every symbol listed in {ALL_SYMBOLS_FILE}"
    ),
    start: str = typer.Option("2020-01-01", help="Start date, YYYY-MM-DD"),
    end: str | None = typer.Option(None, help="End date, YYYY-MM-DD (defaults to latest available)"),
    pattern: str = typer.Option(
        "double_top",
        help=(
            "Pattern name to scan for, or 'all' to scan every registered pattern "
            f"({', '.join(list_registered_patterns())})"
        ),
    ),
    min_confidence: float = typer.Option(0.0, help="Only show candidates at or above this confidence"),
    save_charts: bool = typer.Option(
        True, help="Save a QA chart per symbol under output/charts/ (slow over many symbols)"
    ),
    save_csv: bool = typer.Option(True, help="Save all results to a CSV under output/scans/"),
    quiet: bool = typer.Option(
        False,
        "--quiet",
        help="Print one summary line per symbol instead of full candidate detail "
        "(full detail is always in the CSV) — useful with --all-symbols",
    ),
) -> None:
    """Scan symbols for pattern candidates against real historical data (candle_db),
    printing each match's pivots and confidence so results can be checked by eye —
    this is a manual-verification tool, not the labeled-dataset backtest harness
    planned in functional-spec.md section 8.
    """
    if all_symbols:
        resolved_symbols = _load_all_symbols()
    elif symbols:
        resolved_symbols = symbols
    else:
        typer.echo("Provide at least one symbol, or use --all-symbols.")
        raise typer.Exit(code=1)

    patterns_to_scan = list_registered_patterns() if pattern == "all" else [pattern]
    pattern_configs = {p: load_pattern_config(p) for p in patterns_to_scan}
    smoothing_cfg = load_smoothing_config()

    charts_dir = PROJECT_ROOT / "output" / "charts"
    csv_dir = PROJECT_ROOT / "output" / "scans"
    csv_rows: list[dict] = []
    total_symbols = len(resolved_symbols)
    pattern_candidate_counts: dict[str, int] = dict.fromkeys(patterns_to_scan, 0)

    for symbol_idx, symbol in enumerate(resolved_symbols, start=1):
        logger.info(f"Scanning {symbol_idx}/{total_symbols}: {symbol}")
        df = candle_db.get_history(symbol, start=start, end=end)
        if df.empty:
            typer.echo(f"\n{symbol}: no data found")
            continue

        df = df.set_index("timestamp")[["open", "high", "low", "close", "volume"]]
        pivots = zigzag_pivots(df["close"], threshold_pct=smoothing_cfg.zigzag.threshold_pct)
        typer.echo(f"\n{symbol}: {len(df)} bars, {len(pivots)} pivots")

        chart_candidates: list[Candidate] = []
        for pat in patterns_to_scan:
            candidates = [
                c
                for c in find_candidates(pat, pivots, pattern_configs[pat])
                if c.confidence_score >= min_confidence
            ]
            candidates.sort(key=lambda c: c.confidence_score, reverse=True)
            chart_candidates.extend(candidates)
            pattern_candidate_counts[pat] += len(candidates)

            typer.echo(f"  [{pat}] {len(candidates)} candidate(s)")
            for i, candidate in enumerate(candidates, start=1):
                if not quiet:
                    typer.echo(f"    candidate #{i}  confidence={candidate.confidence_score:.2f}")
                    for p in candidate.pivots:
                        typer.echo(f"      {p.type:<6} {p.timestamp.date()}  {p.price:.2f}")
                    typer.echo(f"      metrics: {_format_metrics(candidate)}")
                csv_rows.append(
                    {
                        "symbol": symbol,
                        "pattern": pat,
                        "candidate_number": i,
                        "confidence_score": candidate.confidence_score,
                        "start_date": candidate.start_timestamp.date(),
                        "end_date": candidate.end_timestamp.date(),
                        "pivots": _format_pivots(candidate),
                        "metrics": _format_metrics(candidate),
                    }
                )

        if save_charts:
            charts_dir.mkdir(parents=True, exist_ok=True)
            stem = _output_stem([symbol], patterns_to_scan, pattern)
            save_path = charts_dir / f"{stem}.png"
            plot_pivots(
                df, pivots, candidates=chart_candidates, title=stem, save_path=str(save_path)
            )
            typer.echo(f"  chart saved: {save_path}")

    counts_str = ", ".join(f"{p}={c}" for p, c in pattern_candidate_counts.items())
    logger.info(
        f"Scan summary: {counts_str} (total={sum(pattern_candidate_counts.values())} "
        f"candidates across {total_symbols} symbol(s))"
    )

    if save_csv:
        csv_dir.mkdir(parents=True, exist_ok=True)
        stem = _output_stem(resolved_symbols, patterns_to_scan, pattern)
        csv_path = csv_dir / f"{stem}.csv"
        with open(csv_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=CSV_FIELDNAMES)
            writer.writeheader()
            writer.writerows(csv_rows)
        typer.echo(f"\nCSV saved: {csv_path} ({len(csv_rows)} rows)")


if __name__ == "__main__":
    app()
