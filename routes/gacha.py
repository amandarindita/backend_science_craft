from flask import Blueprint, request, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
import random
from extensions import db
from models import User, Card, UserCard, Notification

gacha_bp = Blueprint('gacha', __name__)

@gacha_bp.route('/gacha/pull', methods=['POST'])
@jwt_required()
def pull_gacha():
    user_id = int(get_jwt_identity())
    user = db.session.get(User, user_id)
    
    if not user:
        return jsonify({"error": "User tidak ditemukan"}), 404
        
    # 1. Cek apakah tiket gacha user cukup (minimal ada 1)
    if (user.gacha_tickets or 0) < 1:
        return jsonify({"error": "Tiket gacha kamu habis! Selesaikan Daily Quest dulu."}), 400
        
    # 2. Ambil semua katalog kartu yang ada di database
    all_cards = db.session.execute(db.select(Card)).scalars().all()
    if not all_cards:
        return jsonify({"error": "Katalog kartu belum tersedia."}), 500
        
    # 3. Potong 1 tiket user karena dipakai gacha
    user.gacha_tickets -= 1
    
    # 4. Pilih kartu secara acak dari katalog
    pulled_card = random.choice(all_cards)
    
    # 5. Cek apakah user sudah punya kartu ini sebelumnya
    existing_card = db.session.execute(
        db.select(UserCard).filter_by(user_id=user_id, card_id=pulled_card.id)
    ).scalar_one_or_none()
    
    is_duplicate = False
    shards_gained = 0
    
    if existing_card:
        # Kalau sudah punya (kembar), ubah jadi shards (misal dapet 5 shards)
        is_duplicate = True
        shards_gained = 5
        user.shards = (user.shards or 0) + shards_gained
    else:
        # Kalau belum punya, masukkan ke koleksi user
        new_collection = UserCard(user_id=user_id, card_id=pulled_card.id)
        db.session.add(new_collection)
        
    db.session.commit()
    
    # 6. Kirim hasil gacha balik ke frontend (buat ditampilin pas animasi terbuka)
    return jsonify({
        "message": "Gacha berhasil!",
        "is_duplicate": is_duplicate,
        "shards_gained": shards_gained,
        "remaining_tickets": user.gacha_tickets,
        "total_shards": user.shards,
        "card": {
            "id": pulled_card.id,
            "name": pulled_card.name,
            "rarity": pulled_card.rarity,
            "description": pulled_card.description,
            "image_url": pulled_card.image_url
        }
    }), 200

@gacha_bp.route('/gacha/craft', methods=['POST'])
@jwt_required()
def craft_card():
    user_id = int(get_jwt_identity())
    data = request.get_json() or {}
    target_card_id = data.get('card_id')
    
    if not target_card_id:
        return jsonify({"error": "ID kartu yang ingin di-craft wajib diisi."}), 400
        
    user = db.session.get(User, user_id)
    card_to_craft = db.session.get(Card, target_card_id)
    
    if not user or not card_to_craft:
        return jsonify({"error": "User atau kartu tidak ditemukan."}), 404
        
    # Cek apakah user sudah punya kartu itu sebelumnya
    already_owned = db.session.execute(
        db.select(UserCard).filter_by(user_id=user_id, card_id=target_card_id)
    ).scalar_one_or_none()
    
    if already_owned:
        return jsonify({"error": "Kamu sudah memiliki kartu ini di koleksimu!"}), 400
        
    # Tentukan harga shard untuk crafting (misalnya butuh 20 shards)
    craft_cost = 20
    if (user.shards or 0) < craft_cost:
        return jsonify({"error": f"Shards kamu kurang! Butuh {craft_cost} shards."}), 400
        
    # Potong shards user dan masukkan kartu ke koleksinya
    user.shards -= craft_cost
    new_collection = UserCard(user_id=user_id, card_id=target_card_id)
    db.session.add(new_collection)
    db.session.commit()
    
    return jsonify({
        "message": "Berhasil membuat kartu pilihanmu!",
        "remaining_shards": user.shards,
        "card": {
            "id": card_to_craft.id,
            "name": card_to_craft.name,
            "rarity": card_to_craft.rarity,
            "image_url": card_to_craft.image_url
        }
    }), 200