"""Realized capital/price gain calculations for Portfolio Performance transactions."""

from collections import defaultdict
from typing import Any

import pandas as pd


_PURCHASE_TYPES = {'BUY', 'DELIVERY_INBOUND'}
_TRANSFER_OUT = 'TRANSFER_OUT'
_DISPOSAL_TYPES = {'SELL', 'DELIVERY_OUTBOUND'}


def _value(row: pd.Series, name: str, default: Any = None) -> Any:
    value = row.get(name, default)
    return default if value is None or pd.isna(value) else value


def _consume(  # pylint: disable=too-many-arguments,too-many-positional-arguments
    lots: list[dict[str, Any]],
    account_id: str,
    security_id: str,
    shares: float,
    destination: str | None = None,
    share_ratio: float = 1.0,
) -> tuple[float, float, list[dict[str, Any]]]:
    """Consume FIFO lots, optionally moving the consumed basis to a new account."""
    remaining = shares
    basis = 0.0
    moved: list[dict[str, Any]] = []
    for lot in lots:
        if remaining <= 1e-12:
            break
        if lot['accountId'] != account_id or lot['securityId'] != security_id:
            continue
        if lot['shares'] <= 1e-12:
            continue
        taken = min(remaining, lot['shares'])
        fraction = taken / lot['shares'] if lot['shares'] else 0.0
        taken_basis = lot['basis'] * fraction
        basis += taken_basis
        lot['shares'] -= taken
        lot['basis'] -= taken_basis
        remaining -= taken
        if destination and share_ratio > 0:
            moved.append({
                'accountId': destination,
                'securityId': security_id,
                'shares': taken * share_ratio,
                'basis': taken_basis,
                'date': lot['date'],
            })
    return remaining, basis, moved


def calculate_realized_gains(transactions: pd.DataFrame) -> pd.DataFrame:  # pylint: disable=too-many-locals
    """Calculate FIFO realized gains, preserving basis across depot transfers.

    ``SELL`` and ``DELIVERY_OUTBOUND`` are disposals.  The latter is important
    for genuine network-fee withdrawals: it consumes the fee coins and realizes
    their zero-proceeds loss, but it does not turn an internal transfer into a
    disposal.  ``TRANSFER_OUT`` only moves lots to its linked destination.

    Returns a DataFrame indexed by ``(securityId, currency)`` with gross
    proceeds, acquisition cost basis, realized capital gain, fees on sales,
    disposed shares, and unmatched shares.
    """
    if transactions.empty:
        return pd.DataFrame(columns=[
            'grossProceeds', 'costBasis', 'capitalGain', 'salesFees',
            'sharesDisposed', 'unmatchedShares',
        ]).rename_axis(['securityId', 'currency'])

    rows = transactions.reset_index()
    rows['_input_order'] = range(len(rows))
    rows = rows.sort_values(['date', '_input_order'])
    lots: list[dict[str, Any]] = []
    totals: defaultdict[tuple[str, str], dict[str, float]] = defaultdict(lambda: {
        'grossProceeds': 0.0,
        'costBasis': 0.0,
        'capitalGain': 0.0,
        'salesFees': 0.0,
        'sharesDisposed': 0.0,
        'unmatchedShares': 0.0,
    })

    for _, row in rows.iterrows():
        security_id = str(row['securityId'])
        account_id = str(row['accountId'])
        currency = str(_value(row, 'currency', ''))
        tx_type = str(row['type'])
        shares = max(float(_value(row, 'shares', 0.0)), 0.0)
        amount = abs(float(_value(row, 'amount', 0.0)))
        fees = abs(float(_value(row, 'fees', 0.0)))

        if tx_type in _PURCHASE_TYPES and shares > 0:
            lots.append({
                'accountId': account_id,
                'securityId': security_id,
                'shares': shares,
                'basis': amount + fees,
                'date': row['date'],
            })
            continue

        if tx_type == _TRANSFER_OUT:
            target = _value(row, 'transferTargetAccount')
            if target is None:
                continue
            target_shares = _value(row, 'transferTargetShares', shares)
            ratio = float(target_shares) / shares if shares > 0 else 1.0
            _, _, moved = _consume(lots, account_id, security_id, shares, str(target), ratio)
            lots.extend(moved)
            lots.sort(key=lambda lot: lot['date'])
            continue

        if tx_type not in _DISPOSAL_TYPES or shares <= 0:
            continue

        key = (security_id, currency)
        unmatched, basis, _ = _consume(lots, account_id, security_id, shares)
        proceeds = amount if tx_type == 'SELL' else 0.0
        bucket = totals[key]
        bucket['grossProceeds'] += proceeds
        bucket['costBasis'] += basis
        bucket['capitalGain'] += proceeds - basis
        bucket['salesFees'] += fees if tx_type == 'SELL' else 0.0
        bucket['sharesDisposed'] += shares - unmatched
        bucket['unmatchedShares'] += unmatched

    result = pd.DataFrame.from_dict(totals, orient='index')
    result.index = pd.MultiIndex.from_tuples(result.index, names=['securityId', 'currency'])
    if result.empty:
        return pd.DataFrame(columns=[
            'grossProceeds', 'costBasis', 'capitalGain', 'salesFees',
            'sharesDisposed', 'unmatchedShares',
        ]).rename_axis(['securityId', 'currency'])
    return result.sort_index()
