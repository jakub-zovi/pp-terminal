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
    assert '<accountTransaction id=' in imported
    assert '<account-transaction reference=' in imported
    assert '<type>SELL</type>' in imported


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
