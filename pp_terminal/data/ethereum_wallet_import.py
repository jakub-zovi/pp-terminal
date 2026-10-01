"""
    Copyright (C) 2025-26 Dipl.-Ing. Christoph Massmann <chris@dev-investor.de>

    This file is part of pp-terminal.
"""
# pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-locals,too-many-branches
import csv
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

from pp_terminal.data.portfolio_transfer_import import PortfolioTransferCandidate

_IGNORED_UNITS = {'HEX', 'Yf-DAI', 'EverStake', 'ETH | Visit website ethcollect .org to claim rewards', 'WETH'}


def classify_ethereum_wallet_exports(
    exodus_csv: Path,
    trezor_csv: Path,
    exodus_account: str,
    trezor_account: str,
    stake_account: str,
    stake_address: str,
    security: str,
    staking_return_txids: set[str],
) -> tuple[list[PortfolioTransferCandidate], list[str]]:
    exodus_rows = _read_dicts(exodus_csv)
    trezor_rows = _read_dicts(trezor_csv)
    exodus_by_tx = {_exodus_txid(row): row for row in exodus_rows if _exodus_txid(row)}
    trezor_by_tx: dict[str, list[dict[str, str]]] = {}
    for row in trezor_rows:
        trezor_by_tx.setdefault(row['Transaction ID'], []).append(row)

    candidates: list[PortfolioTransferCandidate] = []
    ignored: list[str] = []
    seen: set[str] = set()

    for txid, exodus in exodus_by_tx.items():
        trezor_eth = [row for row in trezor_by_tx.get(txid, []) if row['Amount unit'] == 'ETH']
        if not trezor_eth:
            continue
        trezor = trezor_eth[0]
        if exodus['TYPE'] == 'withdrawal' and trezor['Type'] == 'RECV':
            amount = abs(_decimal(exodus['OUTAMOUNT']))
            candidates.extend(_transfer_with_fee(
                txid, _exodus_date(exodus), exodus_account, trezor_account, security, amount,
                _decimal(trezor.get('Fiat (EUR)')), abs(_decimal(exodus['FEEAMOUNT'])), 'Exodus to Trezor'
            ))
            seen.add(txid)
        elif exodus['TYPE'] == 'deposit' and trezor['Type'] == 'SENT':
            amount = _decimal(exodus['INAMOUNT'])
            candidates.extend(_transfer_with_fee(
                txid, _trezor_date(trezor), trezor_account, exodus_account, security, amount,
                _decimal(trezor.get('Fiat (EUR)')), _decimal(trezor.get('Fee')), 'Trezor to Exodus'
            ))
            seen.add(txid)

    normalized_stake_address = stake_address.lower()
    for row in trezor_rows:
        txid = row['Transaction ID']
        unit = row['Amount unit']
        if txid in seen:
            continue
        if unit in _IGNORED_UNITS:
            ignored.append(f'{txid}: ignored unit {unit}')
            continue
        if unit != 'ETH':
            ignored.append(f'{txid}: ignored non-ETH unit {unit}')
            continue
        amount = _decimal(row['Amount'])
        fee = _decimal(row.get('Fee'))
        if txid in staking_return_txids and amount > 0:
            candidates.append(_candidate(
                txid, _trezor_date(row), 'TRANSFER', stake_account, trezor_account, security, amount,
                _decimal(row.get('Fiat (EUR)')), 'Everstake to Trezor'
            ))
        elif txid in staking_return_txids and fee > 0:
            candidates.append(_candidate(f'{txid}:fee', _trezor_date(row), 'DELIVERY_OUTBOUND', trezor_account, None, security, fee, Decimal('0'), 'Everstake withdrawal network fee'))
        elif row['Type'] == 'SENT' and row['Address'].lower() == normalized_stake_address:
            if amount > 0:
                candidates.extend(_transfer_with_fee(
                    txid, _trezor_date(row), trezor_account, stake_account, security, amount,
                    _decimal(row.get('Fiat (EUR)')), fee, 'Trezor to Everstake'
                ))
            elif fee > 0:
                candidates.append(_candidate(txid, _trezor_date(row), 'DELIVERY_OUTBOUND', trezor_account, None, security, fee, Decimal('0'), 'Everstake contract network fee'))

    return candidates, ignored


def _transfer_with_fee(
    txid: str,
    date: datetime,
    source: str,
    target: str,
    security: str,
    amount: Decimal,
    gross_amount: Decimal,
    fee: Decimal,
    note: str,
) -> list[PortfolioTransferCandidate]:
    candidates = [_candidate(txid, date, 'TRANSFER', source, target, security, amount, gross_amount, note)]
    if fee:
        candidates.append(_candidate(f'{txid}:fee', date, 'DELIVERY_OUTBOUND', source, None, security, fee, Decimal('0'), 'Ethereum network fee'))
    return candidates


def _candidate(
    external_id: str,
    date: datetime,
    transaction_type: str,
    source: str,
    target: str | None,
    security: str,
    shares: Decimal,
    amount: Decimal,
    note: str,
) -> PortfolioTransferCandidate:
    return PortfolioTransferCandidate(
        external_id=external_id,
        date=date,
        transaction_type=transaction_type,
        source_portfolio=source,
        target_portfolio=target,
        security=security,
        shares=shares,
        amount=amount,
        currency='EUR',
        fee_shares=Decimal('0'),
        note=note,
    )


def _read_dicts(path: Path) -> list[dict[str, str]]:
    with path.open(newline='', encoding='utf-8-sig') as handle:
        return list(csv.DictReader(handle))


def _exodus_txid(row: dict[str, str]) -> str:
    return row.get('OUTTXID') or row.get('INTXID') or ''


def _exodus_date(row: dict[str, str]) -> datetime:
    return datetime.fromisoformat(row['DATE'].replace('Z', '+00:00')).replace(tzinfo=None)


def _trezor_date(row: dict[str, str]) -> datetime:
    return datetime.fromtimestamp(int(row['Timestamp']), timezone.utc).replace(tzinfo=None)


def _decimal(value: str | None) -> Decimal:
    if value is None or value.strip() == '':
        return Decimal('0')
    return Decimal(value.strip().replace(',', ''))
