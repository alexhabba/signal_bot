"""Channel access: personal join links, join-request approval and removal."""

import logging
from datetime import datetime, timedelta, timezone

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

logger = logging.getLogger(__name__)


async def make_join_link(bot: Bot, channel_id: int, user_id: int, ttl: timedelta) -> str:
    """A personal link that only files a join request; the bot approves it for paying users only,
    so a forwarded link is useless to anyone else."""
    link = await bot.create_chat_invite_link(
        chat_id=channel_id,
        name=f"user {user_id}",
        expire_date=datetime.now(timezone.utc) + ttl,
        creates_join_request=True,
    )
    return link.invite_link


async def remove_from_channel(bot: Bot, channel_id: int, user_id: int) -> bool:
    """Kick the user; the immediate unban lets them come back after paying again."""
    try:
        await bot.ban_chat_member(chat_id=channel_id, user_id=user_id)
        await bot.unban_chat_member(chat_id=channel_id, user_id=user_id, only_if_banned=True)
        return True
    except TelegramAPIError as exc:
        logger.warning("Could not remove %s from channel: %s", user_id, exc)
        return False
