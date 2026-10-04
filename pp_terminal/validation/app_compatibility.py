"""Portfolio Performance app/XStream compatibility checks."""
# pylint: disable=c-extension-no-member
from collections import Counter
from pathlib import Path

from lxml import etree

_TRANSACTION_TAGS = frozenset({
    'portfolio-transaction', 'portfolioTransaction', 'account-transaction', 'accountTransaction', 'transactionFrom', 'transactionTo',
})
_PORTFOLIO_TAGS = frozenset({'portfolio', 'portfolioFrom', 'portfolioTo'})
_ACCOUNT_TAGS = frozenset({'account', 'referenceAccount', 'accountFrom', 'accountTo'})
_TRANSFER_SIDES = {
    'portfolio-transfer': (('portfolioFrom', 'transactionFrom'), ('portfolioTo', 'transactionTo')),
    'account-transfer': (('accountFrom', 'transactionFrom'), ('accountTo', 'transactionTo')),
}


def validate_app_compatibility(xml_file: Path) -> list[str]:
    """Return violations that make Portfolio Performance reject or misread the XML."""
    return find_app_compatibility_violations(etree.parse(str(xml_file)).getroot())


def find_app_compatibility_violations(root: etree._Element) -> list[str]:
    elements = [element for element in root.iter() if isinstance(element.tag, str)]
    return (
        _forward_references(elements)
        + _duplicate_ids(elements)
        + _duplicate_uuids(elements, _TRANSACTION_TAGS, 'transaction')
        + _duplicate_uuids(elements, _PORTFOLIO_TAGS | _ACCOUNT_TAGS, 'account/portfolio')
        + _transaction_membership(elements)
    )


def _forward_references(elements: list[etree._Element]) -> list[str]:
    seen_ids: set[str] = set()
    violations = []
    for element in elements:
        reference = element.get('reference')
        if reference and reference not in seen_ids:
            violations.append(f'line {element.sourceline}: reference="{reference}" appears before id="{reference}"')
        identifier = element.get('id')
        if identifier:
            seen_ids.add(identifier)
    return violations


def _duplicate_ids(elements: list[etree._Element]) -> list[str]:
    counts = Counter(element.get('id') for element in elements if element.get('id'))
    return [f'id="{identifier}" is defined {count} times' for identifier, count in counts.items() if count > 1]


def _duplicate_uuids(elements: list[etree._Element], tags: frozenset[str], kind: str) -> list[str]:
    counts = Counter(
        element.findtext('uuid') for element in elements
        if element.tag in tags and element.get('id') and element.findtext('uuid')
    )
    return [f'{kind} uuid {uuid} is defined {count} times' for uuid, count in counts.items() if count > 1]


def _transaction_owners(elements: list[etree._Element]) -> dict[str, list[str]]:
    owners: dict[str, list[str]] = {}
    for container in elements:
        if container.tag in _PORTFOLIO_TAGS:
            entry_tag = 'portfolio-transaction'
        elif container.tag in _ACCOUNT_TAGS:
            entry_tag = 'account-transaction'
        else:
            continue
        transactions = container.find('transactions')
        if not container.get('id') or transactions is None:
            continue
        for entry in transactions.findall(entry_tag):
            owners.setdefault(_identifier(entry), []).append(container.get('id') or '')
    return owners


def _transaction_membership(elements: list[etree._Element]) -> list[str]:
    owners = _transaction_owners(elements)
    violations = [
        f'transaction id="{transaction_id}" is listed {len(containers)} times (containers {", ".join(containers)})'
        for transaction_id, containers in owners.items() if len(containers) > 1
    ]
    for cross_entry in elements:
        sides = _TRANSFER_SIDES.get(cross_entry.get('class') or '')
        if cross_entry.tag != 'crossEntry' or sides is None or not cross_entry.get('id'):
            continue
        for container_tag, transaction_tag in sides:
            container_id = _identifier(cross_entry.find(container_tag))
            transaction_id = _identifier(cross_entry.find(transaction_tag))
            if container_id not in owners.get(transaction_id, []):
                violations.append(
                    f'crossEntry id="{cross_entry.get("id")}": {transaction_tag} id="{transaction_id}" '
                    f'is not listed in the transactions of {container_tag} id="{container_id}"'
                )
    return violations


def _identifier(element: etree._Element | None) -> str:
    if element is None:
        return ''
    return element.get('id') or element.get('reference') or ''
