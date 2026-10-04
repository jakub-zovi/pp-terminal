from lxml import etree

from pp_terminal.data.xstream_id_references import reorder_id_references
from pp_terminal.validation.app_compatibility import find_app_compatibility_violations


def test_moves_definition_to_first_occurrence() -> None:
    root = etree.fromstring(  # pylint: disable=c-extension-no-member
        '<client id="1"><a><crossEntry reference="2"/></a><b><crossEntry id="2" class="x"><v>1</v></crossEntry></b></client>'
    )

    reordered = reorder_id_references(root)

    assert etree.tostring(reordered).decode().replace('\n', '').replace(' ', '') == (  # pylint: disable=c-extension-no-member
        '<clientid="1"><a><crossEntryclass="x"id="2"><v>1</v></crossEntry></a><b><crossEntryclass="x"reference="2"/></b></client>'
    )
    assert not find_app_compatibility_violations(reordered)
