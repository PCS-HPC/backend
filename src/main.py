import os
from contextlib import asynccontextmanager

from dotenv import load_dotenv

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient
from argon2 import PasswordHasher

from src.api import api
from src.service import ldap
from src.utils import PrometheusMiddleware, metrics, setting_otlp

import logging
from opentelemetry.instrumentation.logging import LoggingInstrumentor

load_dotenv()
LDAP_ACTIVATED = os.getenv("LDAP_ACTIVATED") == 'true'
APP_NAME = os.getenv("APP_NAME")
OTLP_ENDPOINT = os.getenv("OTLP_ENDPOINT", "http://localhost:4317")

LoggingInstrumentor().instrument(set_logging_format=True)
logging.getLogger(__name__).info("Logging is working")
logging.getLogger("uvicorn.access").setLevel(logging.INFO)
logging.getLogger("uvicorn.error").setLevel(logging.INFO)

@asynccontextmanager
async def lifespan(app: FastAPI):
    mongo_uri = os.getenv("MONGO_URI")
    mongo_db_name = os.getenv("MONGO_DB_NAME", "monhpc")

    if not mongo_uri:
        raise RuntimeError("MONGO_URI not found. Check your .env file.")

    app.mongo_client = MongoClient(mongo_uri)
    app.db = app.mongo_client[mongo_db_name]
    if LDAP_ACTIVATED:
        app.ldap = ldap.get_ldap_connection()
    app.ph = PasswordHasher()

    app.db.command("ping")

    app.db["users"].create_index("email", unique=True)
    app.db["users"].create_index("username", unique=True)

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
    if LDAP_ACTIVATED:
        app.ldap.unbind()


origins = ['*'] # fuck you
app = FastAPI(lifespan=lifespan)

# Observability
app.add_middleware(PrometheusMiddleware, app_name=APP_NAME)
app.add_route("/metrics", metrics)
setting_otlp(app, APP_NAME, OTLP_ENDPOINT)

app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)

app.include_router(api.router, prefix="/api")
