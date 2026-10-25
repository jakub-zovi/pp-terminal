"""
    Copyright (C) 2025-26 Dipl.-Ing. Christoph Massmann <chris@dev-investor.de>

    This file is part of pp-terminal.
"""
# pylint: disable=too-many-arguments,too-many-positional-arguments,c-extension-no-member
from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from uuid import uuid4

from lxml import etree

from pp_terminal.data.broker_import.ibkr_csv import parse_csv
from pp_terminal.data.broker_import.models import ImportCandidate, ImportReport
from pp_terminal.data.broker_import.xtb_xlsx import parse_xlsx
from pp_terminal.data.xstream_id_references import reorder_id_references
from pp_terminal.exceptions import InputError
from pp_terminal.validation.app_compatibility import find_app_compatibility_violations

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
    cash_account_map: dict[str, str] | None = None,
) -> ImportReport:
    candidates = _parse_export(broker_export)
    root = etree.parse(str(source_file)).getroot()
    portfolio = _find_account(root, 'portfolio', portfolio_account_name)
    primary_cash_account = _find_account(root, 'account', cash_account_name)
    cash_accounts = _build_cash_accounts(root, primary_cash_account, cash_account_map or {})
    to_import = [
        candidate for candidate in candidates
        if not _is_duplicate(root, candidate, portfolio, cash_accounts, primary_cash_account, ticker_mappings)
    ]
    expected_net_cash_delta = sum((candidate.net_cash for candidate in to_import), Decimal('0'))

    if not dry_run:
        _write_output(root, to_import, portfolio, cash_accounts, primary_cash_account, ticker_mappings, output_file)

    return ImportReport(
        parsed=len(candidates),
        duplicates=len(candidates) - len(to_import),
        unsupported=0,
        to_import=len(to_import),
        expected_net_cash_delta=expected_net_cash_delta,
        output_file=output_file if not dry_run else None,
    )


def _build_cash_accounts(
    root: etree._Element,
    primary_cash_account: etree._Element,
    cash_account_map: dict[str, str],
) -> dict[str, etree._Element]:
    cash_accounts = {primary_cash_account.findtext('currencyCode'): primary_cash_account}
    for currency, account_name in cash_account_map.items():
        cash_accounts[currency] = _find_account(root, 'account', account_name)
    return cash_accounts


def _resolve_cash_account(cash_accounts: dict[str, etree._Element], currency: str | None) -> etree._Element:
    account = cash_accounts.get(currency) if currency else None
    if account is None:
        raise InputError(f'No cash account mapped for currency {currency}; pass --cash-account-map {currency}=<account name>')
    return account


def _write_output(
    root: etree._Element,
    to_import: list[ImportCandidate],
    portfolio: etree._Element,
    cash_accounts: dict[str, etree._Element],
    primary_cash_account: etree._Element,
    ticker_mappings: dict[str, str],
    output_file: Path | None,
) -> None:
    if output_file is None:
        raise InputError('pass --output or use --dry-run')
    if output_file.exists():
        raise InputError(f'Output file {output_file} already exists')
    for candidate in to_import:
        _append_candidate(root, candidate, portfolio, cash_accounts, primary_cash_account, ticker_mappings)
    serialized = reorder_id_references(root)
    violations = find_app_compatibility_violations(serialized)
    if violations:
        raise InputError('Refusing to write XML Portfolio Performance would reject: ' + '; '.join(violations[:5]))
    etree.ElementTree(serialized).write(str(output_file), encoding='utf-8', xml_declaration=False)


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
    cash_accounts: dict[str, etree._Element],
    primary_cash_account: etree._Element,
    ticker_mappings: dict[str, str],
) -> bool:
    if candidate.is_currency_transfer:
        return _is_duplicate_currency_transfer(candidate, cash_accounts)
    security = _find_security(root, candidate, ticker_mappings)
    security_id = security.get('id') if security is not None else None
    account = portfolio if candidate.is_trade else cash_accounts.get(candidate.currency, primary_cash_account)
    transaction_tag = 'portfolio-transaction' if candidate.is_trade else 'account-transaction'
    for transaction in account.iter(transaction_tag):
        if transaction.get('reference') is not None:
            continue
        if transaction.findtext('type') != candidate.transaction_type:
            continue
        security_ref = transaction.find('security')
        if security_id is not None and (security_ref is None or security_ref.get('reference') != security_id):
            continue
        if _is_duplicate_match(transaction, candidate):
            return True
    return False


def _is_duplicate_match(transaction: etree._Element, candidate: ImportCandidate) -> bool:
    if candidate.is_trade:
        return bool(
            transaction.findtext('amount') == str(_money(_trade_amount(candidate)))
            and transaction.findtext('date') == _format_date(candidate.date)
            and transaction.findtext('shares') == str(_shares(candidate.shares))
        )
    if candidate.transaction_type in {'DEPOSIT', 'REMOVAL'}:
        return bool(
            transaction.findtext('date') == _format_date(candidate.date)
            and transaction.findtext('amount') == str(_money(candidate.gross_amount))
        )
    existing_note = transaction.findtext('note')
    return candidate.note is None or existing_note == candidate.note


def _is_duplicate_currency_transfer(candidate: ImportCandidate, cash_accounts: dict[str, etree._Element]) -> bool:
    from_account = cash_accounts.get(candidate.currency)
    if from_account is None:
        return False
    for transaction in from_account.iter('account-transaction'):
        if transaction.get('reference') is not None:
            continue
        if transaction.findtext('type') != 'TRANSFER_OUT':
            continue
        if transaction.findtext('date') != _format_date(candidate.date):
            continue
        if transaction.findtext('amount') != str(_money(candidate.gross_amount)):
            continue
        return True
    return False


def _append_candidate(
    root: etree._Element,
    candidate: ImportCandidate,
    portfolio: etree._Element,
    cash_accounts: dict[str, etree._Element],
    primary_cash_account: etree._Element,
    ticker_mappings: dict[str, str],
) -> None:
    if candidate.is_currency_transfer:
        from_account = _resolve_cash_account(cash_accounts, candidate.currency)
        to_account = _resolve_cash_account(cash_accounts, candidate.to_currency)
        _append_currency_transfer(root, candidate, from_account, to_account)
        return
    security = _find_security(root, candidate, ticker_mappings)
    if candidate.ticker is not None and security is None:
        raise InputError(f'Security not found for {candidate.ticker}')
    cash_account = cash_accounts.get(candidate.currency, primary_cash_account)
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

    total_amount = _trade_amount(candidate)
    portfolio_transaction = etree.SubElement(portfolio_transactions, 'portfolio-transaction', id=str(portfolio_id))
    _fill_common_transaction(portfolio_transaction, candidate, security, amount=total_amount)
    cross_entry = etree.SubElement(portfolio_transaction, 'crossEntry', {'class': 'buysell', 'id': str(cross_id)})
    etree.SubElement(cross_entry, 'portfolio', reference=portfolio.get('id'))
    etree.SubElement(cross_entry, 'portfolioTransaction', reference=str(portfolio_id))
    etree.SubElement(cross_entry, 'account', reference=cash_account.get('id'))
    account_transaction = etree.SubElement(cross_entry, 'accountTransaction', id=str(account_transaction_id))
    _fill_common_transaction(account_transaction, candidate, security, shares=Decimal('0'), amount=total_amount)
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


def _append_currency_transfer(
    root: etree._Element,
    candidate: ImportCandidate,
    from_account: etree._Element,
    to_account: etree._Element,
) -> None:
    from_transactions = _transactions_element(from_account)
    to_transactions = _transactions_element(to_account)
    from_id = _next_id(root)
    transfer_id = _next_id(root, from_id)
    to_id = _next_id(root, transfer_id)

    from_transaction = etree.SubElement(from_transactions, 'account-transaction', id=str(from_id))
    _fill_common_transaction(from_transaction, candidate, security=None, shares=Decimal('0'))
    cross_entry = etree.SubElement(from_transaction, 'crossEntry', {'class': 'account-transfer', 'id': str(transfer_id)})
    etree.SubElement(cross_entry, 'accountFrom', reference=from_account.get('id'))
    etree.SubElement(cross_entry, 'transactionFrom', reference=str(from_id))
    etree.SubElement(cross_entry, 'accountTo', reference=to_account.get('id'))
    to_transaction = etree.SubElement(cross_entry, 'transactionTo', id=str(to_id))
    to_candidate = replace(candidate, currency=candidate.to_currency or candidate.currency, gross_amount=(candidate.to_amount or Decimal('0')) - candidate.fee)
    _fill_common_transaction(to_transaction, to_candidate, security=None, shares=Decimal('0'))
    etree.SubElement(to_transaction, 'crossEntry', {'class': 'account-transfer', 'reference': str(transfer_id)})
    _append_tail_transaction_fields(to_transaction, 'TRANSFER_IN')
    _append_gross_value_unit(from_transaction, candidate)
    _append_fee_units(to_transaction, to_candidate)
    _append_tail_transaction_fields(from_transaction, 'TRANSFER_OUT')
    etree.SubElement(to_transactions, 'account-transaction', reference=str(to_id))


def _append_gross_value_unit(transaction: etree._Element, candidate: ImportCandidate) -> None:
    units = etree.SubElement(transaction, 'units')
    unit = etree.SubElement(units, 'unit', type='GROSS_VALUE')
    etree.SubElement(unit, 'amount', currency=candidate.currency, amount=str(_money(candidate.gross_amount)))
    if candidate.to_currency and candidate.to_amount:
        etree.SubElement(unit, 'forex', currency=candidate.to_currency, amount=str(_money(candidate.to_amount)))
        exchange_rate = candidate.gross_amount / candidate.to_amount
        etree.SubElement(unit, 'exchangeRate').text = str(exchange_rate.normalize())


def _trade_amount(candidate: ImportCandidate) -> Decimal:
    # Portfolio Performance's transaction `amount` is the actual net cash impact, not the
    # gross trade value: BUY adds fee/tax to the cost, SELL subtracts fee/tax from proceeds.
    if candidate.transaction_type == 'SELL':
        return candidate.gross_amount - candidate.fee - candidate.tax
    return candidate.gross_amount + candidate.fee + candidate.tax


def _fill_common_transaction(
    transaction: etree._Element,
    candidate: ImportCandidate,
    security: etree._Element | None,
    shares: Decimal | None = None,
    amount: Decimal | None = None,
) -> None:
    etree.SubElement(transaction, 'uuid').text = str(uuid4())
    etree.SubElement(transaction, 'date').text = _format_date(candidate.date)
    etree.SubElement(transaction, 'currencyCode').text = candidate.currency
    etree.SubElement(transaction, 'amount').text = str(_money(amount if amount is not None else candidate.gross_amount))
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
