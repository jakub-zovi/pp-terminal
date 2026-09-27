"""
    Copyright (C) 2025-26 Dipl.-Ing. Christoph Massmann <chris@dev-investor.de>

    This file is part of pp-terminal.
"""
# pylint: disable=too-many-arguments,too-many-positional-arguments,too-many-instance-attributes,c-extension-no-member,duplicate-code,too-many-locals
import csv
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from uuid import uuid4

from lxml import etree

from pp_terminal.exceptions import InputError

_MONEY_SCALE = Decimal('100')
_SHARE_SCALE = Decimal('100000000')


@dataclass(frozen=True)
class PortfolioTransferCandidate:
    external_id: str
    date: datetime
    transaction_type: str
    source_portfolio: str
    target_portfolio: str | None
    security: str
    shares: Decimal
    amount: Decimal
    currency: str
    fee_shares: Decimal
    note: str | None


@dataclass(frozen=True)
class PortfolioTransferImportReport:
    parsed: int
    duplicates: int
    unsupported: int
    to_import: int
    output_file: Path | None


def import_portfolio_transfers(source_file: Path, transfer_export: Path, output_file: Path | None, dry_run: bool) -> PortfolioTransferImportReport:
    candidates = _parse_transfer_csv(transfer_export)
    return import_portfolio_transfer_candidates(source_file, candidates, output_file, dry_run)


def import_portfolio_transfer_candidates(
    source_file: Path,
    candidates: list[PortfolioTransferCandidate],
    output_file: Path | None,
    dry_run: bool,
) -> PortfolioTransferImportReport:
    tree = etree.parse(str(source_file))
    root = tree.getroot()
    to_import = [candidate for candidate in candidates if not _is_duplicate(root, candidate)]

    if not dry_run:
        if output_file is None:
            raise InputError('pass --output or use --dry-run')
        if output_file.exists():
            raise InputError(f'Output file {output_file} already exists')
        for candidate in to_import:
            _append_candidate(root, candidate)
        tree.write(str(output_file), encoding='utf-8', xml_declaration=False, pretty_print=True)

    return PortfolioTransferImportReport(
        parsed=len(candidates),
        duplicates=len(candidates) - len(to_import),
        unsupported=0,
        to_import=len(to_import),
        output_file=output_file if not dry_run else None,
    )


def _parse_transfer_csv(path: Path) -> list[PortfolioTransferCandidate]:
    with path.open(newline='', encoding='utf-8-sig') as handle:
        return [_row_to_candidate(row) for row in csv.DictReader(handle)]


def _row_to_candidate(row: dict[str, str]) -> PortfolioTransferCandidate:
    transaction_type = row['type'].strip().upper()
    if transaction_type not in {'TRANSFER', 'DELIVERY_OUTBOUND', 'DELIVERY_INBOUND'}:
        raise InputError(f'Unsupported portfolio transfer import type: {transaction_type}')
    return PortfolioTransferCandidate(
        external_id=row['external_id'].strip(),
        date=datetime.fromisoformat(row['date'].strip()),
        transaction_type=transaction_type,
        source_portfolio=row['source_portfolio'].strip(),
        target_portfolio=row.get('target_portfolio', '').strip() or None,
        security=row['security'].strip(),
        shares=_decimal(row['shares']),
        amount=_decimal(row.get('amount', '0')),
        currency=(row.get('currency') or 'EUR').strip(),
        fee_shares=_decimal(row.get('fee_shares', '0')),
        note=row.get('note', '').strip() or None,
    )


def _append_candidate(root: etree._Element, candidate: PortfolioTransferCandidate) -> None:
    security = _find_security(root, candidate.security)
    if candidate.transaction_type == 'TRANSFER':
        if candidate.target_portfolio is None:
            raise InputError(f'Transfer {candidate.external_id} has no target_portfolio')
        _append_transfer(root, candidate, security)
        if candidate.fee_shares:
            _append_delivery(root, _fee_candidate(candidate), security)
        return
    _append_delivery(root, candidate, security)


def _append_transfer(root: etree._Element, candidate: PortfolioTransferCandidate, security: etree._Element) -> None:
    source = _find_portfolio(root, candidate.source_portfolio)
    target = _find_portfolio(root, candidate.target_portfolio or '')
    source_id = _next_id(root)
    cross_id = _next_id(root, source_id)
    target_id = _next_id(root, cross_id)
    note = _note(candidate)

    source_outer = _appears_after(root, source, target)
    outer = source if source_outer else target
    outer_transactions = _transactions_element(outer)
    outer_transaction = etree.SubElement(outer_transactions, 'portfolio-transaction', id=str(source_id if source_outer else target_id))
    _fill_common(outer_transaction, candidate, security, note)
    cross_entry = etree.SubElement(outer_transaction, 'crossEntry', {'class': 'portfolio-transfer', 'id': str(cross_id)})
    etree.SubElement(cross_entry, 'portfolioFrom', reference=source.get('id'))
    if source_outer:
        etree.SubElement(cross_entry, 'transactionFrom', reference=str(source_id))
    else:
        transaction_from = etree.SubElement(cross_entry, 'transactionFrom', id=str(source_id))
        _fill_common(transaction_from, candidate, security, note)
        etree.SubElement(transaction_from, 'crossEntry', {'class': 'portfolio-transfer', 'reference': str(cross_id)})
        _append_tail(transaction_from, 'TRANSFER_OUT')
    etree.SubElement(cross_entry, 'portfolioTo', reference=target.get('id'))
    if source_outer:
        transaction_to = etree.SubElement(cross_entry, 'transactionTo', id=str(target_id))
        _fill_common(transaction_to, candidate, security, note)
        etree.SubElement(transaction_to, 'crossEntry', {'class': 'portfolio-transfer', 'reference': str(cross_id)})
        _append_tail(transaction_to, 'TRANSFER_IN')
    else:
        etree.SubElement(cross_entry, 'transactionTo', reference=str(target_id))
    if source_outer:
        _add_transaction_reference(target, target_id)
    else:
        _add_transaction_reference(source, source_id)
    _append_tail(outer_transaction, 'TRANSFER_OUT' if source_outer else 'TRANSFER_IN')


def _append_delivery(root: etree._Element, candidate: PortfolioTransferCandidate, security: etree._Element) -> None:
    portfolio = _find_portfolio(root, candidate.source_portfolio)
    transaction = etree.SubElement(_transactions_element(portfolio), 'portfolio-transaction', id=str(_next_id(root)))
    _fill_common(transaction, candidate, security, _note(candidate))
    _append_tail(transaction, candidate.transaction_type)


def _fill_common(transaction: etree._Element, candidate: PortfolioTransferCandidate, security: etree._Element, note: str) -> None:
    etree.SubElement(transaction, 'uuid').text = str(uuid4())
    etree.SubElement(transaction, 'date').text = _format_date(candidate.date)
    etree.SubElement(transaction, 'currencyCode').text = candidate.currency
    etree.SubElement(transaction, 'amount').text = str(_money(candidate.amount))
    etree.SubElement(transaction, 'security', reference=security.get('id'))
    etree.SubElement(transaction, 'shares').text = str(_shares(candidate.shares))
    etree.SubElement(transaction, 'note').text = note


def _append_tail(transaction: etree._Element, transaction_type: str) -> None:
    etree.SubElement(transaction, 'updatedAt').text = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')
    etree.SubElement(transaction, 'type').text = transaction_type


def _fee_candidate(candidate: PortfolioTransferCandidate) -> PortfolioTransferCandidate:
    return PortfolioTransferCandidate(
        external_id=f'{candidate.external_id}:fee',
        date=candidate.date,
        transaction_type='DELIVERY_OUTBOUND',
        source_portfolio=candidate.source_portfolio,
        target_portfolio=None,
        security=candidate.security,
        shares=candidate.fee_shares,
        amount=Decimal('0'),
        currency=candidate.currency,
        fee_shares=Decimal('0'),
        note='Network fee',
    )


def _find_portfolio(root: etree._Element, name: str) -> etree._Element:
    portfolio_ids = _top_level_portfolio_ids(root)
    matches = [
        element for element in root.iter()
        if element.tag in {'portfolio', 'portfolioFrom', 'portfolioTo'}
        and element.get('id') in portfolio_ids
        and element.findtext('name') == name
    ]
    if matches:
        return matches[0]
    raise InputError(f'Portfolio account not found: {name}')


def _top_level_portfolio_ids(root: etree._Element) -> set[str]:
    portfolios = root.find('portfolios')
    if portfolios is None:
        raise InputError('No portfolios section found')
    ids = set()
    for portfolio in portfolios.findall('portfolio'):
        portfolio_id = portfolio.get('id') or portfolio.get('reference')
        if portfolio_id is not None:
            ids.add(portfolio_id)
    return ids


def _find_security(root: etree._Element, security_name: str) -> etree._Element:
    for security in root.iter('security'):
        if security.findtext('tickerSymbol') == security_name or security.findtext('name') == security_name or security.findtext('isin') == security_name:
            return security
    raise InputError(f'Security not found: {security_name}')


def _is_duplicate(root: etree._Element, candidate: PortfolioTransferCandidate) -> bool:
    needle = f'external_id={candidate.external_id}'
    return any(needle in (note.text or '') for note in root.iter('note'))


def _transactions_element(portfolio: etree._Element) -> etree._Element:
    transactions = portfolio.find('transactions')
    if transactions is None:
        transactions = etree.SubElement(portfolio, 'transactions')
    return transactions


def _add_transaction_reference(portfolio: etree._Element, transaction_id: int) -> None:
    etree.SubElement(_transactions_element(portfolio), 'portfolio-transaction', reference=str(transaction_id))


def _appears_after(root: etree._Element, first: etree._Element, second: etree._Element) -> bool:
    elements = list(root.iter())
    return elements.index(first) > elements.index(second)


def _note(candidate: PortfolioTransferCandidate) -> str:
    base = candidate.note or candidate.transaction_type
    return f'{base}; external_id={candidate.external_id}'


def _next_id(root: etree._Element, minimum: int | None = None) -> int:
    max_id = max((int(element.get('id')) for element in root.iter() if element.get('id', '').isdigit()), default=0)
    if minimum is not None:
        max_id = max(max_id, minimum)
    return max_id + 1


def _format_date(date: datetime) -> str:
    return date.strftime('%Y-%m-%dT%H:%M')


def _money(amount: Decimal) -> int:
    return int((amount * _MONEY_SCALE).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def _shares(amount: Decimal) -> int:
    return int((amount * _SHARE_SCALE).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def _decimal(value: str | None) -> Decimal:
    if value is None or value.strip() == '':
        return Decimal('0')
    return Decimal(value.strip())
