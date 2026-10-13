from datetime import datetime, timezone
from decimal import Decimal

from app.services.tron import USDT_CONTRACT, parse_transfer

ADDRESS = "TOurAddress"


def record(**overrides):
    item = {
        "transaction_id": "abc",
        "token_info": {"symbol": "USDT", "address": USDT_CONTRACT, "decimals": 6, "name": "Tether USD"},
        "block_timestamp": 1_791_892_800_000,
        "from": "TSender",
        "to": ADDRESS,
        "type": "Transfer",
        "value": "30010000",
    }
    item.update(overrides)
    return item


def test_parses_usdt_transfer():
    transfer = parse_transfer(record(), ADDRESS)
    assert transfer.amount == Decimal("30.01")
    assert transfer.from_address == "TSender"
    assert transfer.block_time == datetime.fromtimestamp(1_791_892_800, tz=timezone.utc)


def test_ignores_fake_usdt_token():
    fake = record(token_info={"symbol": "USDT", "address": "TFakeContract", "decimals": 6})
    assert parse_transfer(fake, ADDRESS) is None


def test_ignores_outgoing_and_non_transfer():
    assert parse_transfer(record(to="TSomeoneElse"), ADDRESS) is None
    assert parse_transfer(record(type="Approval"), ADDRESS) is None


async def test_client_follows_pages_and_filters():
    from aiohttp import ClientSession, web
    from aiohttp.test_utils import TestServer

    from app.services.tron import TronGridClient

    seen_params = []

    async def handler(request):
        seen_params.append(dict(request.query))
        if "fingerprint" not in request.query:
            return web.json_response(
                {"success": True, "data": [record(transaction_id="a")], "meta": {"fingerprint": "next"}}
            )
        fake = record(transaction_id="b", token_info={"address": "TFake", "decimals": 6})
        return web.json_response({"success": True, "data": [fake, record(transaction_id="c")], "meta": {}})

    app = web.Application()
    app.router.add_get(f"/v1/accounts/{ADDRESS}/transactions/trc20", handler)
    async with TestServer(app) as server, ClientSession() as http:
        client = TronGridClient(http, api_key="key", base_url=str(server.make_url("")))
        since = datetime(2026, 10, 13, tzinfo=timezone.utc)
        transfers = await client.incoming_transfers(ADDRESS, since)

    assert [t.tx_hash for t in transfers] == ["a", "c"]
    assert seen_params[0]["only_confirmed"] == "true"
    assert seen_params[0]["contract_address"] == USDT_CONTRACT
    assert seen_params[0]["min_timestamp"] == str(int(since.timestamp() * 1000))
    assert seen_params[1]["fingerprint"] == "next"
