from datetime import datetime, timedelta
from functools import wraps
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, session, flash
from extensions import db, bcrypt
from sqlalchemy import case
from models import User, ApiKey
from services.key_rotator import KeyRotator

# =========================================================
# HELPER FORMAT TANGGAL & WAKTU (WIB)
# =========================================================

MONTHS_INDO = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]

def format_indo_date(d):
    if not d:
        return "Belum pernah"
    try:
        today = datetime.utcnow().date()
        target_date = d.date() if isinstance(d, datetime) else d
        day_str = f"{target_date.day} {MONTHS_INDO[target_date.month - 1]} {target_date.year}"
        
        diff = (today - target_date).days
        if diff == 0:
            return f"Hari ini ({day_str})"
        elif diff == 1:
            return f"Kemarin ({day_str})"
        else:
            return day_str
    except Exception:
        return str(d)

def format_indo_datetime(dt):
    if not dt:
        return "-"
    try:
        wib_dt = dt + timedelta(hours=7)
        month_name = MONTHS_INDO[wib_dt.month - 1]
        return f"{wib_dt.day} {month_name} {wib_dt.year}, {wib_dt.strftime('%H:%M')} WIB"
    except Exception:
        return str(dt)

def format_time_wib(dt):
    if not dt:
        return None
    try:
        wib_dt = dt + timedelta(hours=7)
        now_wib = datetime.utcnow() + timedelta(hours=7)
        if wib_dt.date() == now_wib.date():
            return f"{wib_dt.strftime('%H:%M:%S')} WIB"
        elif wib_dt.date() == (now_wib + timedelta(days=1)).date():
            return f"Besok, {wib_dt.strftime('%H:%M')} WIB"
        else:
            months = ["", "Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"]
            month_name = months[wib_dt.month] if 1 <= wib_dt.month <= 12 else str(wib_dt.month)
            return f"{wib_dt.day} {month_name}, {wib_dt.strftime('%H:%M')} WIB"
    except Exception:
        return str(dt)


admin_web_bp = Blueprint(
    "admin_web",
    __name__,
    template_folder="../templates",
)

def superadmin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        admin_id = session.get("admin_user_id")
        if not admin_id:
            if request.path.startswith("/admin/web/api") or request.is_json:
                return jsonify({"success": False, "error": "Sesi telah berakhir, silakan login kembali."}), 401
            return redirect(url_for("admin_web.login_page"))
        
        user = db.session.get(User, admin_id)
        if not user or user.role != "superadmin":
            session.clear()
            if request.path.startswith("/admin/web/api") or request.is_json:
                return jsonify({"success": False, "error": "Akses Ditolak! Dashboard ini hanya dapat diakses oleh role SUPERADMIN."}), 403
            flash("Akses Ditolak! Dashboard ini hanya dapat diakses oleh role SUPERADMIN.", "error")
            return redirect(url_for("admin_web.login_page"))
            
        return f(*args, **kwargs)
    return decorated_function


# =========================================================
# WEB PAGES
# =========================================================

@admin_web_bp.route("/login", methods=["GET", "POST"])
def login_page():
    if request.method == "POST":
        email = request.form.get("email", "").strip()
        password = request.form.get("password", "").strip()

        if not email or not password:
            flash("Email dan password wajib diisi.", "error")
            return render_template("admin/login.html")

        user = db.session.scalar(db.select(User).filter_by(email=email))
        
        if not user or not user.password_hash or not bcrypt.check_password_hash(user.password_hash, password):
            flash("Email atau password tidak valid.", "error")
            return render_template("admin/login.html")

        if user.role != "superadmin":
            flash(f"Akses Ditolak! Akun Anda memiliki role '{user.role}'. Halaman ini khusus untuk SUPERADMIN (Tim IT/Owner).", "error")
            return render_template("admin/login.html")

        # Set session (clear first to prevent fixation)
        session.clear()
        session["admin_user_id"] = user.id
        session["admin_username"] = user.username
        session["admin_email"] = user.email
        session["admin_role"] = user.role

        return redirect(url_for("admin_web.api_keys_dashboard"))

    if session.get("admin_user_id"):
        user = db.session.get(User, session.get("admin_user_id"))
        if user and user.role == "superadmin":
            return redirect(url_for("admin_web.api_keys_dashboard"))

    return render_template("admin/login.html")


@admin_web_bp.route("/logout")
def logout():
    session.clear()
    flash("Anda telah berhasil logout.", "info")
    return redirect(url_for("admin_web.login_page"))


@admin_web_bp.route("/api-keys")
@superadmin_required
def api_keys_dashboard():
    return render_template(
        "admin/api_keys.html",
        active_tab="api_keys",
        username=session.get("admin_username", "Superadmin"),
        role=session.get("admin_role", "superadmin"),
    )


@admin_web_bp.route("/users")
@superadmin_required
def users_dashboard():
    return render_template(
        "admin/users.html",
        active_tab="users",
        username=session.get("admin_username", "Superadmin"),
        role=session.get("admin_role", "superadmin"),
    )


# =========================================================
# JSON REST API UNTUK API KEYS
# =========================================================

@admin_web_bp.route("/api/keys", methods=["GET"])
@superadmin_required
def get_all_keys():
    try:
        now = datetime.utcnow()
        # Auto-restore key yang masa cooldown atau masa reset kuotanya sudah selesai
        cooling_keys = db.session.scalars(
            db.select(ApiKey).filter(
                ApiKey.status.in_(["rate_limited", "quota_exhausted"]),
                ApiKey.cooldown_until.is_not(None),
                ApiKey.cooldown_until <= now
            )
        ).all()
        if cooling_keys:
            for k in cooling_keys:
                k.status = "active"
                k.cooldown_until = None
                k.last_error_message = None
            db.session.commit()

        all_keys = db.session.scalars(
            db.select(ApiKey).order_by(ApiKey.provider.asc(), ApiKey.id.asc())
        ).all()

        gemini_keys = []
        elevenlabs_keys = []
        gemini_active = 0
        elevenlabs_active = 0
        total_requests = 0

        for k in all_keys:
            data = k.to_dict(include_key=False)
            data["cooldown_until"] = format_time_wib(k.cooldown_until) if k.cooldown_until else None
            data["last_used_at"] = format_time_wib(k.last_used_at) if k.last_used_at else None

            if k.provider == "gemini":
                gemini_keys.append(data)
                if k.is_active and k.status == "active":
                    gemini_active += 1
            elif k.provider == "elevenlabs":
                elevenlabs_keys.append(data)
                if k.is_active and k.status == "active":
                    elevenlabs_active += 1

            total_requests += (k.usage_count or 0)

        stats = {
            "total_keys": len(all_keys),
            "gemini_total": len(gemini_keys),
            "gemini_active": gemini_active,
            "elevenlabs_total": len(elevenlabs_keys),
            "elevenlabs_active": elevenlabs_active,
            "total_requests": total_requests,
        }

        return jsonify({
            "success": True,
            "stats": stats,
            "gemini_keys": gemini_keys,
            "elevenlabs_keys": elevenlabs_keys,
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


def validate_and_apply_key_status(key: ApiKey):
    """Menguji status live API Key ke provider dan menetapkan status serta estimasi waktu reset."""
    try:
        reset_time_dt = None
        if key.provider == "gemini":
            is_valid, msg = KeyRotator.test_gemini_key(key.key_value)
            # Estimasi reset kuota harian Gemini: Pukul 00:00 UTC (07:00 WIB besok)
            now_utc = datetime.utcnow()
            reset_time_dt = (now_utc + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        elif key.provider == "elevenlabs":
            is_valid, msg, reset_unix = KeyRotator.test_elevenlabs_key(key.key_value)
            if reset_unix:
                reset_time_dt = datetime.utcfromtimestamp(reset_unix)
        else:
            is_valid, msg = False, "Provider tidak dikenal."

        if is_valid:
            key.status = "active"
            key.is_active = True
            key.cooldown_until = None
            key.last_error_message = msg[:500] if (msg and key.provider == "elevenlabs") else None
        else:
            key.last_error_message = msg[:500]
            msg_lower = msg.lower()
            if "kuota" in msg_lower or "quota" in msg_lower or "credit" in msg_lower:
                key.status = "quota_exhausted"
                key.cooldown_until = reset_time_dt
                key.is_active = True
            elif "429" in msg_lower or "rate limit" in msg_lower:
                key.status = "rate_limited"
                key.cooldown_until = datetime.utcnow() + timedelta(seconds=120)
                key.is_active = True
            elif "invalid" in msg_lower or "401" in msg_lower or "403" in msg_lower or "permission" in msg_lower:
                key.status = "invalid"
                key.is_active = False
                key.cooldown_until = None
            else:
                key.status = "invalid"
                key.is_active = False
                key.cooldown_until = None
        return is_valid, msg
    except Exception as e:
        key.status = "invalid"
        key.is_active = False
        key.cooldown_until = None
        key.last_error_message = f"Gagal validasi: {str(e)[:100]}"
        return False, str(e)


@admin_web_bp.route("/api/keys", methods=["POST"])
@superadmin_required
def add_new_key():
    try:
        data = request.get_json() or {}
        provider = data.get("provider", "").strip().lower()
        key_value = data.get("key_value", "").strip()
        label = data.get("label", "").strip()

        if provider not in ["gemini", "elevenlabs"]:
            return jsonify({"success": False, "error": "Provider harus 'gemini' atau 'elevenlabs'."}), 400

        if not key_value or len(key_value) < 10:
            return jsonify({"success": False, "error": "API Key tidak boleh kosong atau terlalu pendek."}), 400

        if not label:
            label = f"{provider.capitalize()} Key #{datetime.utcnow().strftime('%m%d-%H%M')}"

        existing = db.session.scalar(db.select(ApiKey).filter_by(key_value=key_value))
        if existing:
            return jsonify({"success": False, "error": "API Key ini sudah terdaftar di sistem."}), 400

        voice_id = data.get("voice_id", "").strip() if provider == "elevenlabs" else None

        new_key = ApiKey(
            provider=provider,
            key_value=key_value,
            voice_id=voice_id,
            label=label,
            is_active=True,
            status="active"
        )
        
        # Validasi otomatis ke provider langsung saat key ditambahkan
        is_valid, msg = validate_and_apply_key_status(new_key)
        
        db.session.add(new_key)
        db.session.commit()

        return jsonify({
            "success": True,
            "message": f"API Key {provider.upper()} ({label}) berhasil ditambahkan!",
            "key": new_key.to_dict(include_key=False),
            "test_message": msg,
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@admin_web_bp.route("/api/keys/<int:key_id>/toggle", methods=["POST"])
@superadmin_required
def toggle_key_status(key_id):
    try:
        key = db.session.get(ApiKey, key_id)
        if not key:
            return jsonify({"success": False, "error": "API Key tidak ditemukan."}), 404

        key.is_active = not key.is_active
        db.session.commit()

        status_str = "Diaktifkan" if key.is_active else "Dinonaktifkan"
        return jsonify({
            "success": True,
            "message": f"API Key {key.label} berhasil {status_str}.",
            "is_active": key.is_active,
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@admin_web_bp.route("/api/keys/<int:key_id>/reset-cooldown", methods=["POST"])
@superadmin_required
def reset_key_cooldown(key_id):
    try:
        key = db.session.get(ApiKey, key_id)
        if not key:
            return jsonify({"success": False, "error": "API Key tidak ditemukan."}), 404

        if key.status == "quota_exhausted":
            return jsonify({
                "success": False,
                "error": f"API Key '{key.label}' berstatus Kuota Habis. Silakan ganti/perbarui API Key melalui tombol Edit (✏️) atau isi kuota di akun provider.",
            }), 400

        key.status = "active"
        key.cooldown_until = None
        key.last_error_message = "Cooldown di-reset secara manual oleh superadmin."
        db.session.commit()

        return jsonify({
            "success": True,
            "message": f"Status API Key {key.label} berhasil di-reset menjadi ACTIVE.",
            "key": key.to_dict(include_key=False),
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@admin_web_bp.route("/api/keys/<int:key_id>/test", methods=["POST"])
@superadmin_required
def test_single_key(key_id):
    try:
        key = db.session.get(ApiKey, key_id)
        if not key:
            return jsonify({"success": False, "error": "API Key tidak ditemukan."}), 404

        now = datetime.utcnow()
        # Jika key masih dalam masa cooldown Until, hormati cooldown dan jangan aktifkan dulu
        if key.status == "rate_limited" and key.cooldown_until and key.cooldown_until > now:
            time_wib = format_time_wib(key.cooldown_until)
            return jsonify({
                "success": False,
                "message": f"Key sedang cooldown hingga {time_wib}. Klik Reset (🔄) untuk paksa aktif.",
                "status": "rate_limited",
                "cooldown_until": time_wib,
            }), 200

        is_valid, msg = validate_and_apply_key_status(key)
        db.session.commit()

        return jsonify({
            "success": is_valid,
            "message": msg,
            "status": key.status,
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@admin_web_bp.route("/api/keys/<int:key_id>", methods=["PUT", "POST"])
@superadmin_required
def update_key(key_id):
    try:
        key = db.session.get(ApiKey, key_id)
        if not key:
            return jsonify({"success": False, "error": "API Key tidak ditemukan."}), 404

        data = request.get_json() or {}
        label = data.get("label", "").strip()
        key_value = data.get("key_value", "").strip()
        voice_id = data.get("voice_id", "").strip()

        if label:
            key.label = label

        if key_value:
            if len(key_value) < 10:
                return jsonify({"success": False, "error": "API Key baru terlalu pendek."}), 400
            key.key_value = key_value

        if key.provider == "elevenlabs":
            key.voice_id = voice_id if voice_id else None

        # Uji status live secara otomatis di background setelah update
        is_valid, msg = validate_and_apply_key_status(key)
        db.session.commit()

        return jsonify({
            "success": True,
            "message": f"API Key '{key.label}' berhasil diperbarui!",
            "key": key.to_dict(include_key=False),
            "test_message": msg,
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@admin_web_bp.route("/api/keys/<int:key_id>", methods=["DELETE"])
@superadmin_required
def delete_key(key_id):
    try:
        key = db.session.get(ApiKey, key_id)
        if not key:
            return jsonify({"success": False, "error": "API Key tidak ditemukan."}), 404

        label = key.label
        db.session.delete(key)
        db.session.commit()

        return jsonify({
            "success": True,
            "message": f"API Key '{label}' berhasil dihapus dari sistem.",
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


# =========================================================
# JSON REST API UNTUK USER & ROLE MANAGEMENT
# =========================================================

@admin_web_bp.route("/api/users", methods=["GET"])
@superadmin_required
def get_all_users():
    try:
        search_query = request.args.get("q", "").strip().lower()
        role_filter = request.args.get("role", "").strip().lower()
        
        try:
            page = max(1, int(request.args.get("page", 1)))
        except (ValueError, TypeError):
            page = 1
            
        try:
            per_page = max(1, min(100, int(request.args.get("per_page", 10))))
        except (ValueError, TypeError):
            per_page = 10

        # Global stats calculation
        all_users_total = db.session.scalars(db.select(User)).all()
        stats = {
            "total_users": len(all_users_total),
            "total_students": len([u for u in all_users_total if u.role == "user"]),
            "total_admins": len([u for u in all_users_total if u.role == "admin"]),
            "total_superadmins": len([u for u in all_users_total if u.role == "superadmin"]),
        }

        role_priority = case(
            (User.role == "superadmin", 1),
            (User.role == "admin", 2),
            else_=3
        )
        stmt = db.select(User).order_by(role_priority.asc(), User.id.desc())

        if role_filter and role_filter in ["user", "admin", "superadmin"]:
            stmt = stmt.filter(User.role == role_filter)

        filtered_users = db.session.scalars(stmt).all()

        if search_query:
            filtered_users = [
                u for u in filtered_users 
                if (search_query in u.username.lower() or search_query in u.email.lower())
            ]

        total_items = len(filtered_users)
        total_pages = max(1, (total_items + per_page - 1) // per_page)
        if page > total_pages:
            page = total_pages

        start_idx = (page - 1) * per_page
        end_idx = start_idx + per_page
        page_users = filtered_users[start_idx:end_idx]

        users_list = []
        for u in page_users:
            users_list.append({
                "id": u.id,
                "username": u.username,
                "email": u.email,
                "role": u.role or "user",
                "last_login_date": format_indo_date(u.last_login_date),
            })

        return jsonify({
            "success": True,
            "stats": stats,
            "users": users_list,
            "pagination": {
                "current_page": page,
                "per_page": per_page,
                "total_items": total_items,
                "total_pages": total_pages,
                "from_item": start_idx + 1 if total_items > 0 else 0,
                "to_item": min(end_idx, total_items),
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


@admin_web_bp.route("/api/users", methods=["POST"])
@superadmin_required
def create_user():
    try:
        data = request.get_json() or {}
        username = data.get("username", "").strip()
        email = data.get("email", "").strip().lower()
        password = data.get("password", "").strip()
        role = data.get("role", "admin").strip().lower()

        if not username or not email or not password:
            return jsonify({"success": False, "error": "Username, email, dan password wajib diisi."}), 400

        if role not in ["user", "admin", "superadmin"]:
            return jsonify({"success": False, "error": "Role tidak valid."}), 400

        if len(password) < 6:
            return jsonify({"success": False, "error": "Password minimal 6 karakter."}), 400

        # Cek email / username duplicate
        if db.session.scalar(db.select(User).filter_by(email=email)):
            return jsonify({"success": False, "error": f"Email '{email}' sudah terdaftar."}), 400

        if db.session.scalar(db.select(User).filter_by(username=username)):
            return jsonify({"success": False, "error": f"Username '{username}' sudah digunakan."}), 400

        password_hash = bcrypt.generate_password_hash(password).decode("utf-8")

        new_user = User(
            username=username,
            email=email,
            password_hash=password_hash,
            role=role,
            total_xp=0,
            streak_count=0,
        )
        db.session.add(new_user)
        db.session.commit()

        return jsonify({
            "success": True,
            "message": f"Pengguna '{username}' berhasil dibuat dengan role [{role.upper()}]!",
            "user": {
                "id": new_user.id,
                "username": new_user.username,
                "email": new_user.email,
                "role": new_user.role,
            }
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@admin_web_bp.route("/api/users/<int:user_id>/role", methods=["POST"])
@superadmin_required
def change_user_role(user_id):
    try:
        data = request.get_json() or {}
        new_role = data.get("role", "").strip().lower()

        if new_role not in ["user", "admin", "superadmin"]:
            return jsonify({"success": False, "error": "Role harus 'user', 'admin', atau 'superadmin'."}), 400

        user = db.session.get(User, user_id)
        if not user:
            return jsonify({"success": False, "error": "Pengguna tidak ditemukan."}), 404

        # Cegah superadmin mendemote akunnya sendiri jika sedang login
        current_admin_id = session.get("admin_user_id")
        if user.id == current_admin_id and new_role != "superadmin":
            return jsonify({"success": False, "error": "Anda tidak dapat menurunkan role akun Anda sendiri saat sedang login."}), 400

        old_role = user.role
        user.role = new_role
        db.session.commit()

        return jsonify({
            "success": True,
            "message": f"Role '{user.username}' berhasil diubah dari [{old_role.upper()}] menjadi [{new_role.upper()}].",
            "role": user.role,
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@admin_web_bp.route("/api/users/<int:user_id>/reset-password", methods=["POST"])
@superadmin_required
def reset_user_password(user_id):
    try:
        data = request.get_json() or {}
        new_password = data.get("new_password", "").strip()

        if not new_password or len(new_password) < 6:
            return jsonify({"success": False, "error": "Password baru minimal 6 karakter."}), 400

        user = db.session.get(User, user_id)
        if not user:
            return jsonify({"success": False, "error": "Pengguna tidak ditemukan."}), 404

        user.password_hash = bcrypt.generate_password_hash(new_password).decode("utf-8")
        db.session.commit()

        return jsonify({
            "success": True,
            "message": f"Password untuk '{user.username}' ({user.email}) berhasil di-reset!",
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500


@admin_web_bp.route("/api/users/<int:user_id>", methods=["DELETE"])
@superadmin_required
def delete_user(user_id):
    try:
        user = db.session.get(User, user_id)
        if not user:
            return jsonify({"success": False, "error": "Pengguna tidak ditemukan."}), 404

        # Cegah menghapus akun sendiri
        current_admin_id = session.get("admin_user_id")
        if user.id == current_admin_id:
            return jsonify({"success": False, "error": "Anda tidak dapat menghapus akun Anda sendiri."}), 400

        username = user.username
        db.session.delete(user)
        db.session.commit()

        return jsonify({
            "success": True,
            "message": f"Pengguna '{username}' berhasil dihapus dari sistem.",
        })
    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500
