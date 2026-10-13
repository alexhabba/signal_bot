from functools import lru_cache
from typing import Annotated

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore", env_ignore_empty=True
    )

    bot_token: str
    database_url: str = "postgresql+asyncpg://signal_bot:signal_bot@db:5432/signal_bot"

    # Telegram user ids allowed to use admin commands; comma-separated in env.
    admin_ids: Annotated[list[int], NoDecode] = Field(default_factory=list)

    # Private channel where signals are published; the bot must be an admin there.
    channel_id: int | None = None

    # Payments. Only the receiving address is stored here, never a private key.
    payment_network: str = "TRC20"
    payment_address: str = ""
    invoice_ttl_minutes: int = 60
    # Up to this many cents are added to the plan price so every pending invoice has a unique amount.
    amount_offset_slots: int = 99

    @field_validator("admin_ids", mode="before")
    @classmethod
    def parse_admin_ids(cls, value: object) -> object:
        if isinstance(value, str):
            return [int(part) for part in value.split(",") if part.strip()]
        if isinstance(value, int):
            return [value]
        return value

    def is_admin(self, user_id: int) -> bool:
        return user_id in self.admin_ids


@lru_cache
def get_settings() -> Settings:
    return Settings()
