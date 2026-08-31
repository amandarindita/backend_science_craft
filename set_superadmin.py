import sys
from app import app
from extensions import db
from models import User

def set_role(email, role="superadmin"):
    with app.app_context():
        user = db.session.scalar(db.select(User).filter_by(email=email.strip()))
        if not user:
            print(f"Error: User dengan email '{email}' tidak ditemukan.")
            return
        
        user.role = role.strip().lower()
        db.session.commit()
        print(f"Sukses! User '{user.username}' ({user.email}) sekarang memiliki role: '{user.role}'")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Penggunaan: python set_superadmin.py <email_user> [role]")
        print("Contoh: python set_superadmin.py amanda.dita@gmail.com superadmin")
    else:
        target_email = sys.argv[1]
        target_role = sys.argv[2] if len(sys.argv) > 2 else "superadmin"
        set_role(target_email, target_role)
