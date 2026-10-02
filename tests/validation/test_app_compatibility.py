from pathlib import Path

from pp_terminal.validation.app_compatibility import validate_app_compatibility


def test_rejects_forward_xstream_reference(tmp_path: Path) -> None:
    xml = tmp_path / 'forward.xml'
    xml.write_text('<client><portfolio-transaction><crossEntry reference="2"/></portfolio-transaction><crossEntry id="2"/></client>', encoding='utf-8')

    violations = validate_app_compatibility(xml)

    assert violations == ['line 1: reference="2" appears before id="2"']


def test_accepts_reference_defined_first(tmp_path: Path) -> None:
    xml = tmp_path / 'valid.xml'
    xml.write_text('<client><crossEntry id="2"/><portfolio-transaction><crossEntry reference="2"/></portfolio-transaction></client>', encoding='utf-8')

    assert not validate_app_compatibility(xml)
