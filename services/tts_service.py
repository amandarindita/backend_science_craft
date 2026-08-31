import asyncio
import hashlib
import logging
import os
import requests
import edge_tts
from services.key_rotator import KeyRotator

logger = logging.getLogger(__name__)

FALLBACK_EDGE_VOICE = "id-ID-GadisNeural"
DEFAULT_VOICE = "Lala (ElevenLabs)"

def clean_text_for_speech(text: str) -> str:
    if not text:
        return ""
    # Membersihkan karakter markdown
    for ch in ["```", "`", "*", "_", "~", "#", ">", "[", "]"]:
        text = text.replace(ch, " ")
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    cleaned = ". ".join(lines)
    while "  " in cleaned:
        cleaned = cleaned.replace("  ", " ")
    return cleaned.strip()

def _generate_elevenlabs_audio(
    text: str,
    output_path: str,
    api_key: str,
    voice_id: str,
    model_id: str = "eleven_multilingual_v2",
) -> tuple[bool, int, str]:
    url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=mp3_44100_128"
    headers = {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
    }
    payload = {
        "text": text,
        "model_id": model_id,
        "voice_settings": {
            "stability": 0.35,
            "similarity_boost": 0.80,
            "style": 0.40,
            "use_speaker_boost": True,
        },
    }
    try:
        os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
        response = requests.post(url, json=payload, headers=headers, timeout=45)
        if response.status_code == 200:
            with open(output_path, "wb") as f:
                f.write(response.content)
            return True, 200, ""
        else:
            return False, response.status_code, response.text
    except Exception as e:
        return False, 500, str(e)

async def _generate_edge_audio_async(text: str, output_path: str, voice: str = FALLBACK_EDGE_VOICE):
    communicate = edge_tts.Communicate(text, voice=voice)
    await communicate.save(output_path)

def _generate_edge_audio(text: str, output_path: str, voice: str = FALLBACK_EDGE_VOICE):
    try:
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        loop.run_until_complete(_generate_edge_audio_async(text, output_path, voice=voice))
        loop.close()
    except Exception:
        asyncio.run(_generate_edge_audio_async(text, output_path, voice=voice))

def generate_submaterial_tts(
    submaterial_id: int,
    text: str,
    upload_folder: str,
    voice: str = None,
    force_refresh: bool = False
) -> str:
    cleaned = clean_text_for_speech(text)
    if not cleaned:
        return ""

    tts_dir = os.path.join(upload_folder, "tts_audio")
    os.makedirs(tts_dir, exist_ok=True)

    voice_env = os.getenv("ELEVENLABS_VOICE_ID", "").strip()
    voice_id = voice if (voice and voice != DEFAULT_VOICE) else voice_env
    model_id = os.getenv("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2").strip()

    engine_tag = f"el_{voice_id}" if voice_id else f"edge_{FALLBACK_EDGE_VOICE}"
    content_hash = hashlib.md5(f"{submaterial_id}_{engine_tag}_{cleaned}".encode("utf-8")).hexdigest()[:10]
    filename = f"submaterial_{submaterial_id}_{content_hash}.mp3"
    filepath = os.path.join(tts_dir, filename)

    if not os.path.exists(filepath) or force_refresh:
        success = False

        if voice_id:
            active_keys = KeyRotator.get_active_keys("elevenlabs")
            if not active_keys:
                env_key = os.getenv("ELEVENLABS_API_KEY", "").strip()
                if env_key:
                    print(f"[TTS] Mencoba ElevenLabs (.env Key, Voice ID: {voice_id})...")
                    ok, code, err = _generate_elevenlabs_audio(cleaned, filepath, api_key=env_key, voice_id=voice_id, model_id=model_id)
                    success = ok

            for key_obj in active_keys:
                # Prioritaskan Voice ID milik Key akun tersebut, fallback ke default voice_id
                target_voice_id = (key_obj.voice_id.strip() if getattr(key_obj, "voice_id", None) and key_obj.voice_id.strip() else None) or voice_id
                print(f"[TTS] Mencoba ElevenLabs dengan Key ID {key_obj.id} ({key_obj.label}) | Voice ID: {target_voice_id}...")
                ok, code, err = _generate_elevenlabs_audio(cleaned, filepath, api_key=key_obj.key_value, voice_id=target_voice_id, model_id=model_id)
                if ok:
                    KeyRotator.mark_success(key_obj.id)
                    print(f"[TTS] Sukses generate dengan ElevenLabs Key ID {key_obj.id}: {filename}")
                    success = True
                    break
                else:
                    print(f"[TTS] ElevenLabs Key ID {key_obj.id} gagal ({code}): {err[:150]}")
                    if code == 429:
                        KeyRotator.mark_rate_limited(key_obj.id, cooldown_seconds=300, error_message=err)
                    elif code == 401:
                        KeyRotator.mark_invalid(key_obj.id, error_message=err)
                    elif "quota" in err.lower() or "character_limit" in err.lower() or code == 400:
                        KeyRotator.mark_exhausted(key_obj.id, error_message=err)
                    else:
                        key_obj.last_error_message = err[:500]

        if not success:
            print(f"[TTS] Menggunakan fallback Edge-TTS ({FALLBACK_EDGE_VOICE})...")
            _generate_edge_audio(cleaned, filepath, voice=FALLBACK_EDGE_VOICE)
            print(f"[TTS] Sukses generate dengan Edge-TTS: {filename}")

    return f"/uploads/tts_audio/{filename}"
