from app import app, db
from models import Card

def seed_cards():
    with app.app_context():
        # Ganti teks '/uploads/cards/...' sesuai nama file gambar aslimu!
        initial_cards = [
            Card(name="Albert Einstein", rarity="Legendary", image_url="/uploads/cards/charles_darwin.png"),
            Card(name="Marie Curie", rarity="Epic", image_url="/uploads/cards/marie_curie.png"),
            Card(name="Isaac Newton", rarity="Rare", image_url="/uploads/cards/isaac_newton.png")
        ]
        
        for card in initial_cards:
            exists = db.session.scalar(db.select(Card).where(Card.name == card.name))
            if not exists:
                db.session.add(card)
                
        db.session.commit()
        print("✅ Data kartu awal berhasil disuntikkan ke database!")

if __name__ == "__main__":
    seed_cards()