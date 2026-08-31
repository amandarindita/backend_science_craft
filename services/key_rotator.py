# services/key_rotator.py
from datetime import datetime, timedelta
import logging
import os
import requests
import google.generativeai as genai
from extensions import db
from models import ApiKey

logger = logging.getLogger(__name__)

class KeyRotator:
    """
    Sistem cerdas untuk mengelola pool API Key (Gemini & ElevenLabs).
    Mendukung rotasi dinamis, load balancing (least-used), 
    auto-cooldown saat limit (429), dan auto-failover ke key cadangan.
    """

    @staticmethod
    def get_active_keys(provider: str):
        """
        Mengambil semua API key aktif untuk provider tertentu.
        Otomatis me-reset status key yang masa cooldown-nya sudah selesai.
        Disortir berdasarkan least-used (usage_count ASC, last_used_at ASC).
        """
        now = datetime.utcnow()
        try:
            # 1. Cek dan pulihkan key yang sudah lewat masa cooldown
            cooling_keys = db.session.scalars(
                db.select(ApiKey).filter(
                    ApiKey.provider == provider,
                    ApiKey.is_active == True,
                    ApiKey.status == "rate_limited",
                    ApiKey.cooldown_until <= now
                )
            ).all()

            if cooling_keys:
                for k in cooling_keys:
                    k.status = "active"
                    k.cooldown_until = None
                    k.last_error_message = "Cooldown expired, restored to active"
                db.session.commit()
                logger.info(f"[KeyRotator] {len(cooling_keys)} key(s) {provider} berhasil dipulihkan dari cooldown.")

            # 2. Ambil semua key yang berstatus active
            keys = db.session.scalars(
                db.select(ApiKey).filter(
                    ApiKey.provider == provider,
                    ApiKey.is_active == True,
                    ApiKey.status == "active"
                ).order_by(ApiKey.usage_count.asc(), ApiKey.last_used_at.asc())
            ).all()

            return keys

        except Exception as e:
            logger.error(f"[KeyRotator] Error fetching active keys for {provider}: {e}")
            db.session.rollback()
            return []

    @staticmethod
    def mark_rate_limited(key_id: int, cooldown_seconds: int = 120, error_message: str = None):
        """Menandai key terkena rate limit (429) dan memberikan masa pendinginan (cooldown)."""
        try:
            key = db.session.get(ApiKey, key_id)
            if key:
                key.status = "rate_limited"
                key.cooldown_until = datetime.utcnow() + timedelta(seconds=cooldown_seconds)
                key.last_error_message = (error_message or "Rate limit hit (429)")[:500]
                db.session.commit()
                logger.warning(f"[KeyRotator] Key ID {key_id} ({key.label}) di-set cooldown selama {cooldown_seconds}s.")
        except Exception as e:
            logger.error(f"[KeyRotator] Error setting rate limit for key {key_id}: {e}")
            db.session.rollback()

    @staticmethod
    def mark_exhausted(key_id: int, error_message: str = None):
        """Menandai kuota bulanan/harian key habis permanen."""
        try:
            key = db.session.get(ApiKey, key_id)
            if key:
                key.status = "quota_exhausted"
                
                if key.provider == "gemini":
                    key.last_error_message = "Error 429: Kuota harian (Daily Quota) habis untuk hari ini."
                    now_utc = datetime.utcnow()
                    key.cooldown_until = (now_utc + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
                else:
                    key.last_error_message = (error_message or "Quota exhausted")[:500]
                    
                db.session.commit()
                logger.warning(f"[KeyRotator] Key ID {key_id} ({key.label}) ditandai quota_exhausted.")
        except Exception as e:
            logger.error(f"[KeyRotator] Error setting quota_exhausted for key {key_id}: {e}")
            db.session.rollback()

    @staticmethod
    def mark_invalid(key_id: int, error_message: str = None):
        """Menandai key tidak valid / API key salah / revoked."""
        try:
            key = db.session.get(ApiKey, key_id)
            if key:
                key.status = "invalid"
                key.is_active = False
                key.last_error_message = (error_message or "Invalid API Key")[:500]
                db.session.commit()
                logger.error(f"[KeyRotator] Key ID {key_id} ({key.label}) ditandai invalid.")
        except Exception as e:
            logger.error(f"[KeyRotator] Error setting invalid for key {key_id}: {e}")
            db.session.rollback()

    @staticmethod
    def mark_success(key_id: int):
        """Mencatat request berhasil, menambah counter usage, dan memperbarui timestamp."""
        try:
            key = db.session.get(ApiKey, key_id)
            if key:
                key.usage_count += 1
                key.last_used_at = datetime.utcnow()
                key.status = "active"
                db.session.commit()
        except Exception as e:
            logger.error(f"[KeyRotator] Error marking success for key {key_id}: {e}")
            db.session.rollback()

    @classmethod
    def call_gemini_rotator(cls, model_name: str, generate_func):
        """
        Mengeksekusi panggilan ke Gemini API dengan failover pool otomatis.
        Jika satu key terkena limit (429/ResourceExhausted), otomatis mencoba key berikutnya.
        """
        active_keys = cls.get_active_keys("gemini")

        # Fallback jika di DB belum ada key aktif, coba dari .env
        if not active_keys:
            env_key = os.getenv("GEMINI_API_KEY", "").strip()
            if env_key:
                logger.info("[KeyRotator] Menggunakan fallback GEMINI_API_KEY dari .env")
                genai.configure(api_key=env_key)
                model = genai.GenerativeModel(model_name)
                return generate_func(model)
            raise RuntimeError("Tidak ada API Key Gemini yang aktif dan tersedia saat ini.")

        last_exception = None

        for key_obj in active_keys:
            try:
                # Konfigurasi Gemini dengan key saat ini
                genai.configure(api_key=key_obj.key_value)
                model = genai.GenerativeModel(model_name)
                
                result = generate_func(model)
                
                # Sukses -> update usage
                cls.mark_success(key_obj.id)
                return result

            except Exception as e:
                err_str = str(e)
                err_lower = err_str.lower()
                last_exception = e
                logger.warning(f"[KeyRotator] Gemini gagal dengan Key ID {key_obj.id} ({key_obj.label}): {e}")

                if "generaterequestsperday" in err_lower or "perday" in err_lower or "check your plan and billing" in err_lower:
                    # Kuota harian habis -> quota_exhausted
                    cls.mark_exhausted(key_obj.id, error_message=str(e))
                elif "429" in err_str or "resource_exhausted" in err_lower or "rate limit" in err_lower:
                    # Rate limit sementara per menit -> Cooldown 2 menit lalu coba key lain
                    cls.mark_rate_limited(key_obj.id, cooldown_seconds=120, error_message=str(e))
                elif "api_key_invalid" in err_lower or "401" in err_str or "403" in err_str or "permission" in err_lower:
                    # Key Salah -> Nonaktifkan
                    cls.mark_invalid(key_obj.id, error_message=str(e))
                else:
                    # Error lain (misal safety filter atau timeout)
                    key_obj.last_error_message = str(e)[:500]
                    try:
                        db.session.commit()
                    except Exception:
                        db.session.rollback()

        # Jika seluruh key di pool gagal
        raise last_exception or RuntimeError("Seluruh API Key Gemini dalam pool sedang tidak dapat digunakan.")

    @classmethod
    def test_gemini_key(cls, key_value: str) -> tuple[bool, str]:
        """Test langsung keaslian dan status API Key Gemini."""
        if not key_value or len(key_value.strip()) < 10:
            return False, "API Key terlalu pendek atau kosong."

        try:
            genai.configure(api_key=key_value.strip())
            # Coba model untuk tes ping
            model = genai.GenerativeModel("gemini-2.5-flash")
            response = model.generate_content("Balas kata 'PONG' saja.")
            if response and response.text:
                return True, ""
            return True, ""
        except Exception as e:
            err_str = str(e)
            err_lower = err_str.lower()
            if "generaterequestsperday" in err_lower or "perday" in err_lower or "check your plan and billing" in err_lower or "quota exceeded" in err_lower:
                return False, "Error 429: Kuota harian (Daily Quota) habis untuk hari ini."
            elif "429" in err_str or "resource_exhausted" in err_lower or "rate limit" in err_lower:
                return False, "Error 429: Rate limit RPM (terlalu banyak request/menit)."
            elif "api_key_invalid" in err_lower or "invalid_argument" in err_lower or "400" in err_str or "403" in err_str or "api key not valid" in err_lower:
                return False, "Error: API Key Gemini salah atau tidak valid."
            return False, f"Error: {err_str[:80]}"

    @classmethod
    def test_elevenlabs_key(cls, key_value: str) -> tuple[bool, str, int | None]:
        """Test langsung keaslian dan status API Key ElevenLabs beserta estimasi waktu reset kuota."""
        if not key_value or len(key_value.strip()) < 10:
            return False, "API Key terlalu pendek atau kosong.", None

        try:
            url = "https://api.elevenlabs.io/v1/user/subscription"
            headers = {"xi-api-key": key_value.strip()}
            res = requests.get(url, headers=headers, timeout=10)

            if res.status_code == 200:
                data = res.json()
                char_count = data.get("character_count", 0)
                char_limit = data.get("character_limit", 0)
                tier = data.get("tier", "free")
                reset_unix = data.get("next_character_count_reset_unix")
                remaining = max(0, char_limit - char_count)
                if char_limit > 0 and char_count >= char_limit:
                    return False, f"Error: Kuota karakter bulanan habis ({char_count:,}/{char_limit:,}).", reset_unix
                return True, f"Sisa Kuota: {remaining:,} / {char_limit:,} karakter ({tier.upper()})", reset_unix

            # Penanganan khusus Restricted / Fine-Grained API Key & Error Codes
            if res.status_code in (400, 401):
                try:
                    err_json = res.json()
                    detail = err_json.get("detail", {})
                    if isinstance(detail, dict):
                        if detail.get("status") == "missing_permissions":
                            return True, "Sukses! API Key valid & aktif (Restricted TTS Scope).", None
                        code = detail.get("code", "")
                        msg = detail.get("message", "")
                        if code == "invalid_api_key" or "invalid" in msg.lower() or "must be exactly" in msg.lower():
                            return False, "Error: API Key ElevenLabs salah atau tidak valid.", None
                        if "quota" in msg.lower() or "credit" in msg.lower():
                            return False, "Error: Kuota karakter ElevenLabs habis.", None
                except Exception:
                    pass
                return False, "Error: API Key ElevenLabs salah atau tidak valid.", None
            elif res.status_code == 403:
                return False, "Error 403: Akses ditolak oleh ElevenLabs.", None
            elif res.status_code == 429:
                return False, "Error 429: Rate limit request sementara (terlalu cepat).", None
            elif res.status_code >= 500:
                return False, "Error 500: Server ElevenLabs sedang gangguan/down.", None
            else:
                return False, "Error: Verifikasi API Key ElevenLabs gagal.", None
        except Exception as e:
            return False, f"Gagal koneksi ke ElevenLabs: {str(e)[:80]}", None
