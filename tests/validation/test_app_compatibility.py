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


def test_rejects_transaction_defined_inline_and_listed_in_portfolio(tmp_path: Path) -> None:
    xml = tmp_path / 'inline.xml'
    xml.write_text(
        '<client id="1"><portfolios>'
        '<portfolio id="2"><uuid>a</uuid><transactions><portfolio-transaction id="3"><uuid>t-out</uuid>'
        '<crossEntry class="portfolio-transfer" id="4"><portfolioFrom reference="2"/>'
        '<transactionFrom id="5"><uuid>t-out</uuid></transactionFrom>'
        '<portfolioTo id="6"><uuid>b</uuid><transactions><portfolio-transaction id="7"><uuid>t-in</uuid></portfolio-transaction></transactions></portfolioTo>'
        '<transactionTo reference="7"/></crossEntry></portfolio-transaction></transactions></portfolio>'
        '<portfolio reference="6"/></portfolios></client>',
        encoding='utf-8',
    )

    violations = validate_app_compatibility(xml)

    assert 'transaction uuid t-out is defined 2 times' in violations
    assert 'crossEntry id="4": transactionFrom id="5" is not listed in the transactions of portfolioFrom id="2"' in violations


def test_rejects_duplicate_portfolio_definition(tmp_path: Path) -> None:
    xml = tmp_path / 'duplicate.xml'
    xml.write_text('<client id="1"><portfolio id="2"><uuid>p</uuid></portfolio><portfolio id="3"><uuid>p</uuid></portfolio></client>', encoding='utf-8')

    assert validate_app_compatibility(xml) == ['account/portfolio uuid p is defined 2 times']
