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
    assert result.loc[('ETH', 'EUR'), 'grossProceeds'] == 150.0
    assert result.loc[('ETH', 'EUR'), 'costBasis'] == 102.0
    assert result.loc[('ETH', 'EUR'), 'capitalGain'] == pytest.approx(48.0)
    assert result.loc[('ETH', 'EUR'), 'salesFees'] == 1.5
    assert result.loc[('ETH', 'EUR'), 'unmatchedShares'] == 0.0
