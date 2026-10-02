"""View FIFO realized capital/price gains from completed disposals."""

from typing import cast

import typer

from pp_terminal.domain.portfolio import Portfolio
from pp_terminal.domain.realized_gains import calculate_realized_gains
from pp_terminal.output.strategy import Console, OutputStrategy
from pp_terminal.output.table_decorator import TableOptions

app = typer.Typer()
console = Console()


@app.command(name='realized-gains')
def print_realized_gains(ctx: typer.Context) -> None:
    """Show realized price gains by security and transaction currency."""
    portfolio = cast(Portfolio, ctx.obj.portfolio)
    output = cast(OutputStrategy, ctx.obj.output)
    result = calculate_realized_gains(portfolio.securities_account_transactions)
    if result.empty:
        console.print(output.empty_result())
        return

    display = result.reset_index()
    display = display[
        ['securityId', 'currency', 'grossProceeds', 'costBasis', 'capitalGain',
         'salesFees', 'sharesDisposed', 'unmatchedShares']
    ]
    console.print(*output.result_table(
        display,
        TableOptions(
            title='Realized capital/price gains',
            show_index=False,
        ),
    ))
