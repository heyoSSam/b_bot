import asyncio
import json
import logging
import os
import re
from dataclasses import dataclass

import aiohttp

from bot.constants import GEMINI_STYLE_SYSTEM_PROMPT, GEMINI_STYLE_USER_PROMPT


logger = logging.getLogger(__name__)


class GeminiStyleError(Exception):
    pass


class GeminiStyleConfigError(GeminiStyleError):
    pass


class GeminiStyleResponseError(GeminiStyleError):
    pass


class GeminiStyleUnavailableError(GeminiStyleError):
    pass


@dataclass(slots=True)
class GeminiStyleResult:
    style: str
    clarification_question: str
    notes: list[str]


def build_gemini_style_user_prompt(user_input: str, has_channel: bool) -> str:
    return GEMINI_STYLE_USER_PROMPT.format(
        channel_availability="сохранённый канал доступен" if has_channel else "сохранённый канал недоступен",
        user_input=user_input.strip(),
    )


def extract_gemini_response_text(payload: dict) -> str:
    candidates = payload.get("candidates") or []

    for candidate in candidates:
        content = candidate.get("content") or {}
        parts = content.get("parts") or []
        texts = [part.get("text", "") for part in parts if part.get("text")]

        if texts:
            return "".join(texts).strip()

    raise GeminiStyleResponseError("Gemini returned an empty response.")


def normalize_gemini_json_text(value: str) -> str:
    text = value.strip()
    text = re.sub(r"^```(?:json)?\s*", "", text)
    text = re.sub(r"\s*```$", "", text)

    object_start = text.find("{")
    object_end = text.rfind("}")

    if object_start != -1 and object_end != -1 and object_end >= object_start:
        return text[object_start : object_end + 1]

    return text


def extract_gemini_error_message(payload: dict) -> str:
    error = payload.get("error") or {}
    message = error.get("message")
    return message.strip() if isinstance(message, str) and message.strip() else "Gemini request failed."


def is_gemini_temporarily_unavailable(status_code: int, message: str) -> bool:
    normalized_message = message.lower()
    temporary_markers = (
        "overloaded",
        "unavailable",
        "resource exhausted",
        "quota exceeded",
        "try again later",
        "temporarily",
        "timeout",
        "timed out",
    )

    if status_code in {429, 500, 503}:
        return True

    return any(marker in normalized_message for marker in temporary_markers)


def parse_gemini_style_result(payload: dict) -> GeminiStyleResult:
    try:
        response_data = json.loads(normalize_gemini_json_text(extract_gemini_response_text(payload)))
    except json.JSONDecodeError as error:
        raise GeminiStyleResponseError("Gemini returned invalid JSON.") from error

    style = response_data.get("style")
    clarification_question = response_data.get("clarification_question")
    notes = response_data.get("notes")

    if not isinstance(style, str) or not isinstance(clarification_question, str) or not isinstance(notes, list):
        raise GeminiStyleResponseError("Gemini returned an unexpected JSON shape.")

    clean_notes = [
        note.strip()
        for note in notes
        if isinstance(note, str) and note.strip()
    ]
    clean_style = style.strip()
    clean_clarification_question = clarification_question.strip()

    if clean_style:
        clean_clarification_question = ""

    return GeminiStyleResult(
        style=clean_style,
        clarification_question=clean_clarification_question,
        notes=clean_notes[:3],
    )


async def infer_name_style_with_gemini(user_input: str, has_channel: bool) -> GeminiStyleResult:
    api_key = os.getenv("GEMINI_API_KEY")

    if not api_key:
        raise GeminiStyleConfigError("GEMINI_API_KEY is not configured.")

    request_payload = {
        "systemInstruction": {
            "parts": [{"text": GEMINI_STYLE_SYSTEM_PROMPT}],
        },
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": build_gemini_style_user_prompt(user_input, has_channel),
                    }
                ],
            }
        ],
        "generationConfig": {
            "responseMimeType": "application/json",
            "responseJsonSchema": {
                "type": "object",
                "properties": {
                    "style": {"type": "string"},
                    "clarification_question": {"type": "string"},
                    "notes": {
                        "type": "array",
                        "items": {"type": "string"},
                    },
                },
                "required": ["style", "clarification_question", "notes"],
            },
        },
    }

    timeout = aiohttp.ClientTimeout(total=30)
    endpoint = "https://generativelanguage.googleapis.com/v1beta/models/gemma-4-31b-it:generateContent"

    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.post(
                endpoint,
                headers={"x-goog-api-key": api_key, "Content-Type": "application/json"},
                json=request_payload,
            ) as response:
                response_text = await response.text()

                try:
                    payload = json.loads(response_text)
                except json.JSONDecodeError as error:
                    raise GeminiStyleResponseError("Gemini returned invalid JSON response.") from error

                if response.status >= 400:
                    message = extract_gemini_error_message(payload)
                    logger.warning("Gemini style request failed with status %s: %s", response.status, message)

                    if is_gemini_temporarily_unavailable(response.status, message):
                        raise GeminiStyleUnavailableError(message)

                    raise GeminiStyleResponseError(message)
    except (aiohttp.ClientError, asyncio.TimeoutError) as error:
        raise GeminiStyleUnavailableError("Failed to reach Gemini API.") from error

    return parse_gemini_style_result(payload)
