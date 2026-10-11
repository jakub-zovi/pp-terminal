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

import pandas as pd
import pytest

from pp_terminal.domain.portfolio import resolve_security
from pp_terminal.exceptions import InputError


class _Portfolio:  # pylint: disable=too-few-public-methods
    def __init__(self, securities: pd.DataFrame) -> None:
        self.securities = securities


def _portfolio() -> _Portfolio:
    return _Portfolio(pd.DataFrame(
        {'isin': ['IE00B4L5Y983', 'DE0005933931', 'DE0005933931'], 'wkn': ['A0RPWH', '593393', '593394']},
        index=pd.Index(['uuid-a', 'uuid-b', 'uuid-c'], name='securityId'),
    ))


def test_resolves_a_security_id_unchanged() -> None:
    assert resolve_security(_portfolio(), 'uuid-a') == 'uuid-a'  # type: ignore[arg-type]


def test_resolves_an_isin() -> None:
    assert resolve_security(_portfolio(), 'IE00B4L5Y983') == 'uuid-a'  # type: ignore[arg-type]


def test_resolves_a_wkn() -> None:
    assert resolve_security(_portfolio(), '593394') == 'uuid-c'  # type: ignore[arg-type]


def test_rejects_an_ambiguous_isin() -> None:
    with pytest.raises(InputError, match='matches multiple securities'):
        resolve_security(_portfolio(), 'DE0005933931')  # type: ignore[arg-type]


def test_rejects_an_unknown_security() -> None:
    with pytest.raises(InputError, match='not found'):
        resolve_security(_portfolio(), 'XX0000000000')  # type: ignore[arg-type]
