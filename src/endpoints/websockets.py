import json
import logging
from typing import Dict, Set
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from jose import jwt, JWTError
import os
from pathlib import Path
from dotenv import load_dotenv

logger = logging.getLogger("Yana_WebSockets")
router = APIRouter()

# Load env variables for JWT decoding
BASE_DIR = Path(__file__).resolve().parent.parent.parent
load_dotenv(dotenv_path=BASE_DIR / ".env")
SECRET_KEY = os.getenv("SECRET_KEY")
if not SECRET_KEY or SECRET_KEY == "yana-super-secret-key-change-this-in-production":
    # Transient fallback if key is not generated/written yet (should match auth.py fallback behavior)
    import secrets
    SECRET_KEY = os.getenv("SECRET_KEY", secrets.token_hex(32))

ALGORITHM = "HS256"

class ConnectionManager:
    def __init__(self):
        # Map user_id (str) to a set of active WebSockets
        self.active_connections: Dict[str, Set[WebSocket]] = {}

    async def connect(self, websocket: WebSocket, user_id: str):
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = set()
        self.active_connections[user_id].add(websocket)
        logger.info(f"User {user_id} connected. Total active users: {len(self.active_connections)}")

    def disconnect(self, websocket: WebSocket, user_id: str):
        if user_id in self.active_connections:
            if websocket in self.active_connections[user_id]:
                self.active_connections[user_id].remove(websocket)
            if not self.active_connections[user_id]:
                del self.active_connections[user_id]
        logger.info(f"User {user_id} disconnected. Total active users: {len(self.active_connections)}")

    def is_user_connected(self, user_id: str) -> bool:
        return user_id in self.active_connections and len(self.active_connections[user_id]) > 0

    async def broadcast(self, message: dict):
        if not self.active_connections:
            return
        
        message_str = json.dumps(message)
        for user_id, sockets in list(self.active_connections.items()):
            disconnected = []
            for connection in list(sockets):
                try:
                    await connection.send_text(message_str)
                except Exception as e:
                    logger.error(f"Error sending message to user {user_id}: {str(e)}")
                    disconnected.append(connection)
                    
            for connection in disconnected:
                self.disconnect(connection, user_id)

manager = ConnectionManager()

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: str | None = Query(None)):
    # Authenticate socket connection
    if not token:
        logger.warning("WebSocket connection rejected: No token provided.")
        await websocket.close(code=1008) # Policy Violation
        return

    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = payload.get("id")
        if not user_id:
            logger.warning("WebSocket connection rejected: Invalid token payload.")
            await websocket.close(code=1008)
            return
    except JWTError as e:
        logger.warning(f"WebSocket connection rejected: Token validation failed: {str(e)}")
        await websocket.close(code=1008)
        return

    await manager.connect(websocket, user_id)
    try:
        while True:
            # Keep alive and receive messages
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(websocket, user_id)
    except Exception as e:
        logger.error(f"WebSocket connection error for user {user_id}: {str(e)}")
        manager.disconnect(websocket, user_id)
