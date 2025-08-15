from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from src.live.model_server import app as model_app
from src.live.advice_server import app as advice_app

app = FastAPI(title="Cortexa Unified API")

# CORS (gerekirse domainlerini kısıtla)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Alt uygulamalar
app.mount("/model", model_app)
app.mount("/advice", advice_app)
