START_GUIDE_TEXT = """Привет!

Этот бот помогает битмейкерам быстро оформить пост с их работами: добавить биты/бит, сделать им обложку и подготовить текст для публикации.

Выберите действие в меню ниже.

Автор: @wilddogslivelong
"""

BOT_CREDIT_TEXT = "оформление сделано через @FormatterBeatBot"

DEFAULT_NAME_STYLE = "{me}"

NAME_STYLE_TOKEN_PATTERN = r"\{(me|channel|co-author)(?::([^{}]*))?\}"
NAME_STYLE_MAX_LENGTH = 500

SET_STYLE_CONSTRUCTOR_TEXT = """Конструктор шаблона подписи.

Текущий шаблон:
<code>{style}</code>

Кнопки добавляют блоки в конец шаблона. Когда подпись готова, проверьте предпросмотр и сохраните.{notice}"""

SET_STYLE_TEXT_INPUT_PROMPT = """Отправьте текст, который нужно добавить в подпись.

Например: пробел, перенос строки, разделитель или обычную фразу."""

SET_STYLE_ME_TEXT_INPUT_PROMPT = """Отправьте текст для ссылки на личные сообщения.

Например: написать, в лс, @username."""

SET_STYLE_CO_AUTHOR_TEXT_INPUT_PROMPT = """Отправьте текст, который должен стоять перед соавторами.

Например: w/, feat., x или любой ваш разделитель."""

SET_STYLE_RAW_INPUT_PROMPT = """Отправьте шаблон вручную.

Доступные переменные:
<code>{me}</code> - ссылка на ваш Telegram с username
<code>{me:текст}</code> - ссылка на ваш Telegram с указанным текстом
<code>{channel}</code> - ссылка на ваш сохранённый канал
<code>{channel:текст}</code> - ссылка на ваш сохранённый канал с указанным текстом
<code>{co-author}</code> - ссылки на соавторов, если они есть
<code>{co-author:текст}</code> - текст + ссылки на соавторов, если они есть"""

SET_STYLE_RAW_INPUT_WITHOUT_CHANNEL_PROMPT = """Отправьте шаблон вручную.

Доступные переменные:
<code>{me}</code> - ссылка на ваш Telegram с username
<code>{me:текст}</code> - ссылка на ваш Telegram с указанным текстом
<code>{co-author}</code> - ссылки на соавторов, если они есть
<code>{co-author:текст}</code> - текст + ссылки на соавторов, если они есть"""

SET_STYLE_PREVIEW_TEXT = """Предпросмотр подписи:

{preview}

Текущий шаблон:
<code>{style}</code>"""

SET_CHANNEL_GUIDE_TEXT = """Отправьте ссылку на Telegram-канал.

Можно так:

<code>@channel</code>

<code>https://t.me/channel</code>

После этого ваш канал будет доступен для переиспользования в форматировании."""

SUBSCRIPTION_REQUIRED_TEXT = "Чтобы пользоваться этой командой, подпишитесь на канал."

FILE_NAME_RENAME_PROMPT_TEXT = """Отправьте новое название файла.

Старое название:
<code>{file_name}</code>

Можно отправить название без .mp3 - расширение добавится автоматически.
Чтобы оставить старое название, нажмите «Оставить это название».
Кнопка со старым названием копирует его в буфер обмена."""

MAX_TRACK_AUTHORS = 5

COVER_MAX_FILE_BYTES = 20 * 1024 * 1024
COVER_MAX_PIXELS = 25_000_000
COVER_FILE_TOO_LARGE_TEXT = "Обложка слишком большая. Отправьте JPEG или PNG до {max_megabytes} МБ."
COVER_IMAGE_TOO_LARGE_TEXT = (
    "Обложка слишком большая по разрешению. "
    "Отправьте JPEG или PNG до {max_megapixels} мегапикселей."
)
COVER_IMAGE_INVALID_TEXT = (
    "Не удалось обработать обложку. "
    "Отправьте обычный JPEG или PNG без повреждений и аномально большого размера."
)

AUTHOR_LIMIT_EXCEEDED_TEXT = "Можно указать не больше {max_authors} соавторов для одного mp3."

TELEGRAM_AUDIO_THUMBNAIL_MAX_SIZE = (320, 320)
TELEGRAM_AUDIO_THUMBNAIL_MAX_BYTES = 200 * 1024
TELEGRAM_AUDIO_THUMBNAIL_START_QUALITY = 90
TELEGRAM_AUDIO_THUMBNAIL_MIN_QUALITY = 55
TELEGRAM_AUDIO_THUMBNAIL_QUALITY_STEP = 5
BEATPACK_MEDIA_GROUP_COLLECT_SECONDS = 1.0
BEATPACK_BUILD_MAX_CONCURRENCY = 3
