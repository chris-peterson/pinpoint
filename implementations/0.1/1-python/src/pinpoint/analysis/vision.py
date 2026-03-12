"""Ollama vision LLM analysis for images.

Sends images to a local Ollama vision model (e.g., LLaVA) for scene
description. Extracts suggested event, person, and name tags from the
model's response. Silently skipped if Ollama is not running.
"""

from __future__ import annotations

import base64
import logging
import re
from pathlib import Path

import httpx

logger = logging.getLogger(__name__)

# Max dimension for downscaling before sending to vision model
MAX_DIM = 1024


def _downscale_image(path: Path) -> bytes:
    """Read and optionally downscale an image to keep inference fast.

    Returns JPEG bytes suitable for base64 encoding.
    """
    try:
        from PIL import Image

        with Image.open(path) as img:
            # Convert to RGB (handles RGBA, palette, etc.)
            if img.mode not in ("RGB", "L"):
                img = img.convert("RGB")

            # Downscale if larger than MAX_DIM on either axis
            if max(img.size) > MAX_DIM:
                img.thumbnail((MAX_DIM, MAX_DIM))

            import io
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85)
            return buf.getvalue()
    except Exception:
        # Fallback: just read raw bytes (model may still handle it)
        return path.read_bytes()


async def check_ollama(client: httpx.AsyncClient, ollama_url: str) -> bool:
    """Check if Ollama is running and responsive."""
    try:
        resp = await client.get(f"{ollama_url}/api/tags", timeout=3)
        return resp.status_code == 200
    except Exception:
        return False


_VISION_PROMPT = """Describe this image briefly for file organization. Focus on:
1. What type of scene or event is this? (e.g., birthday party, beach vacation, concert, wedding)
2. Any notable people or subjects? (don't identify specific people, just describe - e.g., "group of friends", "child playing")
3. What would be a good short descriptive name for this image?

Reply in this exact format (use lowercase, be concise):
event: <event type or scene>
people: <brief description of people, or "none">
name: <short descriptive name for the file>"""


async def analyze_image(
    client: httpx.AsyncClient,
    ollama_url: str,
    model: str,
    image_path: Path,
) -> list[dict]:
    """Analyze an image using Ollama vision model.

    Returns list of {kind, value, confidence} suggestion dicts.
    """
    # Downscale and encode
    image_bytes = _downscale_image(image_path)
    image_b64 = base64.b64encode(image_bytes).decode("ascii")

    try:
        resp = await client.post(
            f"{ollama_url}/api/generate",
            json={
                "model": model,
                "prompt": _VISION_PROMPT,
                "images": [image_b64],
                "stream": False,
                "options": {"temperature": 0.3, "num_predict": 200},
            },
            timeout=60,
        )
        resp.raise_for_status()
        text = resp.json().get("response", "")
    except Exception:
        logger.debug("Ollama vision analysis failed for %s", image_path, exc_info=True)
        return []

    return _parse_vision_response(text)


def _parse_vision_response(text: str) -> list[dict]:
    """Parse structured response from the vision model into suggestions."""
    suggestions: list[dict] = []

    # Extract event
    event_match = re.search(r"event:\s*(.+)", text, re.IGNORECASE)
    if event_match:
        event = event_match.group(1).strip().rstrip(".")
        if event and event.lower() not in ("none", "n/a", "unknown", "general"):
            suggestions.append({"kind": "event", "value": event, "confidence": 0.5})

    # Extract people as person tag
    people_match = re.search(r"people:\s*(.+)", text, re.IGNORECASE)
    if people_match:
        people = people_match.group(1).strip().rstrip(".")
        if people and people.lower() not in ("none", "n/a", "no one", "nobody"):
            suggestions.append({"kind": "person", "value": people, "confidence": 0.4})

    # Extract name
    name_match = re.search(r"name:\s*(.+)", text, re.IGNORECASE)
    if name_match:
        name = name_match.group(1).strip().rstrip(".")
        if name and name.lower() not in ("none", "n/a", "unknown"):
            suggestions.append({"kind": "name", "value": name, "confidence": 0.5})

    return suggestions
