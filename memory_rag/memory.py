from pymilvus import MilvusClient
import random
import time
import requests
import os
from dotenv import load_dotenv



CLIENT_NAME="SUINA_MEM.db"
DB_MEM_NAME="SUINA_COLLECTION_V1"
client = MilvusClient(CLIENT_NAME)

if client.has_collection(collection_name=DB_MEM_NAME):
    client.drop_collection(collection_name=DB_MEM_NAME)
client.create_collection(
    collection_name=DB_MEM_NAME,
    dimension=768,  # The vectors we will use in this demo has 768 dimensions
)
load_dotenv()
EMBED_URL: str = str(os.environ["EMBED_URL"]) 

# data must be a string (a fact or something) 
def insert_data(text: str, subject: str):
    vec = embed_one(text, prefix="search_document")
    entry = {
        "id": time.time_ns(),       # unique int64; or create the collection with auto_id=True and drop this
        "vector": vec,
        "text": text,
        "subject": subject,
    }
    res = client.insert(collection_name=DB_MEM_NAME, data=[entry])
    print("MEM: INSERT:", {**entry, "vector": f"<{len(vec)} floats>"})
    return res    # e.g. {"insert_count": 1, "ids": [...]}

def embed_one(text: str,prefix: str) -> list[float]:
    r = requests.post(
        f"{EMBED_URL}/embedding",
        json={"content": prefix + text, "embd_normalize": 2},
    )
    r.raise_for_status()
    body = r.json()

    emb = body[0]["embedding"] if isinstance(body, list) else body["embedding"]

    while emb and isinstance(emb[0], list):
        emb = emb[0]

    if len(emb) != 768:
        raise ValueError(f"expected 768 dims, got {len(emb)}")
    return emb

def search(query: str, limit: int = 3) -> list[dict]:
    qvec = embed_one(query, prefix="search_query: ")   # text -> 768 floats

    res = client.search(
        collection_name=DB_MEM_NAME,
        data=[qvec],                        # list of vectors, even for a single query
        limit=limit,                        # singular
        output_fields=["text", "subject"],
    )

    hits = [
        {
            "text": h["entity"]["text"],
            "subject": h["entity"]["subject"],
            "score": round(h["distance"], 3),
        }
        for h in res[0]                     # res[0] = hits for the first (only) query
    ]
    print("MEM: SEARCH:", query, "->", hits)
    return hits