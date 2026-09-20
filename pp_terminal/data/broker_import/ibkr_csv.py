"""
    Copyright (C) 2025-26 Dipl.-Ing. Christoph Massmann <chris@dev-investor.de>

    This file is part of pp-terminal.
"""
import csv
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from pp_terminal.data.broker_import.models import ImportCandidate


def parse_csv(path: Path) -> list[ImportCandidate]:
    candidates = []
    with path.open(encoding='utf-8-sig', newline='') as csv_file:
        for row in csv.DictReader(csv_file):
            if row.get('TransactionType') != 'ExchTrade' or row.get('Buy/Sell') not in {'BUY', 'SELL'}:
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
