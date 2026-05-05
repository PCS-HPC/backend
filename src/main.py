from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from api import api
from pymongo import MongoClient
from dotenv import load_dotenv
from argon2 import PasswordHasher
import os

@asynccontextmanager
async def lifespan(app: FastAPI):

	load_dotenv()
	app.mongo_client = MongoClient(os.getenv('MONGO_URI'))
	app.ph = PasswordHasher()

	yield

	await app.mongo_client.close()

origins = [
	"http://localhost:3000"
]

app = FastAPI(lifespan=lifespan)
app.add_middleware(
	CORSMiddleware,
	allow_origins=origins,
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"]
)
app.include_router(api.router, prefix='/api')