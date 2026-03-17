from fastapi import FastAPI, HTTPException
import requests

app = FastAPI()

@app.get("/")
def slash():
    return { "Hello": "World" }

@app.get("/joke")
def get_jokes():
    response = requests.get("https://official-joke-api.appspot.com/random_joke")
    if (response.status_code == 200):
        data = response.json()
        return data
    else:
        raise HTTPException(500, "No jokes for you right now, come back later")
