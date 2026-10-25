"""
    Copyright (C) 2025-26 Dipl.-Ing. Christoph Massmann <chris@dev-investor.de>

    This file is part of pp-terminal.

    pp-terminal is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    pp-terminal is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with pp-terminal. If not, see <http://www.gnu.org/licenses/>.
"""
from pathlib import Path

from typer.testing import CliRunner

from pp_terminal.main import app


def test_import_transactions_command_is_available() -> None:
    runner = CliRunner()

    result = runner.invoke(app, ['import', '--help'])

    assert result.exit_code == 0
    assert 'transactions' in result.output


def test_import_transactions_dry_run_does_not_write_output(tmp_path: Path) -> None:
    runner = CliRunner()
    xml_file = Path('tests/fixtures/import_base.ids.xml')
    csv_file = Path('tests/fixtures/broker_import/ibkr_trade.csv')
    output_file = tmp_path / 'imported.xml'

    result = runner.invoke(app, [
        '--file', str(xml_file), '--no-cache', 'import', 'transactions', str(csv_file),
        '--portfolio-account', 'Test Depot', '--cash-account', 'Test Cash', '--output', str(output_file), '--dry-run'
    ])

    assert result.exit_code == 0
    assert not output_file.exists()
    assert 'to_import: 1' in result.output


def test_import_transactions_writes_new_xml_without_touching_source(tmp_path: Path) -> None:
    runner = CliRunner()
    xml_file = Path('tests/fixtures/import_base.ids.xml')
    csv_file = Path('tests/fixtures/broker_import/ibkr_trade.csv')
    output_file = tmp_path / 'imported.xml'
    original = xml_file.read_text(encoding='utf-8')

    result = runner.invoke(app, [
        '--file', str(xml_file), '--no-cache', 'import', 'transactions', str(csv_file),
        '--portfolio-account', 'Test Depot', '--cash-account', 'Test Cash', '--output', str(output_file)
    ])

    assert result.exit_code == 0, result.output
    assert xml_file.read_text(encoding='utf-8') == original
    imported = output_file.read_text(encoding='utf-8')
    assert '<portfolio-transaction id=' in imported
    assert '<account-transaction id=' in imported
    assert '<accountTransaction reference=' in imported
    assert '<type>SELL</type>' in imported


def test_import_transactions_amount_is_net_cash_impact_not_gross(tmp_path: Path) -> None:
    # ibkr_trade.csv: SELL, TradeMoney/Proceeds=104.18, IBCommission=-0.353995358
    # PP's `amount` must be the net cash impact (gross - fee for a SELL), not the gross value alone.
    runner = CliRunner()
    xml_file = Path('tests/fixtures/import_base.ids.xml')
    csv_file = Path('tests/fixtures/broker_import/ibkr_trade.csv')
    output_file = tmp_path / 'imported.xml'

    result = runner.invoke(app, [
        '--file', str(xml_file), '--no-cache', 'import', 'transactions', str(csv_file),
        '--portfolio-account', 'Test Depot', '--cash-account', 'Test Cash', '--output', str(output_file)
    ])

    assert result.exit_code == 0, result.output
    imported = output_file.read_text(encoding='utf-8')
    assert '<amount>10383</amount>' in imported
    assert '<amount>10418</amount>' not in imported


def test_import_transactions_skips_duplicate_on_second_run(tmp_path: Path) -> None:
    runner = CliRunner()
    xml_file = Path('tests/fixtures/import_base.ids.xml')
    csv_file = Path('tests/fixtures/broker_import/ibkr_trade.csv')
    first_output = tmp_path / 'first.xml'
    second_output = tmp_path / 'second.xml'

    first = runner.invoke(app, [
        '--file', str(xml_file), '--no-cache', 'import', 'transactions', str(csv_file),
        '--portfolio-account', 'Test Depot', '--cash-account', 'Test Cash', '--output', str(first_output)
    ])
    assert first.exit_code == 0, first.output

    second = runner.invoke(app, [
        '--file', str(first_output), '--no-cache', 'import', 'transactions', str(csv_file),
        '--portfolio-account', 'Test Depot', '--cash-account', 'Test Cash', '--output', str(second_output), '--dry-run'
    ])

    assert second.exit_code == 0, second.output
    assert 'duplicates: 1' in second.output
    assert 'to_import: 0' in second.output


def test_import_transactions_ibkr_does_not_treat_cash_fx_row_as_stock_trade(tmp_path: Path) -> None:
    # EUR.CZK is a currency conversion (AssetClass=CASH), not a security trade of a fake
    # 'EUR.CZK' stock. It is still imported, but as a CURRENCY_TRANSFER, not BUY/SELL.
    runner = CliRunner()
    xml_file = Path('tests/fixtures/import_base.ids.xml')
    csv_file = Path('tests/fixtures/broker_import/ibkr_trade_with_fx.csv')
    output_file = tmp_path / 'imported.xml'

    result = runner.invoke(app, [
        '--file', str(xml_file), '--no-cache', 'import', 'transactions', str(csv_file),
        '--portfolio-account', 'Test Depot', '--cash-account', 'Test Cash',
        '--cash-account-map', 'CZK=Test Cash', '--output', str(output_file), '--dry-run'
    ])

    assert result.exit_code == 0, result.output
    assert 'parsed: 2' in result.output
    assert 'to_import: 2' in result.output


def test_import_transactions_ibkr_fx_conversion_writes_account_transfer(tmp_path: Path) -> None:
    # EUR.USD BUY: 100 EUR bought for 110 USD, 0.5 EUR commission.
    runner = CliRunner()
    xml_file = Path('tests/fixtures/import_base.ids.xml')
    csv_file = Path('tests/fixtures/broker_import/ibkr_fx_conversion.csv')
    output_file = tmp_path / 'imported.xml'

    result = runner.invoke(app, [
        '--file', str(xml_file), '--no-cache', 'import', 'transactions', str(csv_file),
        '--portfolio-account', 'Test Depot', '--cash-account', 'Test Cash',
        '--cash-account-map', 'EUR=Test Cash EUR', '--output', str(output_file)
    ])

    assert result.exit_code == 0, result.output
    imported = output_file.read_text(encoding='utf-8')
    assert '<type>TRANSFER_OUT</type>' in imported
    assert '<type>TRANSFER_IN</type>' in imported
    assert '<amount>11000</amount>' in imported  # USD leg: 110.00 leaving Test Cash
    assert '<amount>9950</amount>' in imported  # EUR leg: 100.00 - 0.50 fee = 99.50 into Test Cash EUR
    assert 'class="account-transfer"' in imported


def test_import_transactions_ibkr_fx_conversion_dry_run_is_idempotent(tmp_path: Path) -> None:
    runner = CliRunner()
    xml_file = Path('tests/fixtures/import_base.ids.xml')
    csv_file = Path('tests/fixtures/broker_import/ibkr_fx_conversion.csv')
    first_output = tmp_path / 'first.xml'

    first = runner.invoke(app, [
        '--file', str(xml_file), '--no-cache', 'import', 'transactions', str(csv_file),
        '--portfolio-account', 'Test Depot', '--cash-account', 'Test Cash',
        '--cash-account-map', 'EUR=Test Cash EUR', '--output', str(first_output)
    ])
    assert first.exit_code == 0, first.output

    second = runner.invoke(app, [
        '--file', str(first_output), '--no-cache', 'import', 'transactions', str(csv_file),
        '--portfolio-account', 'Test Depot', '--cash-account', 'Test Cash',
        '--cash-account-map', 'EUR=Test Cash EUR', '--dry-run'
    ])
    assert second.exit_code == 0, second.output
    assert 'duplicates: 1' in second.output
    assert 'to_import: 0' in second.output


def test_import_transactions_ibkr_cash_deposit_from_activity_statement(tmp_path: Path) -> None:
    # Multi-table IBKR "Activity Statement" export: the deposit row's header reappears
    # mid-file with a different column schema than the trades table.
    runner = CliRunner()
    xml_file = Path('tests/fixtures/import_base.ids.xml')
    csv_file = Path('tests/fixtures/broker_import/ibkr_cash_deposit.csv')
    output_file = tmp_path / 'imported.xml'

    result = runner.invoke(app, [
        '--file', str(xml_file), '--no-cache', 'import', 'transactions', str(csv_file),
        '--portfolio-account', 'Test Depot', '--cash-account', 'Test Cash', '--output', str(output_file)
    ])

    assert result.exit_code == 0, result.output
    assert 'parsed: 1' in result.output
    assert 'to_import: 1' in result.output
    imported = output_file.read_text(encoding='utf-8')
    assert '<type>DEPOSIT</type>' in imported
    assert '<amount>100000</amount>' in imported


def test_import_transactions_xtb_parses_shares_with_ticker_in_comment(tmp_path: Path) -> None:
    runner = CliRunner()
    xml_file = Path('tests/fixtures/import_base.ids.xml')
    xlsx_file = Path('tests/fixtures/broker_import/xtb_cash_operations.xlsx')
    output_file = tmp_path / 'imported.xml'

    result = runner.invoke(app, [
        '--file', str(xml_file), '--no-cache', 'import', 'transactions', str(xlsx_file),
        '--portfolio-account', 'Test Depot', '--cash-account', 'Test Cash', '--output', str(output_file)
    ])

    assert result.exit_code == 0, result.output
    assert 'to_import: 1' in result.output
    imported = output_file.read_text(encoding='utf-8')
    assert '<shares>200000000</shares>' in imported
