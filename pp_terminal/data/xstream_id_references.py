"""
    Copyright (C) 2025-26 Dipl.-Ing. Christoph Massmann <chris@dev-investor.de>

    This file is part of pp-terminal.
"""
# pylint: disable=c-extension-no-member
from collections.abc import Iterator

from lxml import etree


def reorder_id_references(root: etree._Element) -> etree._Element:
    """Re-serializes an XStream ID_REFERENCES object graph so each object is defined at its first occurrence.

    Every element carrying an id is an object, every element carrying a reference points to one. The graph
    (which slot points to which object) is preserved exactly; only the position of each definition changes,
    the same way XStream itself writes the graph: depth-first, define on first encounter, reference afterwards.
    """
    definitions = {element.get('id'): element for element in root.iter() if isinstance(element.tag, str) and element.get('id')}
    emitted: set[str] = set()

    new_root, children = _open(root, None, definitions, emitted)
    stack: list[tuple[etree._Element, Iterator[etree._Element]]] = [(new_root, children or iter(()))]
    while stack:
        parent, pending = stack[-1]
        slot = next(pending, None)
        if slot is None:
            stack.pop()
            continue
        if not isinstance(slot.tag, str):
            continue
        element, grandchildren = _open(slot, parent, definitions, emitted)
        if grandchildren is not None:
            stack.append((element, grandchildren))

    etree.indent(new_root, space='  ')
    return new_root


def _open(
    slot: etree._Element,
    parent: etree._Element | None,
    definitions: dict[str | None, etree._Element],
    emitted: set[str],
) -> tuple[etree._Element, Iterator[etree._Element] | None]:
    object_id = slot.get('id') or slot.get('reference')
    source = slot if object_id is None else definitions.get(object_id)
    if source is None:
        raise ValueError(f'reference="{object_id}" in line {slot.sourceline} has no definition')

    attributes = {key: value for key, value in source.attrib.items() if key not in ('id', 'reference')}
    attributes.update({key: value for key, value in slot.attrib.items() if key not in ('id', 'reference')})
    element = etree.Element(slot.tag, attributes) if parent is None else etree.SubElement(parent, slot.tag, attributes)

    if object_id is not None and object_id in emitted:
        element.set('reference', object_id)
        return element, None
    if object_id is not None:
        emitted.add(object_id)
        element.set('id', object_id)

    if len(source) == 0:
        element.text = source.text
    return element, iter(source)
