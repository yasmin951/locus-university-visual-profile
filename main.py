import os
import requests
from fastapi import FastAPI
from dotenv import load_dotenv

load_dotenv()

app = FastAPI()
SERPER_API_KEY = os.getenv("SERPER_API_KEY")
print("КЛЮЧ:", SERPER_API_KEY)


def search_university_images(university: str, category: str, num_results: int = 5):
    url = "https://google.serper.dev/images"
    query = f"{university} {category}"
    headers = {
        "X-API-KEY": SERPER_API_KEY,
        "Content-Type": "application/json"
    }
    payload = {"q": query, "num": num_results}

    response = requests.post(url, headers=headers, json=payload)
    response.raise_for_status()
    data = response.json()

    images = []
    for item in data.get("images", []):
        images.append({
            "url": item.get("imageUrl"),
            "source": item.get("link"),
            "title": item.get("title"),
        })
    return images


@app.get("/profile")
def get_profile(university: str):
    categories = ["campus", "dormitory", "library", "classroom"]
    result = {}

    for category in categories:
        result[category] = search_university_images(university, category)

    return {
        "university": university,
        "categories": result
    }


@app.get("/")
def root():
    return {"message": "Сервер работает"}