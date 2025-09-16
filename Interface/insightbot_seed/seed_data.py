from pymongo import MongoClient
from datetime import datetime

MONGODB_URI = "mongodb://localhost:27017"
DB_NAME = "insightbot"

client = MongoClient(MONGODB_URI)
dbh = client[DB_NAME]
try:
    if "user_preferences" in dbh.list_collection_names():
        dbh.drop_collection("user_preferences")
        print("🧹 Dropped legacy collection: user_preferences")
    else:
        print("ℹ️ Legacy collection 'user_preferences' not found. Nothing to drop.")
except Exception as e:
    print(f"⚠️ Could not drop 'user_preferences': {e}")

ADMIN_USERNAME = "admin"
ADMIN_EMAIL = "admin@example.com"
ADMIN_PASSWORD_HASH = "$2b$12$ER/DoxvvW0wsdQd/XcBXhuTAUPFW6es1ucB4cB5gKCllD.txLX/zm"

existing_admin = dbh.users.find_one({"username": ADMIN_USERNAME})
if existing_admin:
    print(f"ℹ️ Admin user '{ADMIN_USERNAME}' already exists. Skipping creation.")
else:
    dbh.users.insert_one({
        "username": ADMIN_USERNAME,
        "email": ADMIN_EMAIL,
        "role": "admin",
        "password_hash": ADMIN_PASSWORD_HASH,
        "is_approved": True,
        "join_date": datetime.utcnow()
    })
    print(f"✅ Created admin user '{ADMIN_USERNAME}' (password: admin123).")


dbh.app_store.update_one(
    {"key": "last_page"},
    {"$set": {"value": "dashboard"}},
    upsert=True
)
print("✅ app_store.last_page set to 'dashboard' (upsert).")

dbh.app_store.update_one(
    {"key": "app_version"},
    {"$set": {"value": "1.0.0"}},
    upsert=True
)
print("✅ app_store.app_version set to '1.0.0' (upsert).")

print("\n🎉 Seeding finished successfully.")
