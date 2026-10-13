"""Reading incoming USDT (TRC-20) transfers from the TronGrid API.

Only the public address is used; nothing here can move funds.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

import aiohttp

logger = logging.getLogger(__name__)

TRONGRID_URL = "https://api.trongrid.io"
# The real USDT contract on Tron. Transfers of look-alike tokens named "USDT" are ignored.
USDT_CONTRACT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
USDT_DECIMALS = 6
PAGE_LIMIT = 200
MAX_PAGES = 20


@dataclass(frozen=True)
class Transfer:
    tx_hash: str
    from_address: str
    to_address: str
    amount: Decimal
    block_time: datetime


def parse_transfer(item: dict, address: str) -> Transfer | None:
    """Turn one TronGrid record into a Transfer, or None if it is not a USDT payment to us."""
    token = item.get("token_info") or {}
    if token.get("address") != USDT_CONTRACT:
        return None
    if item.get("type") != "Transfer" or item.get("to") != address:
        return None
    decimals = int(token.get("decimals", USDT_DECIMALS))
    return Transfer(
        tx_hash=item["transaction_id"],
        from_address=item.get("from", ""),
        to_address=item["to"],
        amount=Decimal(item["value"]).scaleb(-decimals),
        block_time=datetime.fromtimestamp(item["block_timestamp"] / 1000, tz=timezone.utc),
    )


class TronGridClient:
    def __init__(self, session: aiohttp.ClientSession, api_key: str = "", base_url: str = TRONGRID_URL) -> None:
        self.session = session
        self.base_url = base_url.rstrip("/")
        self.headers = {"TRON-PRO-API-KEY": api_key} if api_key else {}

    async def incoming_transfers(self, address: str, since: datetime) -> list[Transfer]:
        """Confirmed (solidified) incoming USDT transfers to `address` since `since`, oldest first."""
        url = f"{self.base_url}/v1/accounts/{address}/transactions/trc20"
        params: dict[str, str | int] = {
            "only_to": "true",
            "only_confirmed": "true",
            "contract_address": USDT_CONTRACT,
            "min_timestamp": int(since.timestamp() * 1000),
            "order_by": "block_timestamp,asc",
            "limit": PAGE_LIMIT,
        }
        transfers: list[Transfer] = []
        for _ in range(MAX_PAGES):
            async with self.session.get(url, params=params, headers=self.headers) as resp:
                resp.raise_for_status()
                body = await resp.json()
            if not body.get("success", True):
                raise RuntimeError(f"TronGrid error: {body}")
            for item in body.get("data", []):
                transfer = parse_transfer(item, address)
                if transfer is not None:
                    transfers.append(transfer)
            fingerprint = (body.get("meta") or {}).get("fingerprint")
            if not fingerprint:
                break
            params["fingerprint"] = fingerprint
        else:
            logger.warning("Stopped after %s pages of TronGrid results; the rest is picked up next poll", MAX_PAGES)
        return transfers
