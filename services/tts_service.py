import asyncio
import hashlib
import os
import re
import edge_tts

# id-ID Audio list
# id-ID-ArdiNeural
# id-ID-BellaNeural
# id-ID-BinbinNeural
# id-ID-DewiNeural
# id-ID-GadisNeural
# id-ID-HafizahNeural
# id-ID-HasanNeural
# id-ID-IkaNeural
# id-ID-KamarulNeural
# id-ID-PutuNeural
# id-ID-RinaNeural
# id-ID-YuniNeural

# en-US Audio list
# en-US-AvaMultilingualNeural
# en-US-AndrewMultilingualNeural
# en-US-AnaNeural
# en-US-AriaNeural
# en-US-AvaMultilingualNeural
# en-US-CoraNeural
# en-US-DaisyNeural
# en-US-DianaNeural
# en-US-ElenaNeural
# en-US-EmmaNeural
# en-US-FinnNeural
# en-US-GraceNeural
# en-US-IanNeural
# en-US-JennyNeural
# en-US-LisaNeural
# en-US-LisaMultilingualNeural
# en-US-MadelynNeural
# en-US-MadelynMultilingualNeural
# en-US-MargaretNeural
# en-US-NancyNeural
# en-US-NathanNeural
# en-US-OliviaNeural
# en-US-NancyNeural
# en-US-OliviaNeural
# en-US-PamelaNeural
# en-US-RyanNeural
# en-US-SaraNeural
# en-US-SaraMultilingualNeural
# en-US-StevenNeural
# en-US-TaylorNeural
# en-US-ThomasNeural
# en-US-TysonNeural
# en-US-ValerieNeural
# en-US-WilliamNeural

DEFAULT_VOICE = "en-US-AndrewMultilingualNeural"
FEMALE_VOICE = "id-ID-ArdiNeural"

def clean_text_for_speech(text: str) -> str:
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

async def _generate_audio_async(text: str, output_path: str, voice: str = DEFAULT_VOICE):
    communicate = edge_tts.Communicate(text, voice=voice)
    await communicate.save(output_path)

def generate_submaterial_tts(submaterial_id: int, text: str, upload_folder: str, voice: str = DEFAULT_VOICE, force_refresh: bool = False) -> str:
    cleaned = clean_text_for_speech(text)
    if not cleaned:
        return ""

    tts_dir = os.path.join(upload_folder, "tts_audio")
    os.makedirs(tts_dir, exist_ok=True)

    content_hash = hashlib.md5(f"{submaterial_id}_{voice}_{cleaned}".encode("utf-8")).hexdigest()[:10]
    filename = f"submaterial_{submaterial_id}_{content_hash}.mp3"
    filepath = os.path.join(tts_dir, filename)

    if not os.path.exists(filepath) or force_refresh:
        try:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(_generate_audio_async(cleaned, filepath, voice=voice))
            loop.close()
        except Exception:
            asyncio.run(_generate_audio_async(cleaned, filepath, voice=voice))

    return f"/uploads/tts_audio/{filename}"
