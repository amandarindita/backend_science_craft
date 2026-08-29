import asyncio
import hashlib
import os
import re
import requests
import edge_tts

# Default fallback voice for Edge TTS if ElevenLabs is unavailable
FALLBACK_EDGE_VOICE = "id-ID-GadisNeural"
DEFAULT_VOICE = "Lala (ElevenLabs)"

def clean_text_for_speech(text: str) -> str:
    """
    Membersihkan teks dari elemen Markdown dan format yang tidak perlu dibaca oleh TTS.
    Membuat teks lebih hemat karakter (sangat penting untuk kuota ElevenLabs) dan intonasi lebih natural.
    """
    if not text:
        return ""
    # Remove code blocks
    cleaned = re.sub(r'```[\s\S]*?```', '', text)
    # Remove inline code
    cleaned = re.sub(r'`([^`]+)`', r'\1', cleaned)
    # Remove image markdown ![alt](url)
    cleaned = re.sub(r'!\[[^\]]*\]\([^)]*\)', '', cleaned)
    # Remove link markdown [text](url) -> text
    cleaned = re.sub(r'\[([^\]]+)\]\([^)]*\)', r'\1', cleaned)
    # Remove header markers #
    cleaned = re.sub(r'#+\s*', '', cleaned)
    # Remove bold/italic markers * or _ or ~
    cleaned = re.sub(r'[*_~]', '', cleaned)
    # Remove bullet markers (- or * or +) at start of line
    cleaned = re.sub(r'^[ \t]*[-*+][ \t]+', '', cleaned, flags=re.MULTILINE)
    # Remove numbered lists at start of line (e.g. 1. )
    cleaned = re.sub(r'^[ \t]*\d+\.[ \t]+', '', cleaned, flags=re.MULTILINE)
    # Clean whitespace and newlines into smooth sentence pauses
    cleaned = re.sub(r'\n+', '. ', cleaned)
    cleaned = re.sub(r'\s+', ' ', cleaned)
    # Clean multiple consecutive dots
    cleaned = re.sub(r'\.{2,}', '.', cleaned)
    return cleaned.strip()

import os
import requests


def _generate_elevenlabs_audio(
    text: str,
    output_path: str,
    api_key: str,
    voice_id: str,
    model_id: str = "eleven_multilingual_v2",
) -> bool:
  """Generate audio menggunakan ElevenLabs REST API v1 dengan tuning karakter tutor santai."""
  # Menambahkan query params output_format agar latency & kualitas optimal
  url = f"https://api.elevenlabs.io/v1/text-to-speech/{voice_id}?output_format=mp3_44100_128"

  headers = {
      "xi-api-key": api_key,
      "Content-Type": "application/json",
  }

  payload = {
      "text": text,
      "model_id": model_id,
      "voice_settings": {
          "stability": 0.35,  # Lebih dinamis & ekspresif
          "similarity_boost": 0.80,  # Mempertahankan warna vokal karakter
          "style": 0.40,  # Nada tutor yang santai & engaging
          "use_speaker_boost": True,
      },
  }

  try:
    # Memastikan folder direktori tujuan sudah ada
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    response = requests.post(url, json=payload, headers=headers, timeout=45)

    if response.status_code == 200:
      with open(output_path, "wb") as f:
        f.write(response.content)
      return True
    else:
      print(
          f"[ElevenLabs Error] Status {response.status_code}: {response.text}"
      )
      return False

  except Exception as e:
    print(f"[ElevenLabs Request Exception]: {str(e)}")
    return False

async def _generate_edge_audio_async(text: str, output_path: str, voice: str = FALLBACK_EDGE_VOICE):
    """
    Generate audio menggunakan Edge-TTS sebagai fallback gratis.
    """
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
    """
    Membuat file MP3 TTS untuk submateri pembelajaran dengan fitur Caching.
    
    Urutan Prioritas:
    1. Menggunakan ElevenLabs jika ELEVENLABS_API_KEY & ELEVENLABS_VOICE_ID tersedia.
    2. Fallback otomatis ke Edge-TTS jika ElevenLabs gagal (kuota habis / network error / key belum ada).
    3. Menggunakan Cache lokal jika audio sudah pernah dibuat untuk konten teks yang sama.
    """
    cleaned = clean_text_for_speech(text)
    if not cleaned:
        return ""

    tts_dir = os.path.join(upload_folder, "tts_audio")
    os.makedirs(tts_dir, exist_ok=True)

    # Konfigurasi ElevenLabs dari environment
    api_key = os.getenv("ELEVENLABS_API_KEY", "").strip()
    voice_env = os.getenv("ELEVENLABS_VOICE_ID", "").strip()
    # Jika voice adalah DEFAULT_VOICE atau tidak ada, gunakan voice_id dari .env
    voice_id = voice if (voice and voice != DEFAULT_VOICE) else voice_env
    model_id = os.getenv("ELEVENLABS_MODEL_ID", "eleven_multilingual_v2").strip()

    engine_tag = f"el_{voice_id}" if (api_key and voice_id) else f"edge_{FALLBACK_EDGE_VOICE}"
    content_hash = hashlib.md5(f"{submaterial_id}_{engine_tag}_{cleaned}".encode("utf-8")).hexdigest()[:10]
    filename = f"submaterial_{submaterial_id}_{content_hash}.mp3"
    filepath = os.path.join(tts_dir, filename)

    # Caching check: jika file sudah ada dan tidak di-force refresh, gunakan cache yang ada
    if not os.path.exists(filepath) or force_refresh:
        success = False
        if api_key and voice_id:
            print(f"[TTS] Mencoba generate dengan ElevenLabs (Voice ID: {voice_id})...")
            success = _generate_elevenlabs_audio(cleaned, filepath, api_key=api_key, voice_id=voice_id, model_id=model_id)
            if success:
                print(f"[TTS] Sukses generate dengan ElevenLabs: {filename}")

        # Jika ElevenLabs gagal atau tidak dikonfigurasi, gunakan fallback Edge-TTS
        if not success:
            print(f"[TTS] Menggunakan fallback Edge-TTS ({FALLBACK_EDGE_VOICE})...")
            _generate_edge_audio(cleaned, filepath, voice=FALLBACK_EDGE_VOICE)
            print(f"[TTS] Sukses generate dengan Edge-TTS: {filename}")

    return f"/uploads/tts_audio/{filename}"
