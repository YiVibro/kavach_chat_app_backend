from fastapi import WebSocket,WebSocketDisconnect
from fastapi import HTMLResponse
from typing import List,Dict
import json
import uuid 
from datetime import datetime

class ConnectionManager:
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
        self.user_rooms: Dict[str, str] = {}  # user_id -> room_id

    async def connect(self, websocket: WebSocket, user_id: str, room_id: str):
        await websocket.accept()
        self.active_connections[user_id] = websocket
        self.user_rooms[user_id] = room_id

    def disconnect(self, user_id: str):
        if user_id in self.active_connections:
            del self.active_connections[user_id]
        if user_id in self.user_rooms:
            del self.user_rooms[user_id]

    async def send_personal_message(self, message: str, user_id: str):
        if user_id in self.active_connections:
            await self.active_connections[user_id].send_text(message)

    async def broadcast_to_room(self, message: str, room_id: str, exclude_user: str = None):
        disconnected_users = []
        for user_id, websocket in self.active_connections.items():
            if self.user_rooms.get(user_id) == room_id and user_id != exclude_user:
                try:
                    await websocket.send_text(message)
                except:
                    disconnected_users.append(user_id)
        
        # Clean up disconnected users
        for user_id in disconnected_users:
            self.disconnect(user_id)

#manager = ConnectionManager()
