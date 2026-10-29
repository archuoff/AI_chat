"""Images attached to a chat question.

Images are held in memory only for the duration of one question (never written to the chat memory
database), validated, and described by the vision-capable chat model so the description can drive
retrieval; the answer step then sees the images themselves too.
"""
from __future__ import annotations

import base64
import binascii
import logging
import re
import threading
import uuid

from ..llm import add_usage, describe_llm_error, get_chat_model

log = logging.getLogger(__name__)

MAX_IMAGES = 4
MAX_IMAGE_BYTES = 5 * 1024 * 1024
_DATA_URL = re.compile(r"^data:image/(png|jpeg|jpg|webp|gif);base64,([A-Za-z0-9+/=\s]+)$")

_lock = threading.Lock()
_pending: dict[str, list[str]] = {}

_DESCRIBE_PROMPT = """Describe the attached image(s) from an automotive engineering context so a document search can find
related specifications, guidelines, FMEAs and benchmarking data. In 4-8 short lines give:
- what it shows (part / component / system / diagram / screenshot type)
- all readable text, labels, part numbers and codes (transcribe exactly)
- visible dimensions, values, tolerances or units
- materials, finishes, defects or failure signs if visible
Be factual; say "unclear" rather than guessing."""


def validate_images(images: list[str]) -> list[str]:
    """Return the images if valid data URLs (png/jpeg/webp/gif, <= 5 MB each, max 4); raise ValueError otherwise."""
    if len(images) > MAX_IMAGES:
        raise ValueError(f"At most {MAX_IMAGES} images per question")
    out = []
    for i, url in enumerate(images, start=1):
        m = _DATA_URL.match(url.strip())
        if not m:
            raise ValueError(f"Image {i} is not a PNG, JPEG, WebP or GIF data URL")
        try:
            raw = base64.b64decode(m.group(2), validate=False)
        except (binascii.Error, ValueError) as e:
            raise ValueError(f"Image {i} is not valid base64") from e
        if len(raw) > MAX_IMAGE_BYTES:
            raise ValueError(f"Image {i} is larger than {MAX_IMAGE_BYTES // (1024 * 1024)} MB")
        out.append(url.strip())
    return out


def hold(images: list[str]) -> str | None:
    """Keep images for the current question; returns a reference stored in the graph state."""
    if not images:
        return None
    ref = uuid.uuid4().hex
    with _lock:
        _pending[ref] = images
    return ref


def get(ref: str | None) -> list[str]:
    if not ref:
        return []
    with _lock:
        return list(_pending.get(ref, []))


def release(ref: str | None) -> None:
    if ref:
        with _lock:
            _pending.pop(ref, None)


def image_parts(images: list[str]) -> list[dict]:
    return [{"type": "image_url", "image_url": {"url": u, "detail": "auto"}} for u in images]


def describe(images: list[str], question: str, usage: dict | None = None) -> tuple[str, str | None]:
    """Return (description, notice). Empty description when the model is unavailable or fails."""
    llm = get_chat_model(fast=True)
    if llm is None:
        return "", "Image understanding needs Azure OpenAI; the attached image was not analysed."
    content = [{"type": "text", "text": f"User question: {question or '(no text, only the image)'}\n\n{_DESCRIBE_PROMPT}"}]
    try:
        msg = llm.invoke([("user", content + image_parts(images))])
        add_usage(usage, msg)
        return str(msg.content).strip(), None
    except Exception as e:  # noqa: BLE001 - the question still runs without the image description
        log.warning("image description failed: %s", describe_llm_error(e))
        return "", f"The attached image could not be analysed ({describe_llm_error(e)})."
