from typing import Any

import pandas as pd
import pytest

from pp_terminal.domain.realized_gains import calculate_realized_gains


def _transactions(rows: list[dict[str, Any]]) -> pd.DataFrame:
    frame = pd.DataFrame(rows)
    frame.index = pd.MultiIndex.from_tuples(
        [(r['date'], r['accountId'], r['securityId']) for r in rows],
        names=['date', 'accountId', 'securityId'],
    )
    return frame.drop(columns=['date', 'accountId', 'securityId'])


def test_realized_gains_preserves_basis_across_transfers_and_ignores_fee_deliveries() -> None:
    transactions = _transactions([
        {'date': '2024-01-01', 'accountId': 'A', 'securityId': 'ETH', 'type': 'BUY', 'amount': 100.0, 'shares': 1.0, 'fees': 2.0, 'currency': 'EUR', 'transferTargetAccount': None, 'transferTargetShares': None},
        {'date': '2024-02-01', 'accountId': 'A', 'securityId': 'ETH', 'type': 'TRANSFER_OUT', 'amount': 0.0, 'shares': 1.0, 'fees': 0.0, 'currency': 'EUR', 'transferTargetAccount': 'B', 'transferTargetShares': 1.0},
        {'date': '2024-02-01', 'accountId': 'B', 'securityId': 'ETH', 'type': 'TRANSFER_IN', 'amount': 0.0, 'shares': 1.0, 'fees': 0.0, 'currency': 'EUR', 'transferTargetAccount': None, 'transferTargetShares': None},
        {'date': '2024-03-01', 'accountId': 'B', 'securityId': 'ETH', 'type': 'DELIVERY_OUTBOUND', 'amount': 0.0, 'shares': 0.01, 'fees': 0.0, 'currency': 'EUR', 'transferTargetAccount': None, 'transferTargetShares': None},
        {'date': '2024-04-01', 'accountId': 'B', 'securityId': 'ETH', 'type': 'SELL', 'amount': 150.0, 'shares': 0.99, 'fees': 1.5, 'currency': 'EUR', 'transferTargetAccount': None, 'transferTargetShares': None},
    ])

    result = calculate_realized_gains(transactions)

    assert result.loc[('ETH', 'EUR'), 'sharesDisposed'] == 1.0
    assert result.loc[('ETH', 'EUR'), 'grossProceeds'] == pytest.approx(151.5)
    assert result.loc[('ETH', 'EUR'), 'costBasis'] == 102.0
    assert result.loc[('ETH', 'EUR'), 'capitalGain'] == pytest.approx(49.5)
    assert result.loc[('ETH', 'EUR'), 'salesFees'] == 1.5
    assert result.loc[('ETH', 'EUR'), 'unmatchedShares'] == 0.0


def test_realized_gains_adds_sales_fee_back_to_proceeds() -> None:
    # PpPortfolioBuilder's SQL strips the transaction fee once from 'amount' for both BUY and
    # SELL (mirroring that Portfolio Performance's top-level <amount> is already net of fee).
    # calculate_realized_gains must add it back on both sides: to the cost basis for BUYs
    # (already covered above) and to gross proceeds for SELLs, or every disposal with a fee
    # understates its proceeds (and therefore its capital gain) by the fee amount.
    transactions = _transactions([
        {'date': '2024-01-01', 'accountId': 'A', 'securityId': 'BRK', 'type': 'BUY', 'amount': 954.78, 'shares': 2.0, 'fees': 0.35, 'currency': 'USD', 'transferTargetAccount': None, 'transferTargetShares': None},
        {'date': '2024-06-01', 'accountId': 'A', 'securityId': 'BRK', 'type': 'SELL', 'amount': 952.49, 'shares': 2.0, 'fees': 0.37, 'currency': 'USD', 'transferTargetAccount': None, 'transferTargetShares': None},
    ])

    result = calculate_realized_gains(transactions)

    assert result.loc[('BRK', 'USD'), 'grossProceeds'] == pytest.approx(952.86)
    assert result.loc[('BRK', 'USD'), 'costBasis'] == pytest.approx(955.13)
    assert result.loc[('BRK', 'USD'), 'capitalGain'] == pytest.approx(-2.27)


def test_realized_gains_counts_delivery_outbound_proceeds_when_nonzero() -> None:
    # Portfolio Performance books both network-fee dust (amount == 0) and genuine disposals,
    # e.g. spending crypto directly, as DELIVERY_OUTBOUND. Only the former is proceeds-free;
    # a DELIVERY_OUTBOUND with a real amount must count as real proceeds like a SELL does, or
    # the full cost basis of the spent coins is booked as a loss.
    transactions = _transactions([
        {'date': '2024-01-01', 'accountId': 'A', 'securityId': 'BTC', 'type': 'BUY', 'amount': 100.0, 'shares': 1.0, 'fees': 0.0, 'currency': 'EUR', 'transferTargetAccount': None, 'transferTargetShares': None},
        {'date': '2024-02-01', 'accountId': 'A', 'securityId': 'BTC', 'type': 'DELIVERY_OUTBOUND', 'amount': 0.0, 'shares': 0.001, 'fees': 0.0, 'currency': 'EUR', 'transferTargetAccount': None, 'transferTargetShares': None},
        {'date': '2024-03-01', 'accountId': 'A', 'securityId': 'BTC', 'type': 'DELIVERY_OUTBOUND', 'amount': 60.0, 'shares': 0.5, 'fees': 0.0, 'currency': 'EUR', 'transferTargetAccount': None, 'transferTargetShares': None},
    ])

    result = calculate_realized_gains(transactions)

    assert result.loc[('BTC', 'EUR'), 'sharesDisposed'] == pytest.approx(0.501)
    assert result.loc[('BTC', 'EUR'), 'grossProceeds'] == pytest.approx(60.0)
    assert result.loc[('BTC', 'EUR'), 'costBasis'] == pytest.approx(50.1)
    assert result.loc[('BTC', 'EUR'), 'capitalGain'] == pytest.approx(9.9)
