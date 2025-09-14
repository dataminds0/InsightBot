import pandas as pd
import os
from pymongo import MongoClient

# ====== MongoDB connection setup ======
client = MongoClient("mongodb://localhost:27017/")  # adjust host/port/user/password if needed
db = client["insightbot"]
collection = db["articles"]

# ====== Fetch all data from MongoDB ======
data = list(collection.find())

# ====== Convert to DataFrame ======
df_new = pd.DataFrame(data)

# If MongoDB _id exists, convert to string to prevent duplicates
df_new['_id'] = df_new['_id'].astype(str)

# ====== Read existing CSV if it exists ======
csv_path = r"../data/report_data/data.csv"
os.makedirs(os.path.dirname(csv_path), exist_ok=True)  # create folder if not exists

try:
    df_existing = pd.read_csv(csv_path)
except FileNotFoundError:
    df_existing = pd.DataFrame()

# ====== Merge new data with existing without duplicates ======
if not df_existing.empty:
    df = pd.concat([df_new, df_existing], ignore_index=True)
    df.drop_duplicates(subset=['_id'], inplace=True)
else:
    df = df_new

# ====== Reset 'id' column from 1 to last row ======
df = df.reset_index(drop=True)
df['id'] = df.index + 1  # numbering starts from 1

# ====== Save the result to CSV ======
df.to_csv(csv_path, index=False)
print(f"{csv_path} has been updated successfully with reset id!")
