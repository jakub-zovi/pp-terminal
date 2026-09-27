from pathlib import Path

from typer.testing import CliRunner

from pp_terminal.main import app


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
    <portfolio id="6">
      <uuid>target-portfolio</uuid>
      <name>Target Wallet</name>
      <isRetired>false</isRetired>
      <referenceAccount reference="3"/>
      <transactions/>
      <attributes><map/></attributes>
      <updatedAt>2026-01-01T00:00:00.000000Z</updatedAt>
    </portfolio>
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
        'TRANSFER,2026-01-02T12:00,Source Wallet,Target Wallet,ETH-EUR,0.25,500,EUR,0.001,tx-1,Wallet transfer\n',
        encoding='utf-8',
    )
    output_file = tmp_path / 'imported.xml'

    result = runner.invoke(app, [
        '--file', str(xml_file), '--no-cache', 'import', 'portfolio-transfers', str(csv_file), '--output', str(output_file)
    ])

    assert result.exit_code == 0, result.output
    imported = output_file.read_text(encoding='utf-8')
    assert '<crossEntry class="portfolio-transfer"' in imported
    assert '<portfolioFrom reference="4"/>' in imported
    assert '<portfolioTo reference="6"/>' in imported
    assert '<type>TRANSFER_OUT</type>' in imported
    assert '<type>TRANSFER_IN</type>' in imported
    assert '<type>DELIVERY_OUTBOUND</type>' in imported
    assert 'tx-1' in imported


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
