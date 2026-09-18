import os
import io
import json
import time
import requests
from fastapi import FastAPI
from dotenv import load_dotenv
from google import genai
from PIL import Image
import imagehash
from concurrent.futures import ThreadPoolExecutor, as_completed

load_dotenv()

app = FastAPI()
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)
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
            "category": category,
        })
    return images


def verify_image(img_data: dict, university: str):
    image_url = img_data["url"]
    category = img_data["category"]

    try:
        headers = {"User-Agent": "Mozilla/5.0"}
        img_response = requests.get(image_url, timeout=8, headers=headers)
        content_type = img_response.headers.get("Content-Type", "")
        if "image" not in content_type:
            img_data["verification"] = {"category": "other", "confidence": 0, "reason": "URL does not point to a valid image"}
            return img_data
        img = Image.open(io.BytesIO(img_response.content))
        img.load()
        img.thumbnail((300, 300))
        img_data["phash"] = str(imagehash.phash(img))
    except Exception as e:
        img_data["verification"] = {"category": "other", "confidence": 0, "reason": f"failed to load image: {e}"}
        img.close()
        del img
        return img_data

    prompt = f"""You are verifying a photo for a university profile service.
University: {university}
Expected category: {category} (campus / dormitory / library / classroom / city)

Look at the image and assess:
1. category - most likely category (campus, dormitory, library, classroom, city, other)
2. confidence - number from 0 to 100, how plausible it is that this photo really shows this university and category
3. reason - one short sentence why

Answer STRICTLY in JSON format, no extra text, no markdown:
{{"category": "...", "confidence": 0, "reason": "..."}}"""

    for attempt in range(3):
        try:
            result = client.models.generate_content(
                model="gemini-flash-lite-latest",
                contents=[prompt, img]
            )
            text = result.text.strip().replace("```json", "").replace("```", "").strip()
            img_data["verification"] = json.loads(text)
            break
        except Exception as e:
            if "RESOURCE_EXHAUSTED" in str(e) and attempt < 2:
                time.sleep(5)
                continue
            img_data["verification"] = {"category": "other", "confidence": 0, "reason": f"verification error: {e}"}
            break
    
    return img_data

def remove_duplicates(images: list, threshold: int = 5):
    """Убирает визуально похожие фото, оставляя первое из каждой группы."""
    unique = []
    seen_hashes = []

    for img in images:
        phash_str = img.get("phash")
        if not phash_str:
            unique.append(img)
            continue

        current_hash = imagehash.hex_to_hash(phash_str)
        is_duplicate = False

        for seen in seen_hashes:
            if current_hash - seen <= threshold:
                is_duplicate = True
                break

        if not is_duplicate:
            seen_hashes.append(current_hash)
            unique.append(img)

    return unique

def generate_summary(university: str):
    prompt = f"Напиши краткое, объективное описание кампуса и студенческой жизни университета {university} в 2-3 предложениях, на основе общеизвестной информации. Без вымышленных фактов, только то, что широко известно."
    try:
        result = client.models.generate_content(
            model="gemini-flash-lite-latest",
            contents=[prompt]
        )
        return result.text.strip()
    except Exception:
        return "Описание временно недоступно."


@app.get("/profile")
def get_profile(university: str):
    start_time = time.time()
    categories = ["campus", "dormitory", "library", "classroom", "city"]


    # 1. Поиск фото по всем категориям параллельно
    all_images = []
    with ThreadPoolExecutor(max_workers=4) as executor:
        futures = [executor.submit(search_university_images, university, cat) for cat in categories]
        for future in as_completed(futures):
            all_images.extend(future.result()[:3])  # берём по 3 фото на категорию

        # 2. Проверка фото по очереди (экономим память)
    verified = []
    for img in all_images:
        verified.append(verify_image(img, university))

    # 3. Убираем дубли
    verified = remove_duplicates(verified)

    # 4. Раскладываем обратно по категориям
    result = {cat: [] for cat in categories}
    for img in verified:
        result[img["category"]].append(img)

    elapsed = round(time.time() - start_time, 2)
    summary = generate_summary(university)

    return {
        "university": university,
        "summary": summary,
        "search_time_seconds": elapsed,
        "categories": result
    }


from fastapi.responses import FileResponse

@app.get("/")
def root():
    return FileResponse("index.html")