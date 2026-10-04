from pathlib import Path

from lxml import etree
from typer.testing import CliRunner

from pp_terminal.main import app
from pp_terminal.validation.app_compatibility import validate_app_compatibility


def _xml_fixture(path: Path) -> None:
    path.write_text('''<client id="1">
  <version>66</version>
  <baseCurrency>EUR</baseCurrency>
  <securities>
    <security id="2">
      <uuid>eth-security</uuid>
      <name>Ethereum EUR</name>
      <currencyCode>EUR</currencyCode>
      <tickerSymbol>ETH-EUR</tickerSymbol>
      <feed>MANUAL</feed>
      <prices/>
      <attributes><map/></attributes>
      <events/>
      <isRetired>false</isRetired>
      <updatedAt>2026-01-01T00:00:00.000000Z</updatedAt>
    </security>
  </securities>
  <watchlists/>
  <accounts>
    <account id="3">
      <uuid>cash-account</uuid>
      <name>Cash</name>
      <currencyCode>EUR</currencyCode>
      <isRetired>false</isRetired>
      <transactions/>
      <attributes><map/></attributes>
      <updatedAt>2026-01-01T00:00:00.000000Z</updatedAt>
    </account>
  </accounts>
  <portfolios>
    <portfolio id="99">
      <uuid>container-portfolio</uuid>
      <name>Container</name>
      <isRetired>false</isRetired>
      <referenceAccount reference="3"/>
      <transactions>
        <portfolio-transaction id="100">
          <uuid>container-transaction</uuid>
          <date>2025-12-31T00:00</date>
          <currencyCode>EUR</currencyCode>
          <amount>0</amount>
          <security reference="2"/>
          <crossEntry class="portfolio-transfer" id="101">
            <portfolioFrom reference="99"/>
            <transactionFrom reference="100"/>
            <portfolioTo id="6">
              <uuid>target-portfolio</uuid>
              <name>Target Wallet</name>
              <isRetired>false</isRetired>
              <referenceAccount reference="3"/>
              <transactions>
                <portfolio-transaction id="103">
                  <uuid>container-transaction-in</uuid>
                  <date>2025-12-31T00:00</date>
                  <currencyCode>EUR</currencyCode>
                  <amount>0</amount>
                  <security reference="2"/>
                  <crossEntry class="portfolio-transfer" reference="101"/>
                  <shares>0</shares>
                  <updatedAt>2026-01-01T00:00:00.000000Z</updatedAt>
                  <type>TRANSFER_IN</type>
                </portfolio-transaction>
              </transactions>
              <attributes><map/></attributes>
              <updatedAt>2026-01-01T00:00:00.000000Z</updatedAt>
            </portfolioTo>
            <transactionTo reference="103"/>
          </crossEntry>
          <shares>0</shares>
          <updatedAt>2026-01-01T00:00:00.000000Z</updatedAt>
          <type>TRANSFER_OUT</type>
        </portfolio-transaction>
      </transactions>
      <attributes><map/></attributes>
      <updatedAt>2026-01-01T00:00:00.000000Z</updatedAt>
    </portfolio>
    <portfolio id="4">
      <uuid>source-portfolio</uuid>
      <name>Source Wallet</name>
      <isRetired>false</isRetired>
      <referenceAccount reference="3"/>
      <transactions>
        <portfolio-transaction id="5">
          <uuid>initial-delivery</uuid>
          <date>2026-01-01T00:00</date>
          <currencyCode>EUR</currencyCode>
          <amount>100000</amount>
          <security reference="2"/>
          <shares>100000000</shares>
          <note>Initial ETH</note>
          <updatedAt>2026-01-01T00:00:00.000000Z</updatedAt>
          <type>DELIVERY_INBOUND</type>
        </portfolio-transaction>
      </transactions>
      <attributes><map/></attributes>
      <updatedAt>2026-01-01T00:00:00.000000Z</updatedAt>
    </portfolio>
    <portfolio reference="6"/>
  </portfolios>
  <plans/>
  <taxonomies/>
  <dashboards/>
  <properties/>
  <settings><bookmarks/><attributeTypes/><configurationSets/></settings>
</client>
''', encoding='utf-8')


def test_import_portfolio_transfer_csv_writes_valid_transfer_and_fee(tmp_path: Path) -> None:
    runner = CliRunner()
    xml_file = tmp_path / 'base.xml'
    _xml_fixture(xml_file)
    csv_file = tmp_path / 'transfers.csv'
    csv_file.write_text(
        'type,date,source_portfolio,target_portfolio,security,shares,amount,currency,fee_shares,external_id,note\n'
        'TRANSFER,2026-01-02T12:00,Source Wallet,Target Wallet,ETH-EUR,0.25,500,EUR,0.001,tx-1,Wallet transfer\n'
        'TRANSFER,2026-01-03T12:00,Source Wallet,Target Wallet,ETH-EUR,0.10,200,EUR,0,tx-2,Wallet transfer 2\n',
        encoding='utf-8',
    )
    output_file = tmp_path / 'imported.xml'

    result = runner.invoke(app, [
        '--file', str(xml_file), '--no-cache', 'import', 'portfolio-transfers', str(csv_file), '--output', str(output_file)
    ])

    assert result.exit_code == 0, result.output
    assert not validate_app_compatibility(output_file)
    root = etree.parse(str(output_file)).getroot()  # pylint: disable=c-extension-no-member
    assert _legs(root, 'Source Wallet') == [('TRANSFER_OUT', 'tx-1'), ('DELIVERY_OUTBOUND', 'tx-1:fee'), ('TRANSFER_OUT', 'tx-2')]
    assert _legs(root, 'Target Wallet') == [('TRANSFER_IN', 'tx-1'), ('TRANSFER_IN', 'tx-2')]
    assert sum(1 for element in root.iter('portfolio', 'portfolioFrom', 'portfolioTo') if element.findtext('uuid') == 'target-portfolio') == 1

    accounts = runner.invoke(app, ['--file', str(output_file), '--no-cache', '--output', 'json', 'view', 'securities', '--in-stock'])
    assert accounts.exit_code == 0, accounts.output


def _legs(root: etree._Element, name: str) -> list[tuple[str, str]]:
    definition = next(element for element in root.iter('portfolio', 'portfolioFrom', 'portfolioTo') if element.get('id') and element.findtext('name') == name)
    by_id = {element.get('id'): element for element in root.iter() if element.get('id')}
    legs = []
    for entry in definition.find('transactions'):
        transaction = by_id[entry.get('id') or entry.get('reference')]
        note = transaction.findtext('note') or ''
        if 'external_id=' in note:
            legs.append((transaction.findtext('type'), note.split('external_id=', 1)[1]))
    return legs


def test_import_portfolio_transfer_csv_dry_run_reports_without_writing(tmp_path: Path) -> None:
    runner = CliRunner()
    xml_file = tmp_path / 'base.xml'
    _xml_fixture(xml_file)
    csv_file = tmp_path / 'transfers.csv'
    csv_file.write_text(
        'type,date,source_portfolio,target_portfolio,security,shares,amount,currency,fee_shares,external_id,note\n'
        'TRANSFER,2026-01-02T12:00,Source Wallet,Target Wallet,ETH-EUR,0.25,500,EUR,0,tx-1,Wallet transfer\n',
        encoding='utf-8',
    )
    output_file = tmp_path / 'imported.xml'

    result = runner.invoke(app, [
        '--file', str(xml_file), '--no-cache', 'import', 'portfolio-transfers', str(csv_file), '--output', str(output_file), '--dry-run'
    ])

    assert result.exit_code == 0, result.output
    assert not output_file.exists()
    assert 'to_import: 1' in result.output
