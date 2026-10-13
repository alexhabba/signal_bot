from decimal import Decimal

DISCLAIMER = (
    "⚠️ Сигналы не являются инвестиционной рекомендацией. "
    "Торговля криптовалютой связана с высоким риском, решения вы принимаете сами."
)

WELCOME = (
    "Привет! Это бот закрытого канала с торговыми сигналами.\n\n"
    "Выберите тариф, чтобы оформить подписку. Оплата в USDT.\n\n" + DISCLAIMER
)

NO_PLANS = "Тарифы пока не настроены. Загляните чуть позже."

PAYMENTS_UNAVAILABLE = "Приём оплаты временно недоступен. Попробуйте позже."

INVOICE_CANCELLED = "Счёт отменён."

INVOICE_NOT_FOUND = "Этот счёт уже неактуален."

NO_SUBSCRIPTION = "У вас нет активной подписки. Нажмите /start, чтобы выбрать тариф."


def plan_button(title: str, price: Decimal) -> str:
    return f"{title} — {format_amount(price)} USDT"


def format_amount(amount: Decimal) -> str:
    return f"{amount:.6f}".rstrip("0").rstrip(".")


def invoice_text(*, plan_title: str, amount: Decimal, network: str, address: str, minutes_left: int) -> str:
    return (
        f"Счёт на тариф «{plan_title}»\n\n"
        f"Сеть: <b>{network}</b> (только эта сеть!)\n"
        f"Сумма: <code>{format_amount(amount)}</code> USDT\n"
        f"Адрес: <code>{address}</code>\n\n"
        f"Переведите <b>ровно эту сумму</b>: по ней бот узнаёт ваш платёж. "
        f"Если платите с биржи, проверьте, что к зачислению приходит именно {format_amount(amount)} USDT, "
        f"а не сумма за вычетом комиссии.\n\n"
        f"Счёт действует {minutes_left} мин. Доступ откроется автоматически после подтверждения перевода."
    )


def subscription_active(ends_at_text: str) -> str:
    return f"Подписка активна до {ends_at_text} (UTC)."


def format_date(value) -> str:
    return value.strftime("%d.%m.%Y %H:%M")


def payment_received(ends_at_text: str) -> str:
    return f"✅ Оплата получена! Подписка активна до {ends_at_text} (UTC)."


def signal_message(text: str) -> str:
    return f"📈 Сигнал\n\n{text}"


def broadcast_report(delivered: int, failed: int) -> str:
    text = f"Отправлено подписчикам: {delivered}."
    if failed:
        text += f" Не дошло: {failed} (заблокировали бота или недоступны)."
    return text


SIGNAL_USAGE = "Формат: /signal <текст сигнала>. Текст получат все подписчики с активной подпиской."
FREE_USAGE = "Формат: /free <текст>. Он будет опубликован в открытом канале."
NO_SUBSCRIBERS = "Активных подписчиков пока нет, сигнал никому не отправлен."
PUBLIC_CHANNEL_NOT_CONFIGURED = "Открытый канал не настроен: укажите PUBLIC_CHANNEL_ID в .env."


def join_link(link: str, ttl_hours: int) -> str:
    return (
        f"Ваша ссылка в канал с сигналами: {link}\n\n"
        f"Нажмите «Подать заявку», бот одобрит её автоматически. Ссылка действует {ttl_hours} ч, "
        f"новую можно получить командой /link."
    )


def underpaid(received, shortfall) -> str:
    return (
        f"⚠️ Получено {format_amount(received)} USDT, это меньше суммы счёта на {format_amount(shortfall)} USDT. "
        "Скорее всего, биржа вычла комиссию за вывод. Мы уже видим платёж: напишите администратору, "
        "и он поможет закрыть оплату."
    )


def renewal_reminder(ends_at_text: str) -> str:
    return f"⏳ Подписка заканчивается {ends_at_text} (UTC). Чтобы продлить, нажмите /start и выберите тариф."


SUBSCRIPTION_ENDED = "Подписка закончилась, доступ к каналу закрыт. Чтобы вернуться, нажмите /start."

SIGNALS_IN_CHAT = "Полные сигналы будут приходить сюда, в этот чат. Не блокируйте бота и не отключайте уведомления."


def admin_unmatched(tx_hash: str, amount, from_address: str) -> str:
    return (
        f"❓ Перевод не совпал ни с одним счётом.\n"
        f"Сумма: {format_amount(amount)} USDT\nОт: {from_address}\nTx: <code>{tx_hash}</code>\n"
        f"Если это чья-то оплата, выдайте доступ: /grant &lt;user_id&gt; &lt;дней&gt;"
    )


def admin_underpaid(user_id: int, invoice_id: int, received, expected) -> str:
    return (
        f"⚠️ Недоплата по счёту #{invoice_id} от пользователя {user_id}: "
        f"пришло {format_amount(received)} из {format_amount(expected)} USDT.\n"
        f"Чтобы засчитать: /grant {user_id} &lt;дней&gt;"
    )
