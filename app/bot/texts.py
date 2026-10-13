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
