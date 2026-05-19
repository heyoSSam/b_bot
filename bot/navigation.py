from aiogram import Bot, F, Router
from aiogram.exceptions import TelegramAPIError
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from bot.cleanup import cleanup_messages
from bot.constants import START_GUIDE_TEXT


router = Router()


def get_start_keyboard() -> InlineKeyboardMarkup:
    return with_start_button()


def with_start_button(reply_markup: InlineKeyboardMarkup | None = None) -> InlineKeyboardMarkup:
    inline_keyboard = []

    if reply_markup:
        inline_keyboard.extend(reply_markup.inline_keyboard)

    inline_keyboard.append(
        [
            InlineKeyboardButton(
                text="Меню",
                callback_data="navigation:start",
            )
        ]
    )

    return InlineKeyboardMarkup(inline_keyboard=inline_keyboard)


@router.callback_query(F.data == "navigation:start")
async def go_to_start(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer()

    if not callback.message:
        await state.clear()
        return

    chat_id = callback.message.chat.id
    message_id = callback.message.message_id

    await cleanup_messages(bot, state, chat_id)

    try:
        await bot.delete_message(chat_id=chat_id, message_id=message_id)
    except TelegramAPIError:
        pass

    await state.clear()
    await callback.message.answer(START_GUIDE_TEXT)
