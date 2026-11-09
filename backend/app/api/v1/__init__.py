from fastapi import APIRouter

from app.api.v1 import chat, conversations, documents, system, workspaces

api_router = APIRouter()
api_router.include_router(system.router)
api_router.include_router(workspaces.router)
api_router.include_router(documents.router)
api_router.include_router(conversations.router)
api_router.include_router(chat.router)
