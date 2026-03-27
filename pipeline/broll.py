"""Gemini Imagen b-roll generation + Ken Burns animation."""

import base64
import os
from pathlib import Path

import requests
from PIL import Image

from .config import VIDEO_WIDTH, VIDEO_HEIGHT, get_gemini_key, run_cmd
from .log import log
from .retry import with_retry

# Model fallback chain: try primary model, then fast imagen, then fallback color frame
IMAGEN_MODEL = os.environ.get("IMAGEN_MODEL", "gemini-3.1-flash-image-preview")
IMAGEN_FALLBACK_MODEL = os.environ.get(
    "IMAGEN_FALLBACK_MODEL", "imagen-4.0-fast-generate-001"
)
IMAGEN_TIMEOUT = int(os.environ.get("IMAGEN_TIMEOUT", "120"))


def _generate_image_gemini_native(
    prompt: str, output_path: Path, api_key: str, model: str
):
    """Generate image using Gemini native image generation (generateContent)."""
    url = (
        f"https://generativelanguage.googleapis.com/v1beta"
        f"/models/{model}:generateContent"
    )
    body = {
        "contents": [{"parts": [{"text": f"Generate an image: {prompt}"}]}],
        "generationConfig": {"responseModalities": ["IMAGE", "TEXT"]},
    }
    r = requests.post(
        url,
        json=body,
        timeout=IMAGEN_TIMEOUT,
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
    )
    if r.status_code != 200:
        try:
            detail = r.json().get("error", {}).get("message", r.text[:200])
        except Exception:
            detail = r.text[:200]
        raise RuntimeError(f"Gemini API {r.status_code} ({model}): {detail}")
    data = r.json()
    for part in data.get("candidates", [{}])[0].get("content", {}).get("parts", []):
        if "inlineData" in part:
            img_b64 = part["inlineData"]["data"]
            output_path.write_bytes(base64.b64decode(img_b64))
            return
    raise RuntimeError(f"No image in Gemini response ({model})")


def _generate_image_imagen(prompt: str, output_path: Path, api_key: str, model: str):
    """Generate image using Imagen API (predict endpoint)."""
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:predict"
    body = {
        "instances": [{"prompt": prompt}],
        "parameters": {
            "sampleCount": 1,
            "aspectRatio": "9:16",
        },
    }
    r = requests.post(
        url,
        json=body,
        timeout=IMAGEN_TIMEOUT,
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
    )
    if r.status_code != 200:
        try:
            detail = r.json().get("error", {}).get("message", r.text[:200])
        except Exception:
            detail = r.text[:200]
        raise RuntimeError(f"Imagen API {r.status_code} ({model}): {detail}")
    data = r.json()
    predictions = data.get("predictions", [])
    if predictions and "bytesBase64Encoded" in predictions[0]:
        img_b64 = predictions[0]["bytesBase64Encoded"]
        output_path.write_bytes(base64.b64decode(img_b64))
        return
    raise RuntimeError(f"No image in Imagen response ({model})")


@with_retry(max_retries=2, base_delay=3.0)
def _generate_image_with_fallback(prompt: str, output_path: Path, api_key: str):
    """Try primary model, fallback to imagen-4.0-fast if it fails."""
    try:
        _generate_image_gemini_native(prompt, output_path, api_key, IMAGEN_MODEL)
        return
    except Exception as e:
        log(f"Primary model ({IMAGEN_MODEL}) failed: {e}")

    if IMAGEN_FALLBACK_MODEL.startswith("imagen-"):
        log(f"Trying fallback model: {IMAGEN_FALLBACK_MODEL}...")
        _generate_image_imagen(prompt, output_path, api_key, IMAGEN_FALLBACK_MODEL)
    else:
        log(f"Trying fallback model: {IMAGEN_FALLBACK_MODEL}...")
        _generate_image_gemini_native(
            prompt, output_path, api_key, IMAGEN_FALLBACK_MODEL
        )


def _fallback_frame(i: int, out_dir: Path) -> Path:
    colors = [(20, 20, 60), (40, 10, 40), (10, 30, 50)]
    img = Image.new("RGB", (VIDEO_WIDTH, VIDEO_HEIGHT), colors[i % len(colors)])
    path = out_dir / f"broll_{i}.png"
    img.save(path)
    return path


def generate_broll(prompts: list, out_dir: Path) -> list[Path]:
    api_key = get_gemini_key()
    frames = []

    for i, prompt in enumerate(prompts[:3]):
        out_path = out_dir / f"broll_{i}.png"
        log(
            f"Generating b-roll frame {i + 1}/3 via {IMAGEN_MODEL} (timeout={IMAGEN_TIMEOUT}s)..."
        )

        try:
            _generate_image_with_fallback(prompt, out_path, api_key)

            img = Image.open(out_path).convert("RGB")
            target_w, target_h = VIDEO_WIDTH, VIDEO_HEIGHT
            orig_w, orig_h = img.size
            scale = max(target_w / orig_w, target_h / orig_h)
            new_w, new_h = int(orig_w * scale), int(orig_h * scale)
            img = img.resize((new_w, new_h), Image.LANCZOS)
            left = (new_w - target_w) // 2
            top = (new_h - target_h) // 2
            img = img.crop((left, top, left + target_w, top + target_h))
            img.save(out_path)
            frames.append(out_path)

        except Exception as e:
            log(f"Frame {i + 1} failed (all models): {e} — using fallback")
            frames.append(_fallback_frame(i, out_dir))

    return frames


def animate_frame(
    img_path: Path, out_path: Path, duration: float, effect: str = "zoom_in"
):
    fps = 30
    frames = int(duration * fps)
    w, h = VIDEO_WIDTH, VIDEO_HEIGHT

    if effect == "zoom_in":
        vf = (
            f"scale={int(w * 1.12)}:{int(h * 1.12)},"
            f"zoompan=z='1.12-0.12*on/{frames}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":d={frames}:s={w}x{h}:fps={fps}"
        )
    elif effect == "pan_right":
        vf = (
            f"scale={int(w * 1.15)}:{int(h * 1.15)},"
            f"zoompan=z=1.15:x='0.15*iw*on/{frames}':y='ih*0.075'"
            f":d={frames}:s={w}x{h}:fps={fps}"
        )
    else:
        vf = (
            f"scale={int(w * 1.12)}:{int(h * 1.12)},"
            f"zoompan=z='1.0+0.12*on/{frames}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
            f":d={frames}:s={w}x{h}:fps={fps}"
        )

    run_cmd(
        [
            "ffmpeg",
            "-loop",
            "1",
            "-i",
            str(img_path),
            "-vf",
            vf,
            "-t",
            str(duration),
            "-r",
            str(fps),
            "-pix_fmt",
            "yuv420p",
            str(out_path),
            "-y",
            "-loglevel",
            "quiet",
        ]
    )
