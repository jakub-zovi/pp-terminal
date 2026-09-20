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
# pylint: disable=too-many-instance-attributes
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path


@dataclass(frozen=True)
class ImportCandidate:
    external_id: str
    date: datetime
    transaction_type: str
    ticker: str | None
    isin: str | None
    currency: str
    shares: Decimal
    gross_amount: Decimal
    fee: Decimal
    tax: Decimal
    net_cash: Decimal
    note: str | None

    @property
    def is_trade(self) -> bool:
        return self.transaction_type in {'BUY', 'SELL'}


@dataclass(frozen=True)
class ImportReport:
    parsed: int
    duplicates: int
    unsupported: int
    to_import: int
    expected_net_cash_delta: Decimal
    output_file: Path | None
