import re

from app.bot import texts

ALLOWED_TAGS = {"b", "i", "u", "s", "code", "pre", "a", "tg-spoiler", "blockquote"}


def test_usage_hints_contain_only_valid_html_tags():
    # The bot sends with ParseMode.HTML, so a bare "<text>" is rejected by Telegram.
    for hint in (texts.SIGNAL_USAGE, texts.FREE_USAGE):
        for tag in re.findall(r"</?([A-Za-z0-9-]+)", hint):
            assert tag in ALLOWED_TAGS, hint
        assert "<текст" not in hint
