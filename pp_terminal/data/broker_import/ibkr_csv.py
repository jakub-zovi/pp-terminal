"""
    Copyright (C) 2025-26 Dipl.-Ing. Christoph Massmann <chris@dev-investor.de>

    This file is part of pp-terminal.
"""
import csv
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from pp_terminal.data.broker_import.models import ImportCandidate

_SECTION_HEADER_MARKERS = {'ClientAccountID', 'CurrencyPrimary'}


def parse_csv(path: Path) -> list[ImportCandidate]:
    candidates = []
    for header, rows in _split_sections(path):
        if 'TransactionType' in header and 'Buy/Sell' in header:
            candidates.extend(_parse_trades(header, rows))
        elif 'Type' in header and 'Amount' in header and 'TransactionType' not in header:
            candidates.extend(_parse_cash_report(header, rows))
    return candidates


def _split_sections(path: Path) -> list[tuple[list[str], list[list[str]]]]:
    # IBKR "Activity Statement" CSV exports concatenate multiple flex-query tables, each
    # reintroducing its own header row (identifiable by its first column name) mid-file.
    sections: list[tuple[list[str], list[list[str]]]] = []
    header: list[str] | None = None
    rows: list[list[str]] = []
    with path.open(encoding='utf-8-sig', newline='') as csv_file:
        for row in csv.reader(csv_file):
            if not row:
                continue
            if row[0] in _SECTION_HEADER_MARKERS:
                if header is not None:
                    sections.append((header, rows))
                header, rows = row, []
            elif header is not None:
                rows.append(row)
    if header is not None:
        sections.append((header, rows))
    return sections


def _parse_trades(header: list[str], rows: list[list[str]]) -> list[ImportCandidate]:
    candidates = []
    for values in rows:
        row = dict(zip(header, values))
        if row.get('TransactionType') != 'ExchTrade' or row.get('Buy/Sell') not in {'BUY', 'SELL'}:
            continue
        if row.get('AssetClass') == 'CASH':
            candidate = _parse_currency_conversion(row)
            if candidate is not None:
                candidates.append(candidate)
            continue
        quantity = Decimal(row['Quantity'])
        trade_type = 'BUY' if quantity > 0 else 'SELL'
        trade_money = abs(Decimal(row.get('TradeMoney') or row.get('Proceeds') or '0'))
        commission = abs(Decimal(row.get('IBCommission') or '0'))
        date = datetime.strptime(row['DateTime'], '%Y%m%d;%H%M%S').replace(second=0)
        candidates.append(ImportCandidate(
            external_id=row.get('TradeID') or row.get('TransactionID') or row['DateTime'],
            date=date,
            transaction_type=trade_type,
            ticker=row.get('Symbol') or None,
            isin=row.get('ISIN') or row.get('SecurityID') or None,
            currency=row.get('CurrencyPrimary') or row.get('IBCommissionCurrency') or 'USD',
            shares=abs(quantity),
            gross_amount=trade_money,
            fee=commission,
            tax=abs(Decimal(row.get('Taxes') or '0')),
            net_cash=Decimal(row.get('NetCash') or '0'),
            note=row.get('Description') or None,
        ))
    return candidates


def _parse_currency_conversion(row: dict[str, str]) -> ImportCandidate | None:
    # IBKR FX pair rows (AssetClass=CASH, Symbol like "EUR.CZK"): Buy/Sell refers to the
    # BASE currency (first part); Quantity is in the base currency, TradeMoney/Proceeds in
    # the quote currency (second part). Model as a cross-currency account transfer.
    symbol = row.get('Symbol') or ''
    if '.' not in symbol:
        return None
    base_currency, quote_currency = symbol.split('.', 1)
    quantity = abs(Decimal(row['Quantity']))
    quote_amount = abs(Decimal(row.get('TradeMoney') or row.get('Proceeds') or '0'))
    commission = abs(Decimal(row.get('IBCommission') or '0'))
    commission_currency = row.get('IBCommissionCurrency') or base_currency
    date = datetime.strptime(row['DateTime'], '%Y%m%d;%H%M%S').replace(second=0)
    if row.get('Buy/Sell') == 'BUY':
        from_currency, from_amount, to_currency, to_amount = quote_currency, quote_amount, base_currency, quantity
    else:
        from_currency, from_amount, to_currency, to_amount = base_currency, quantity, quote_currency, quote_amount
    fee = commission if commission_currency == to_currency else Decimal('0')
    return ImportCandidate(
        external_id=row.get('TradeID') or row.get('TransactionID') or row['DateTime'],
        date=date,
        transaction_type='CURRENCY_TRANSFER',
        ticker=None,
        isin=None,
        currency=from_currency,
        shares=Decimal('0'),
        gross_amount=from_amount,
        fee=fee,
        tax=Decimal('0'),
        net_cash=Decimal('0'),
        note=symbol,
        to_currency=to_currency,
        to_amount=to_amount,
    )


def _parse_cash_report(header: list[str], rows: list[list[str]]) -> list[ImportCandidate]:
    candidates = []
    for values in rows:
        row = dict(zip(header, values))
        if row.get('Type') != 'Deposits/Withdrawals':
            continue
        amount = Decimal(row.get('Amount') or '0')
        date_text = row.get('Date/Time') or row.get('SettleDate') or row.get('ReportDate') or ''
        date = datetime.strptime(date_text, '%Y%m%d')
        transaction_type = 'DEPOSIT' if amount > 0 else 'REMOVAL'
        candidates.append(ImportCandidate(
            external_id=row.get('TransactionID') or f'{date.isoformat()}-{transaction_type}',
            date=date,
            transaction_type=transaction_type,
            ticker=None,
            isin=None,
            currency=row.get('CurrencyPrimary') or 'EUR',
            shares=Decimal('0'),
            gross_amount=abs(amount),
            fee=Decimal('0'),
            tax=Decimal('0'),
            net_cash=amount,
            note=row.get('Description') or None,
        ))
    return candidates
