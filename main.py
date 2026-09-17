import os
import io
import json
import requests
from fastapi import FastAPI
from dotenv import load_dotenv
from google import genai
from PIL import Image

load_dotenv()

app = FastAPI()
SERPER_API_KEY = os.getenv("SERPER_API_KEY")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

client = genai.Client(api_key=GEMINI_API_KEY)


def search_university_images(university: str, category: str, num_results: int = 5):
    url = "https://google.serper.dev/images"
    query = f"{university} {category}"
    headers = {"X-API-KEY": SERPER_API_KEY, "Content-Type": "application/json"}
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


def verify_image(image_url: str, university: str, category: str):
    try:
        img_response = requests.get(image_url, timeout=8)
        img = Image.open(io.BytesIO(img_response.content))
    except Exception as e:
        return {"category": "other", "confidence": 0, "reason": f"failed to load image: {e}"}

    prompt = f"""You are verifying a photo for a university profile service.
University: {university}
Expected category: {category} (campus / dormitory / library / classroom / city)

Look at the image and assess:
1. category - most likely category (campus, dormitory, library, classroom, city, other)
2. confidence - number from 0 to 100, how plausible it is that this photo really shows this university and category
3. reason - one short sentence why

Answer STRICTLY in JSON format, no extra text, no markdown:
{{"category": "...", "confidence": 0, "reason": "..."}}"""

    try:
        result = client.models.generate_content(
            model="gemini-3.6-flash",
            contents=[prompt, img]
        )
        text = result.text.strip()
        text = text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)
    except Exception as e:
        return {"category": "other", "confidence": 0, "reason": f"verification error: {e}"}


@app.get("/profile")
def get_profile(university: str):
    categories = ["campus", "dormitory", "library", "classroom"]
    result = {}

    for category in categories:
        images = search_university_images(university, category)
        verified_images = []
        for img in images[:3]:
            verification = verify_image(img["url"], university, category)
            img["verification"] = verification
            verified_images.append(img)
        result[category] = verified_images

    return {"university": university, "categories": result}


@app.get("/")
def root():
    return {"message": "Server is running"}