"""Portfolio Performance app/XStream compatibility checks."""

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
