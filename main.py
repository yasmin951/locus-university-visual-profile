from fastapi import FastAPI

app = FastAPI()

@app.get("/profile")
def get_profile(university: str):
    return {
        "university": university,
        "status": "placeholder — здесь будет реальный поиск фото",
        "photos": []
    }

@app.get("/")
def root():
    return {"message": "Сервер работает"}