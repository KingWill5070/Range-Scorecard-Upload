from database import SessionLocal
from models import User
from auth_utils import hash_password
import uuid

db = SessionLocal()

admin_user = User(
    user_id=str(uuid.uuid4()),
    username="harold",
    hashed_password=hash_password("Harold123!"),
    role="admin"
)

db.add(admin_user)
db.commit()
db.close()

print("Admin user created successfully.")
