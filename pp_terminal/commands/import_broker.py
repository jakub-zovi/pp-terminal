"""
    Copyright (C) 2025-26 Dipl.-Ing. Christoph Massmann <chris@dev-investor.de>

    This file is part of pp-terminal.

    pp-terminal is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    pp-terminal is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with pp-terminal. If not, see <http://www.gnu.org/licenses/>.
"""
# pylint: disable=too-many-arguments,too-many-positional-arguments
from pathlib import Path
from typing import cast

from rich.console import Console
import typer
from typing_extensions import Annotated

from pp_terminal.data.broker_import.importer import import_transactions
from pp_terminal.data.broker_import.models import ImportReport
from pp_terminal.exceptions import InputError

app = typer.Typer(no_args_is_help=True)
console = Console()


def _print_report(report: ImportReport) -> None:
    console.print(f"parsed: {report.parsed}")
    console.print(f"duplicates: {report.duplicates}")
    console.print(f"unsupported: {report.unsupported}")
    console.print(f"to_import: {report.to_import}")
    console.print(f"expected_net_cash_delta: {report.expected_net_cash_delta}")
    if report.output_file is not None:
        console.print(f"output: {report.output_file}")


@app.command(name='transactions')
def transactions(
    ctx: typer.Context,
    broker_export: Annotated[Path, typer.Argument(exists=True, file_okay=True, dir_okay=False, readable=True)],
    portfolio_account: Annotated[str, typer.Option(help='Portfolio account name to import security transactions into.')],
    cash_account: Annotated[str, typer.Option(help='Cash/deposit account name to import cash legs into.')],
    output_file: Annotated[Path | None, typer.Option('--output', help='Output Portfolio Performance XML file. The source file is never modified.')] = None,
    dry_run: Annotated[bool, typer.Option(help='Preview import without writing XML.')] = False,
    ticker_map: Annotated[list[str] | None, typer.Option(help='Ticker alias mapping, e.g. GAW.UK=GAW.L.')] = None,
) -> None:
    """Import the broker transaction exports supported by pp-terminal into a new XML file."""

    source_file = cast(Path, ctx.obj.source_file)
    mappings = dict(item.split('=', 1) for item in ticker_map or [])

    if not dry_run and output_file is None:
        raise InputError('pass --output or use --dry-run')

    report = import_transactions(
        source_file=source_file,
        broker_export=broker_export,
        portfolio_account_name=portfolio_account,
        cash_account_name=cash_account,
        output_file=output_file,
        dry_run=dry_run,
        ticker_mappings=mappings,
    )
    _print_report(report)
