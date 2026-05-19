import logging
import os
import tempfile

from aiogram import Bot
from aiogram.types import FSInputFile, Message

from bot.audio import add_cover_to_mp3


logger = logging.getLogger(__name__)


async def handle_image(
    message: Message,
    bot: Bot,
    audio_file_id: str,
    audio_file_name: str,
):
    if message.photo:
        photo = message.photo[-1]
        safe_audio_file_name = os.path.basename(audio_file_name) or "audio.mp3"

        logger.info(f"Received cover image: {photo.file_id}. Audio file ID: {audio_file_id}")

        with tempfile.TemporaryDirectory() as temp_dir:
            audio_path = os.path.join(temp_dir, safe_audio_file_name)
            cover_path = os.path.join(temp_dir, "cover.jpg")

            await message.answer("Обрабатываю файл...")
            await bot.download(audio_file_id, destination=audio_path)
            await bot.download(photo.file_id, destination=cover_path)

            add_cover_to_mp3(audio_path, cover_path)

            await message.answer_audio(
                audio=FSInputFile(audio_path, filename=safe_audio_file_name),
                caption="Готово.",
            )
    else:
        logger.warning("Received a message without an image.")
        await message.answer("Пожалуйста, отправьте изображение для обложки.")
