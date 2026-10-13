import logging
from datetime import timedelta

from aiogram import Bot, Router
from aiogram.filters import Command
from aiogram.types import ChatJoinRequest, Message
from sqlalchemy.ext.asyncio import AsyncSession

from app.bot import texts
from app.config import Settings
from app.services.access import make_join_link
from app.services.subscriptions import active_until

logger = logging.getLogger(__name__)
router = Router(name="channel")


@router.chat_join_request()
async def on_join_request(request: ChatJoinRequest, session: AsyncSession, settings: Settings) -> None:
    if request.chat.id != settings.channel_id:
        return
    if await active_until(session, request.from_user.id):
        await request.approve()
        logger.info("Approved join request from %s", request.from_user.id)
    else:
        await request.decline()
        logger.info("Declined join request from %s: no active subscription", request.from_user.id)


@router.message(Command("link"))
async def link(message: Message, bot: Bot, session: AsyncSession, settings: Settings) -> None:
    if await active_until(session, message.from_user.id) is None:
        await message.answer(texts.NO_SUBSCRIPTION)
        return
    if not settings.channel_id:
        await message.answer(texts.SIGNALS_IN_CHAT)
        return
    invite = await make_join_link(
        bot, settings.channel_id, message.from_user.id, timedelta(hours=settings.invite_link_ttl_hours)
    )
    await message.answer(texts.join_link(invite, settings.invite_link_ttl_hours))
