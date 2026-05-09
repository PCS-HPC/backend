import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv

load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient
from argon2 import PasswordHasher

from src.api import api


@asynccontextmanager
async def lifespan(app: FastAPI):
    mongo_uri = os.getenv("MONGO_URI")
    mongo_db_name = os.getenv("MONGO_DB_NAME", "monhpc")

    if not mongo_uri:
        raise RuntimeError("MONGO_URI not found. Check your .env file.")

    app.mongo_client = MongoClient(mongo_uri)
    app.db = app.mongo_client[mongo_db_name]
    app.ph = PasswordHasher()

    app.db.command("ping")

    app.db["users"].create_index("email", unique=True)

    app.db["blacklisted_tokens"].create_index(
        [("expiresAt", 1)],
        expireAfterSeconds=0
    )

    app.db["sessions"].create_index("jti", unique=True)

    app.db["sessions"].create_index(
        [("expiresAt", 1)],
        expireAfterSeconds=0
    )

    print("MongoDB connected successfully")

    yield

    app.mongo_client.close()


origins = [
    "http://localhost:3000",
    "http://127.0.0.1:3000"
]

app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api.router, prefix="/api")


@app.get("/")
def root():
    return {"message": "MONHPC backend running"}


@app.get("/db-test")
def db_test():
    app.db.command("ping")
    return {"message": "MongoDB Atlas connected successfully"}