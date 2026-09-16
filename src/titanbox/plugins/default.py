from __future__ import annotations

from typing import TYPE_CHECKING, Any


class DefaultPlugin:
    """Small demo plugin. Replace this class with your actual bot feature router."""

    async def handle(self, update: dict[str, Any], bot: "BotContext") -> None:
        message = update.get("message") or update.get("edited_message")
        if not isinstance(message, dict):
            return
        chat = message.get("chat") or {}
        chat_id = chat.get("id")
        if chat_id is None:
            return
        text = str(message.get("text", ""))
        if text.startswith("/start"):
            reply = (
                "TitanBox is online ✅\n\n"
                "This is the minimal default plugin. Replace it with your medical bot router.\n"
                "Commands: /start /ping"
            )
        elif text.startswith("/ping"):
            reply = "pong ✅"
        else:
            reply = "Bot is online. Configure your plugin to handle this message."
        await bot.send_message(chat_id=chat_id, text=reply)


# Import only for typing without a runtime cycle.
if TYPE_CHECKING:
    from titanbox.telegram import BotContext
