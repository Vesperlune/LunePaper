"""FastAPI application entry point."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from backend.routes import router as api_router
from backend.ws import router as ws_router
from config import get

app = FastAPI(title="Paper Translator API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[get('server', 'cors_origin', default='http://localhost:5173')],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)
app.include_router(ws_router)


@app.get("/")
async def root():
    return {"service": "Paper Translator API", "status": "running"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("backend.main:app",
                host=get('server', 'host', default='0.0.0.0'),
                port=get('server', 'port', default=7860),
                reload=False)
