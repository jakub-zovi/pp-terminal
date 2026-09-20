"""
    Copyright (C) 2025-26 Dipl.-Ing. Christoph Massmann <chris@dev-investor.de>

    This file is part of pp-terminal.
"""
# pylint: disable=too-many-arguments,too-many-positional-arguments,c-extension-no-member
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from uuid import uuid4

from lxml import etree

from pp_terminal.data.broker_import.ibkr_csv import parse_csv
from pp_terminal.data.broker_import.models import ImportCandidate, ImportReport
from pp_terminal.data.broker_import.xtb_xlsx import parse_xlsx
from pp_terminal.exceptions import InputError

_MONEY_SCALE = Decimal('100')
_SHARE_SCALE = Decimal('100000000')


def import_transactions(
    source_file: Path,
    broker_export: Path,
    portfolio_account_name: str,
    cash_account_name: str,
    output_file: Path | None,
    dry_run: bool,
    ticker_mappings: dict[str, str],
) -> ImportReport:
    candidates = _parse_export(broker_export)
    tree = etree.parse(str(source_file))
    root = tree.getroot()
    portfolio = _find_account(root, 'portfolio', portfolio_account_name)
    cash_account = _find_account(root, 'account', cash_account_name)
    to_import = [candidate for candidate in candidates if not _is_duplicate(root, candidate, portfolio, cash_account, ticker_mappings)]
    expected_net_cash_delta = sum((candidate.net_cash for candidate in to_import), Decimal('0'))

    if not dry_run:
        if output_file is None:
            raise InputError('pass --output or use --dry-run')
        if output_file.exists():
            raise InputError(f'Output file {output_file} already exists')
        for candidate in to_import:
            _append_candidate(root, candidate, portfolio, cash_account, ticker_mappings)
        tree.write(str(output_file), encoding='utf-8', xml_declaration=False, pretty_print=True)

    return ImportReport(
        parsed=len(candidates),
        duplicates=len(candidates) - len(to_import),
        unsupported=0,
        to_import=len(to_import),
        expected_net_cash_delta=expected_net_cash_delta,
        output_file=output_file if not dry_run else None,
    )


def _parse_export(path: Path) -> list[ImportCandidate]:
    if path.suffix.lower() == '.csv':
        return parse_csv(path)
    if path.suffix.lower() == '.xlsx':
        return parse_xlsx(path)
    raise InputError(f'Unsupported broker export format: {path.suffix}')


def _find_account(root: etree._Element, tag: str, name: str) -> etree._Element:
    allowed_tags = {'account', 'accountFrom', 'accountTo', 'referenceAccount'} if tag == 'account' else {'portfolio', 'portfolioFrom', 'portfolioTo'}
    matches = []
    for element in root.iter():
        if element.tag not in allowed_tags or element.get('id') is None:
            continue
        name_element = element.find('name')
        transactions = element.find('transactions')
        if name_element is not None and transactions is not None and name_element.text == name:
            matches.append(element)
    if matches:
        return max(matches, key=lambda item: len(list(item.iter('account-transaction'))) + len(list(item.iter('portfolio-transaction'))))
    raise InputError(f'{tag} account not found: {name}')


def _find_security(root: etree._Element, candidate: ImportCandidate, ticker_mappings: dict[str, str]) -> etree._Element | None:
    wanted_ticker = ticker_mappings.get(candidate.ticker or '', candidate.ticker)
    for security in root.iter('security'):
        isin = security.findtext('isin')
        ticker = security.findtext('tickerSymbol')
        if candidate.isin and isin == candidate.isin:
            return security
        if wanted_ticker and ticker == wanted_ticker:
            return security
    return None


def _is_duplicate(
    root: etree._Element,
    candidate: ImportCandidate,
    portfolio: etree._Element,
    cash_account: etree._Element,
    ticker_mappings: dict[str, str],
) -> bool:
    security = _find_security(root, candidate, ticker_mappings)
    security_id = security.get('id') if security is not None else None
    account = portfolio if candidate.is_trade else cash_account
    transaction_tag = 'portfolio-transaction' if candidate.is_trade else 'account-transaction'
    for transaction in account.iter(transaction_tag):
        if transaction.get('reference') is not None:
            continue
        if transaction.findtext('type') != candidate.transaction_type:
            continue
        security_ref = transaction.find('security')
        if security_id is not None and (security_ref is None or security_ref.get('reference') != security_id):
            continue
        if not candidate.is_trade:
            existing_note = transaction.findtext('note')
            if candidate.note is None or existing_note == candidate.note:
                return True
            continue
        if transaction.findtext('amount') != str(_money(candidate.gross_amount)):
            continue
        if transaction.findtext('date') != _format_date(candidate.date):
            continue
        if transaction.findtext('shares') != str(_shares(candidate.shares)):
            continue
        return True
    return False


def _append_candidate(
    root: etree._Element,
    candidate: ImportCandidate,
    portfolio: etree._Element,
    cash_account: etree._Element,
    ticker_mappings: dict[str, str],
) -> None:
    security = _find_security(root, candidate, ticker_mappings)
    if candidate.ticker is not None and security is None:
        raise InputError(f'Security not found for {candidate.ticker}')
    if candidate.is_trade:
        _append_trade(root, candidate, portfolio, cash_account, security)
    else:
        _append_cash_operation(root, candidate, cash_account, security)


def _append_trade(
    root: etree._Element,
    candidate: ImportCandidate,
    portfolio: etree._Element,
    cash_account: etree._Element,
    security: etree._Element | None,
) -> None:
    portfolio_transactions = _transactions_element(portfolio)
    cash_transactions = _transactions_element(cash_account)
    portfolio_id = _next_id(root)
    cross_id = _next_id(root, portfolio_id)
    account_transaction_id = _next_id(root, cross_id)

    portfolio_transaction = etree.SubElement(portfolio_transactions, 'portfolio-transaction', id=str(portfolio_id))
    _fill_common_transaction(portfolio_transaction, candidate, security)
    cross_entry = etree.SubElement(portfolio_transaction, 'crossEntry', {'class': 'buysell', 'id': str(cross_id)})
    etree.SubElement(cross_entry, 'portfolio', reference=portfolio.get('id'))
    etree.SubElement(cross_entry, 'portfolioTransaction', reference=str(portfolio_id))
    etree.SubElement(cross_entry, 'account', reference=cash_account.get('id'))
    account_transaction = etree.SubElement(cross_entry, 'accountTransaction', id=str(account_transaction_id))
    _fill_common_transaction(account_transaction, candidate, security, shares=Decimal('0'))
    etree.SubElement(account_transaction, 'crossEntry', {'class': 'buysell', 'reference': str(cross_id)})
    _append_tail_transaction_fields(account_transaction, candidate.transaction_type)
    etree.SubElement(portfolio_transaction, 'shares').text = str(_shares(candidate.shares))
    _append_fee_units(portfolio_transaction, candidate)
    _append_tail_transaction_fields(portfolio_transaction, candidate.transaction_type)
    etree.SubElement(cash_transactions, 'account-transaction', reference=str(account_transaction_id))


def _append_cash_operation(
    root: etree._Element,
    candidate: ImportCandidate,
    cash_account: etree._Element,
    security: etree._Element | None,
) -> None:
    transaction = etree.SubElement(_transactions_element(cash_account), 'account-transaction', id=str(_next_id(root)))
    _fill_common_transaction(transaction, candidate, security, shares=Decimal('0'))
    _append_fee_units(transaction, candidate)
    _append_tail_transaction_fields(transaction, candidate.transaction_type)


def _fill_common_transaction(
    transaction: etree._Element,
    candidate: ImportCandidate,
    security: etree._Element | None,
    shares: Decimal | None = None,
) -> None:
    etree.SubElement(transaction, 'uuid').text = str(uuid4())
    etree.SubElement(transaction, 'date').text = _format_date(candidate.date)
    etree.SubElement(transaction, 'currencyCode').text = candidate.currency
    etree.SubElement(transaction, 'amount').text = str(_money(candidate.gross_amount))
    if security is not None:
        etree.SubElement(transaction, 'security', reference=security.get('id'))
    if shares is not None:
        etree.SubElement(transaction, 'shares').text = str(_shares(shares))
    if candidate.note:
        etree.SubElement(transaction, 'note').text = candidate.note


def _append_fee_units(transaction: etree._Element, candidate: ImportCandidate) -> None:
    units = []
    if candidate.fee:
        units.append(('FEE', candidate.fee))
    if candidate.tax:
        units.append(('TAX', candidate.tax))
    if not units:
        return
    units_element = etree.SubElement(transaction, 'units')
    for unit_type, amount in units:
        unit = etree.SubElement(units_element, 'unit', type=unit_type)
        etree.SubElement(unit, 'amount', currency=candidate.currency, amount=str(_money(amount)))


def _append_tail_transaction_fields(transaction: etree._Element, transaction_type: str) -> None:
    etree.SubElement(transaction, 'updatedAt').text = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.%fZ')
    etree.SubElement(transaction, 'type').text = transaction_type


def _transactions_element(account: etree._Element) -> etree._Element:
    transactions = account.find('transactions')
    if transactions is None:
        transactions = etree.SubElement(account, 'transactions')
    return transactions


def _next_id(root: etree._Element, minimum: int | None = None) -> int:
    max_id = max((int(element.get('id')) for element in root.iter() if element.get('id', '').isdigit()), default=0)
    if minimum is not None:
        max_id = max(max_id, minimum)
    return max_id + 1


def _money(amount: Decimal) -> int:
    return int((amount * _MONEY_SCALE).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def _shares(amount: Decimal) -> int:
    return int((amount * _SHARE_SCALE).quantize(Decimal('1'), rounding=ROUND_HALF_UP))


def _format_date(value: datetime) -> str:
    return value.strftime('%Y-%m-%dT%H:%M')
