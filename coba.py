from elevenlabs.client import ElevenLabs
from elevenlabs.types import VoiceSettings

# Inisialisasi client dengan API key kamu
client = ElevenLabs(
    api_key="sk_d582d70dbd4637763b8f5bf3e03e938ea32dbb34c5937134"
)

# Generate audio
audio_stream = client.text_to_speech.convert(
    text="Per",
    voice_id="4UNmeS5ijruDobVfcjih",  # Ganti dengan Voice ID pilihanmu
    model_id="eleven_multilingual_v2",  # Model terbaik untuk multi-bahasa
    voice_settings=VoiceSettings(
        stability=0.35,        # Nilai lebih rendah = lebih ekspresif/hidup
        similarity_boost=0.80, # Menjaga kejelasan vokal
        style=0.50,            # Menambah gaya bicara naratif
        use_speaker_boost=True
    ),
    output_format="mp3_44100_128",
)

# Simpan ke file mp3
with open("output_elevenlabs.mp3", "wb") as f:
    for chunk in audio_stream:
        f.write(chunk)

print("Audio berhasil dibuat!")