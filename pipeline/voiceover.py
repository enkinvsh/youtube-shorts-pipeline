"""ElevenLabs TTS + edge-tts (Russian) + macOS say fallback."""

import asyncio
from pathlib import Path

import requests

from .config import VOICE_ID_EN, VOICE_ID_HI, VOICE_RU, get_elevenlabs_key, run_cmd
from .log import log
from .retry import with_retry


@with_retry(max_retries=3, base_delay=2.0)
def _call_elevenlabs(script: str, voice_id: str, api_key: str) -> bytes:
    r = requests.post(
        f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}",
        headers={"xi-api-key": api_key, "Content-Type": "application/json"},
        json={
            "text": script,
            "model_id": "eleven_multilingual_v2",
            "voice_settings": {
                "stability": 0.4,
                "similarity_boost": 0.85,
                "style": 0.3,
                "use_speaker_boost": True,
            },
        },
        timeout=60,
    )
    if r.status_code != 200:
        raise RuntimeError(f"ElevenLabs {r.status_code}: {r.text[:200]}")
    return r.content


def _edge_tts_generate(script: str, voice: str, output_path: Path) -> Path:
    """Generate audio via edge-tts (free Microsoft TTS, supports Russian)."""
    import edge_tts

    async def _generate():
        communicate = edge_tts.Communicate(script, voice, rate="+5%")
        await communicate.save(str(output_path))

    asyncio.run(_generate())
    return output_path


def _say_fallback(script: str, out_dir: Path) -> Path:
    out_path = out_dir / "voiceover_say.aiff"
    mp3_path = out_dir / "voiceover_say.mp3"
    run_cmd(["say", "-o", str(out_path), script])
    run_cmd(
        [
            "ffmpeg",
            "-i",
            str(out_path),
            "-acodec",
            "libmp3lame",
            str(mp3_path),
            "-y",
            "-loglevel",
            "quiet",
        ]
    )
    return mp3_path


def generate_voiceover(script: str, out_dir: Path, lang: str = "en") -> Path:
    if lang == "ru":
        log(f"Generating Russian voiceover via edge-tts ({VOICE_RU})...")
        out_path = out_dir / "voiceover_ru.mp3"
        try:
            return _edge_tts_generate(script, VOICE_RU, out_path)
        except Exception as e:
            log(f"edge-tts failed: {e} — using macOS say fallback")
            return _say_fallback(script, out_dir)

    voice_id = VOICE_ID_HI if lang == "hi" else VOICE_ID_EN
    api_key = get_elevenlabs_key()

    if not api_key:
        log("No ElevenLabs key — using macOS 'say' fallback")
        return _say_fallback(script, out_dir)

    log(f"Generating {lang} voiceover via ElevenLabs...")
    out_path = out_dir / f"voiceover_{lang}.mp3"

    try:
        audio_bytes = _call_elevenlabs(script, voice_id, api_key)
        out_path.write_bytes(audio_bytes)
        log(f"Voiceover saved: {out_path.name}")
        return out_path
    except Exception as e:
        log(f"ElevenLabs failed: {e} — using 'say' fallback")
        return _say_fallback(script, out_dir)
