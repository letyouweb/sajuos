# backend/main.py (일부)
from fastapi import FastAPI
import os
from services.rulecards_store import RuleCardStore

app = FastAPI()
RULESTORE: RuleCardStore | None = None

@app.on_event("startup")
def startup():
    global RULESTORE
    path = os.getenv("SAJUOS_RULECARDS_PATH", "backend/data/sajuos_master_db.jsonl")
    store = RuleCardStore(path)
    store.load()
    RULESTORE = store
    print(f"[RuleCards] loaded: {len(store.cards)}")
