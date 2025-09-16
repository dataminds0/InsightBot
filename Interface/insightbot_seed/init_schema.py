from pymongo import MongoClient, ASCENDING, DESCENDING, errors

MONGODB_URI = "mongodb://localhost:27017"
DB_NAME = "insightbot"

client = MongoClient(MONGODB_URI, serverSelectionTimeoutMS=3000)
dbh = client[DB_NAME]

def _norm_keys(spec: dict):
    out = []
    for k, v in spec.items():
        if v in (1, ASCENDING):
            out.append((k, ASCENDING))
        elif v in (-1, DESCENDING):
            out.append((k, DESCENDING))
        else:
            raise ValueError(f"Unsupported index direction for {k}: {v}")
    return tuple(out)

def _human_name(keys: tuple):
    return "_".join([f"{k}_{1 if d == ASCENDING else -1}" for k, d in keys])

def create_or_update_collection(name: str, json_schema: dict | None = None):
    try:
        if name not in dbh.list_collection_names():
            if json_schema:
                dbh.create_collection(name, validator={"$jsonSchema": json_schema})
            else:
                dbh.create_collection(name)
            print(f"✅ Created collection: {name}")
        else:
            print(f"ℹ️  Collection exists: {name}")
            if json_schema:
                try:
                    dbh.command({
                        "collMod": name,
                        "validator": {"$jsonSchema": json_schema},
                        "validationLevel": "moderate"
                    })
                    print(f"✅ Updated validator on: {name}")
                except errors.OperationFailure as e:
                    msg = e.details.get("errmsg", str(e)) if getattr(e, "details", None) else str(e)
                    print(f"⚠️  collMod skipped on {name}: {msg}")
    except Exception as e:
        print(f"❌ create_or_update_collection({name}) skipped due to: {e}")

def ensure_index(coll: str, spec: dict, name: str | None = None, unique: bool = False, **opts):
    try:
        keys = _norm_keys(spec)
        want_name = name or _human_name(keys)
        coll = dbh[coll]

        existing_same_keys = None
        existing_same_name = None
        try:
            for idx in coll.list_indexes():
                if tuple(idx.get("key", {}).items()) == keys:
                    existing_same_keys = idx
                if idx.get("name") == want_name:
                    existing_same_name = idx
        except errors.OperationFailure as e:
            print(f"⚠️  list_indexes warning on {coll.name}: {e}")

        if existing_same_keys:
            print(f"ℹ️  Index exists (same keys) on {coll.name}: {existing_same_keys.get('name')}")
            return existing_same_keys.get("name")

        if existing_same_name:
            want_name = f"{want_name}__auto"

        try:
            created_name = coll.create_index(keys, name=want_name, unique=unique, **opts)
            print(f"✅ Index created on {coll.name}: {created_name}  keys={dict(spec)} unique={unique}")
            return created_name
        except errors.OperationFailure as e:
            dup = ("E11000" in str(e)) or (getattr(e, "details", {}) or {}).get("code") == 11000
            if unique and dup:
                print(f"⚠️  Duplicates on {coll.name} for {want_name}. Creating non-unique fallback.")
                try:
                    created_name = coll.create_index(keys, name=want_name + "__nuniq", unique=False, **opts)
                    print(f"✅ Non-unique index created on {coll.name}: {created_name}")
                    return created_name
                except Exception as e2:
                    print(f"❌ Failed to create non-unique fallback on {coll.name}: {e2}")
                    return None
            code = (getattr(e, "details", {}) or {}).get("code")
            if code == 85 or "already exists" in str(e).lower():
                print(f"ℹ️  Index conflict on {coll.name} ({want_name}); keeping existing.")
                return None
            print(f"❌ create_index failed on {coll.name}: {e}")
            return None
    except Exception as e:
        print(f"❌ ensure_index({coll}, {spec}) skipped due to: {e}")
        return None



users_schema = {
    "bsonType": "object",
    "required": ["username", "email", "role", "is_approved", "join_date"],
    "properties": {
        "username": {"bsonType": "string"},
        "email": {"bsonType": "string"},
        "role": {"enum": ["admin", "user"]},
        "is_approved": {"bsonType": "bool"},
        "join_date": {"bsonType": "date"},
        "time_spent_minutes": {"bsonType": ["double", "int"], "minimum": 0}
    }
}
create_or_update_collection("users", users_schema)

logs_schema = {
    "bsonType": "object",
    "required": ["ts", "event"],
    "properties": {
        "ts": {"bsonType": "date"},
        "user": {"bsonType": ["string", "null"]},
        "event": {"bsonType": "string"},
        "meta": {"bsonType": "object"}
    }
}
create_or_update_collection("logs", logs_schema)

app_store_schema = {
    "bsonType": "object",
    "required": ["key", "value"],
    "properties": {
        "key": {"bsonType": "string"},
        "value": {} 
    }
}
create_or_update_collection("app_store", app_store_schema)


create_or_update_collection("articles", None)


try:
    if "user_preferences" in dbh.list_collection_names():
        dbh.drop_collection("user_preferences")
        print("🧹 Dropped legacy collection: user_preferences")
except Exception as e:
    print(f"⚠️  Could not drop user_preferences: {e}")



ensure_index("users", {"username": 1}, name="username_1", unique=True)
ensure_index("users", {"email": 1}, name="email_1", unique=True)

ensure_index("logs", {"ts": -1}, name="ts_-1")
ensure_index("logs", {"user": 1}, name="user_1")
ensure_index("logs", {"event": 1}, name="event_1")

ensure_index("app_store", {"key": 1}, name="key_1", unique=True)

ensure_index("articles", {"id": 1}, name="id_1", unique=True)
ensure_index("articles", {"fetched_at": -1}, name="fetched_at_-1")
ensure_index("articles", {"source": 1}, name="source_1")
ensure_index("articles", {"sentiment": 1}, name="sentiment_1")
ensure_index("articles", {"context": 1}, name="context_1")


try:
    res = dbh.users.update_many(
        {"time_spent_minutes": {"$exists": False}},
        {"$set": {"time_spent_minutes": 0}}
    )
    print(f"✅ Ensured time_spent_minutes. Matched: {res.matched_count}, Modified: {res.modified_count}")
except Exception as e:
    print(f"⚠️  users update_many skipped: {e}")

print("✅ InsightBot schema & indexes initialized without hard failures.")
