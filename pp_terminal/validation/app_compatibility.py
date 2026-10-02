"""Portfolio Performance app/XStream compatibility checks."""

from copy import deepcopy
from pathlib import Path

from lxml import etree


def validate_app_compatibility(xml_file: Path) -> list[str]:
    """Return violations that can make Portfolio Performance reject the XML."""
    root = etree.parse(str(xml_file)).getroot()  # pylint: disable=c-extension-no-member
    seen_ids: set[str] = set()
    violations: list[str] = []
    for element in root.iter():
        reference = element.get('reference')
        if reference and reference not in seen_ids:
            violations.append(f'line {element.sourceline}: reference="{reference}" appears before id="{reference}"')
        identifier = element.get('id')
        if identifier:
            seen_ids.add(identifier)
    return violations


def repair_app_compatibility(source_file: Path, output_file: Path) -> list[str]:  # pylint: disable=too-many-locals,too-many-branches,too-many-statements
    """Rewrite forward portfolio-transfer references into app-loadable XML."""
    tree = etree.parse(str(source_file))  # pylint: disable=c-extension-no-member
    root = tree.getroot()
    original_transactions = {element.get('id'): element for element in root.iter('portfolio-transaction') if element.get('id')}

    for reference_element in list(root.xpath('.//crossEntry[@reference]')):
        reference = reference_element.get('reference')
        before = list(root.iter())
        if reference in {element.get('id') for element in before[:before.index(reference_element)]}:
            continue
        definition = next((element for element in root.iter('crossEntry') if element.get('id') == reference), None)
        if definition is None:
            continue
        target_transaction = reference_element.getparent()
        while target_transaction is not None and target_transaction.tag != 'portfolio-transaction':
            target_transaction = target_transaction.getparent()
        source_reference = definition.find('transactionFrom')
        if target_transaction is None or source_reference is None or source_reference.get('reference') is None:
            continue
        source_id = source_reference.get('reference')
        source_transaction = original_transactions.get(source_id)
        if source_transaction is None:
            continue

        repaired_definition = deepcopy(definition)
        repaired_source_reference = repaired_definition.find('transactionFrom')
        repaired_definition.remove(repaired_source_reference)
        inline_source = deepcopy(source_transaction)
        nested_cross_entry = inline_source.find('crossEntry')
        if nested_cross_entry is not None:
            nested_cross_entry.attrib.pop('id', None)
            nested_cross_entry.set('reference', reference)
        inline_source.tag = 'transactionFrom'
        insertion_index = list(repaired_definition).index(repaired_definition.find('portfolioFrom')) + 2
        repaired_definition.insert(insertion_index, inline_source)
        target_transaction.replace(reference_element, repaired_definition)
        parent = source_transaction.getparent()
        if parent is not None:
            parent.remove(source_transaction)

    for cross_entry in root.iter('crossEntry'):
        source_reference = cross_entry.find('transactionFrom')
        if source_reference is None or source_reference.get('reference') is None:
            continue
        before = list(root.iter())
        if source_reference.get('reference') in {element.get('id') for element in before[:before.index(cross_entry)]}:
            continue
        source_transaction = original_transactions.get(source_reference.get('reference'))
        if source_transaction is None:
            continue
        inline_source = deepcopy(source_transaction)
        nested_cross_entry = inline_source.find('crossEntry')
        if nested_cross_entry is not None:
            nested_cross_entry.attrib.pop('id', None)
            nested_cross_entry.set('reference', cross_entry.get('id'))
        inline_source.tag = 'transactionFrom'
        cross_entry.replace(source_reference, inline_source)

    inline_ids = {element.get('id') for element in root.iter('transactionFrom') if element.get('id')}
    seen_inline_ids: set[str] = set()
    for transaction_from in list(root.iter('transactionFrom')):
        identifier = transaction_from.get('id')
        if identifier in seen_inline_ids:
            parent = transaction_from.getparent()
            if parent is not None:
                parent.remove(transaction_from)
        elif identifier:
            seen_inline_ids.add(identifier)
    for transaction in list(root.iter('portfolio-transaction')):
        if transaction.get('id') not in inline_ids:
            continue
        parent = transaction.getparent()
        ancestor = parent
        nested = False
        while ancestor is not None:
            if ancestor.tag == 'transactionFrom':
                nested = True
                break
            ancestor = ancestor.getparent()
        if parent is not None and not nested:
            parent.remove(transaction)

    tree.write(str(output_file), encoding='utf-8', xml_declaration=False, pretty_print=True)
    return validate_app_compatibility(output_file)
