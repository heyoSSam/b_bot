import io
import logging
import os
import warnings

from aiogram.types import Message
from mutagen.id3 import APIC, ID3, ID3NoHeaderError
from PIL import Image, ImageOps, UnidentifiedImageError

from bot.constants import (
    COVER_MAX_FILE_BYTES,
    COVER_MAX_PIXELS,
    TELEGRAM_AUDIO_THUMBNAIL_MAX_BYTES,
    TELEGRAM_AUDIO_THUMBNAIL_MAX_SIZE,
    TELEGRAM_AUDIO_THUMBNAIL_MIN_QUALITY,
    TELEGRAM_AUDIO_THUMBNAIL_QUALITY_STEP,
    TELEGRAM_AUDIO_THUMBNAIL_START_QUALITY,
)

logger = logging.getLogger(__name__)


class CoverValidationError(Exception):
    pass


class CoverFileTooLargeError(CoverValidationError):
    pass


class CoverImageTooLargeError(CoverValidationError):
    pass


class CoverImageInvalidError(CoverValidationError):
    pass


def validate_cover_file_size(cover_path: str) -> None:
    if os.path.getsize(cover_path) > COVER_MAX_FILE_BYTES:
        raise CoverFileTooLargeError


def open_cover_as_rgb(cover_path: str) -> Image.Image:
    validate_cover_file_size(cover_path)

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(cover_path) as image:
                if image.width * image.height > COVER_MAX_PIXELS:
                    raise CoverImageTooLargeError

                image = ImageOps.exif_transpose(image)

                if image.mode in ("RGBA", "LA"):
                    background = Image.new("RGB", image.size, "white")
                    background.paste(image, mask=image.getchannel("A"))
                    return background

                if image.mode != "RGB":
                    return image.convert("RGB")

                return image.copy()
    except CoverImageTooLargeError:
        raise
    except CoverFileTooLargeError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise CoverImageTooLargeError from None
    except (UnidentifiedImageError, OSError, ValueError):
        raise CoverImageInvalidError from None


def prepare_cover_jpeg(cover_path: str, output_path: str) -> None:
    image = open_cover_as_rgb(cover_path)
    image.save(output_path, format="JPEG", quality=95, optimize=True, progressive=False)


def prepare_cover_bytes(cover_path: str) -> bytes:
    image = open_cover_as_rgb(cover_path)
    output = io.BytesIO()
    image.save(output, format="JPEG", quality=95, optimize=True, progressive=False)
    return output.getvalue()


def create_audio_thumbnail(cover_path: str, thumbnail_path: str) -> None:
    image = open_cover_as_rgb(cover_path)
    image.thumbnail(TELEGRAM_AUDIO_THUMBNAIL_MAX_SIZE, Image.Resampling.LANCZOS)

    quality = TELEGRAM_AUDIO_THUMBNAIL_START_QUALITY

    while True:
        image.save(
            thumbnail_path,
            format="JPEG",
            quality=quality,
            optimize=True,
            progressive=False,
        )

        if (
            os.path.getsize(thumbnail_path) <= TELEGRAM_AUDIO_THUMBNAIL_MAX_BYTES
            or quality <= TELEGRAM_AUDIO_THUMBNAIL_MIN_QUALITY
        ):
            break

        quality -= TELEGRAM_AUDIO_THUMBNAIL_QUALITY_STEP


def add_cover_bytes_to_mp3(audio_path: str, cover_data: bytes) -> None:
    try:
        tags = ID3(audio_path)
    except ID3NoHeaderError:
        tags = ID3()

    tags.delall("APIC")
    tags.add(
        APIC(
            encoding=3,
            mime="image/jpeg",
            type=3,
            desc="Cover",
            data=cover_data,
        )
    )
    tags.save(audio_path, v2_version=3)


def add_cover_to_mp3(audio_path: str, cover_path: str) -> None:
    add_cover_bytes_to_mp3(audio_path, prepare_cover_bytes(cover_path))


async def handle_audio(message: Message):
    if message.audio:
        audio = message.audio
        file_id = audio.file_id
        file_name = audio.file_name
        file_size = audio.file_size
        logger.info(f"Received audio file: {file_name} (ID: {file_id}, Size: {file_size} bytes)")
        await message.answer(f"Получен аудиофайл: {file_name}")
    else:
        logger.warning("Received a message without an audio file.")
        await message.answer("Пожалуйста, отправьте аудиофайл в формате mp3.")
