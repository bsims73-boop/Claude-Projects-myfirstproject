import base64
import io
import json

import anthropic
from PIL import Image

import config

_client = None


def get_client():
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY)
    return _client


def extract_receipt_data(image_bytes, mime_type):
    image_bytes = _resize_image_if_needed(image_bytes, config.MAX_IMAGE_SIZE_MB)
    image_b64 = base64.standard_b64encode(image_bytes).decode("utf-8")

    response = get_client().messages.create(
        model=config.CLAUDE_MODEL,
        max_tokens=1024,
        system="You are a receipt data extractor. Extract structured data from receipt images. Always respond with valid JSON only, no other text.",
        messages=[{
            "role": "user",
            "content": [
                {
                    "type": "image",
                    "source": {
                        "type": "base64",
                        "media_type": mime_type,
                        "data": image_b64,
                    }
                },
                {
                    "type": "text",
                    "text": (
                        "Extract all data from this receipt and return ONLY this JSON structure:\n"
                        "{\n"
                        '  "date": "YYYY-MM-DD or null if not found",\n'
                        '  "company_name": "string or null",\n'
                        '  "line_items": [\n'
                        '    {"name": "string", "quantity": number_or_null, "unit_price": number_or_null, "line_total": number_or_null}\n'
                        '  ],\n'
                        '  "total_amount": number_or_null,\n'
                        '  "currency": "USD"\n'
                        "}\n"
                        "Rules:\n"
                        "- date must be ISO format YYYY-MM-DD\n"
                        "- all monetary values are numbers (not strings), no currency symbols\n"
                        "- if a field cannot be determined, use null\n"
                        "- line_items may be empty array if no itemization visible\n"
                        "- total_amount should be the final total including tax"
                    )
                }
            ]
        }]
    )

    text = response.content[0].text.strip()
    text = _strip_markdown(text)
    return json.loads(text)


def _strip_markdown(text):
    if not text.startswith("```"):
        return text.strip()
    newline = text.find("\n")
    if newline == -1:
        return text.strip()
    text = text[newline + 1:]
    close = text.rstrip().rfind("\n```")
    if close != -1:
        text = text[:close]
    return text.strip()


def _resize_image_if_needed(image_bytes, max_mb):
    if len(image_bytes) / (1024 * 1024) <= max_mb:
        return image_bytes

    img = Image.open(io.BytesIO(image_bytes))
    max_dim = 2000
    if max(img.size) > max_dim:
        ratio = max_dim / max(img.size)
        new_size = (int(img.size[0] * ratio), int(img.size[1] * ratio))
        img = img.resize(new_size, Image.LANCZOS)

    buf = io.BytesIO()
    img_format = "JPEG" if img.mode == "RGB" else "PNG"
    if img.mode == "RGBA":
        img = img.convert("RGB")
        img_format = "JPEG"
    img.save(buf, format=img_format)
    return buf.getvalue()
