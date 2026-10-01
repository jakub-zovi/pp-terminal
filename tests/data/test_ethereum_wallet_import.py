from decimal import Decimal
from pathlib import Path

from pp_terminal.data.ethereum_wallet_import import classify_ethereum_wallet_exports


def test_classify_ethereum_wallet_exports_matches_internal_transfer(tmp_path: Path) -> None:
    exodus = tmp_path / 'exodus.csv'
    exodus.write_text(
        'DATE,TYPE,FROMPORTFOLIO,TOPORTFOLIO,OUTAMOUNT,OUTCURRENCY,FEEAMOUNT,FEECURRENCY,FROMADDRESS,TOADDRESS,OUTTXID,OUTTXURL,INAMOUNT,INCURRENCY,INTXID,INTXURL,ORDERID,PERSONALNOTE\n'
        '2026-01-01T10:00:00.000Z,withdrawal,exodus_0,,-0.5,ETH,-0.001,ETH,,0xtrezor,tx-1,,, ,,, ,\n',
        encoding='utf-8',
    )
    trezor = tmp_path / 'trezor.csv'
    trezor.write_text(
        'Timestamp,Date,Time,Type,Transaction ID,Fee,Fee unit,Address,Label,Amount,Amount unit,Fiat (EUR),Other\n'
        '1767261600,01/01/2026,11:00:00 GMT+1,RECV,tx-1,,,0xexodus,,0.5,ETH,1000,\n',
        encoding='utf-8',
    )

    candidates, ignored = classify_ethereum_wallet_exports(
        exodus_csv=exodus,
        trezor_csv=trezor,
        exodus_account='Exodus',
        trezor_account='Trezor',
        stake_account='Everstake',
        stake_address='0xstake',
        security='ETH-EUR',
        staking_return_txids=set(),
    )

    assert len(candidates) == 2
    transfer = candidates[0]
    fee = candidates[1]
    assert transfer.transaction_type == 'TRANSFER'
    assert transfer.source_portfolio == 'Exodus'
    assert transfer.target_portfolio == 'Trezor'
    assert transfer.shares == Decimal('0.5')
    assert transfer.external_id == 'tx-1'
    assert fee.transaction_type == 'DELIVERY_OUTBOUND'
    assert fee.shares == Decimal('0.001')
    assert not ignored


def test_classify_ethereum_wallet_exports_ignores_spam_units(tmp_path: Path) -> None:
    exodus = tmp_path / 'exodus.csv'
    exodus.write_text(
        'DATE,TYPE,FROMPORTFOLIO,TOPORTFOLIO,OUTAMOUNT,OUTCURRENCY,FEEAMOUNT,FEECURRENCY,FROMADDRESS,TOADDRESS,OUTTXID,OUTTXURL,INAMOUNT,INCURRENCY,INTXID,INTXURL,ORDERID,PERSONALNOTE\n',
        encoding='utf-8',
    )
    trezor = tmp_path / 'trezor.csv'
    trezor.write_text(
        'Timestamp,Date,Time,Type,Transaction ID,Fee,Fee unit,Address,Label,Amount,Amount unit,Fiat (EUR),Other\n'
        '1767261600,01/01/2026,11:00:00 GMT+1,RECV,tx-spam,,,0xsender,,1,WETH,0,\n',
        encoding='utf-8',
    )

    candidates, ignored = classify_ethereum_wallet_exports(
        exodus_csv=exodus,
        trezor_csv=trezor,
        exodus_account='Exodus',
        trezor_account='Trezor',
        stake_account='Everstake',
        stake_address='0xstake',
        security='ETH-EUR',
        staking_return_txids=set(),
    )

    assert not candidates
    assert ignored == ['tx-spam: ignored unit WETH']
