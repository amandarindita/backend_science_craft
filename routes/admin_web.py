from datetime import datetime
from functools import wraps
from flask import Blueprint, render_template, request, jsonify, redirect, url_for, session, flash
from extensions import db, bcrypt
from models import User, ApiKey
from services.key_rotator import KeyRotator

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
            return redirect(url_for("admin_web.login_page"))
        
        user = db.session.get(User, admin_id)
        if not user or user.role != "superadmin":
            session.clear()
            flash("Akses Ditolak! Dashboard API Key ini hanya dapat diakses oleh role SUPERADMIN.", "error")
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

        # STRICT CHECK: Hanya SUPERADMIN yang diizinkan masuk
        if user.role != "superadmin":
            flash(f"Akses Ditolak! Akun Anda memiliki role '{user.role}'. Halaman ini khusus untuk SUPERADMIN (Tim IT/Owner).", "error")
            return render_template("admin/login.html")

        # Set session
        session["admin_user_id"] = user.id
        session["admin_username"] = user.username
        session["admin_email"] = user.email
        session["admin_role"] = user.role

        return redirect(url_for("admin_web.api_keys_dashboard"))

    # If already logged in as superadmin, redirect to dashboard
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
        username=session.get("admin_username", "Superadmin"),
        role=session.get("admin_role", "superadmin"),
    )


# =========================================================
# JSON REST API UNTUK DASHBOARD (HANYA SUPERADMIN)
# =========================================================

@admin_web_bp.route("/api/keys", methods=["GET"])
@superadmin_required
def get_all_keys():
    try:
        keys = db.session.scalars(db.select(ApiKey).order_by(ApiKey.created_at.desc())).all()
        
        gemini_keys = [k.to_dict(include_key=False) for k in keys if k.provider == "gemini"]
        elevenlabs_keys = [k.to_dict(include_key=False) for k in keys if k.provider == "elevenlabs"]

        # Summary stats
        stats = {
            "total_keys": len(keys),
            "gemini_total": len(gemini_keys),
            "gemini_active": len([k for k in gemini_keys if k["is_active"] and k["status"] == "active"]),
            "elevenlabs_total": len(elevenlabs_keys),
            "elevenlabs_active": len([k for k in elevenlabs_keys if k["is_active"] and k["status"] == "active"]),
            "total_requests": sum(k.usage_count for k in keys),
        }

        return jsonify({
            "success": True,
            "stats": stats,
            "gemini_keys": gemini_keys,
            "elevenlabs_keys": elevenlabs_keys,
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


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

        new_key = ApiKey(
            provider=provider,
            key_value=key_value,
            label=label,
            is_active=True,
            status="active"
        )
        db.session.add(new_key)
        db.session.commit()

        return jsonify({
            "success": True,
            "message": f"API Key {provider.upper()} ({label}) berhasil ditambahkan!",
            "key": new_key.to_dict(include_key=False),
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

        if key.provider == "gemini":
            is_valid, msg = KeyRotator.test_gemini_key(key.key_value)
        elif key.provider == "elevenlabs":
            is_valid, msg = KeyRotator.test_elevenlabs_key(key.key_value)
        else:
            return jsonify({"success": False, "error": "Provider tidak dikenal."}), 400

        if is_valid:
            key.status = "active"
            key.cooldown_until = None
            key.last_error_message = None
        else:
            key.last_error_message = msg[:500]
        db.session.commit()

        return jsonify({
            "success": is_valid,
            "message": msg,
            "status": key.status,
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
