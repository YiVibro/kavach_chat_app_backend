from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from typing import List, Dict
import json
import uuid
from datetime import datetime

app = FastAPI()

# CORS middleware to allow mobile app connections
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

manager = ConnectionManager()

# HTML test page for WebSocket
html = """
<!DOCTYPE html>
<html>
<head>
    <title>Chat Test</title>
</head>
<body>
    <h1>WebSocket Chat Test</h1>
    <div>
        <input type="text" id="userInput" placeholder="User ID" value="test_user">
        <input type="text" id="roomInput" placeholder="Room ID" value="room1">
        <button onclick="connect()">Connect</button>
        <button onclick="disconnect()">Disconnect</button>
    </div>
    <div>
        <input type="text" id="messageInput" placeholder="Type message">
        <button onclick="sendMessage()">Send</button>
    </div>
    <div id="messages"></div>
    <script>
        var ws = null;
        
        function connect() {
            const userId = document.getElementById('userInput').value;
            const roomId = document.getElementById('roomInput').value;
            
            ws = new WebSocket(`ws://localhost:8000/ws/${userId}/${roomId}`);
            
            ws.onopen = function(event) {
                addMessage('Connected to server');
            };
            
            ws.onmessage = function(event) {
                const data = JSON.parse(event.data);
                addMessage(`Received: ${JSON.stringify(data)}`);
            };
            
            ws.onclose = function(event) {
                addMessage('Disconnected from server');
            };
            
            ws.onerror = function(event) {
                addMessage('WebSocket error: ' + event);
            };
        }
        
        function disconnect() {
            if (ws) {
                ws.close();
                ws = null;
            }
        }
        
        function sendMessage() {
            if (ws && ws.readyState === WebSocket.OPEN) {
                const messageInput = document.getElementById('messageInput');
                const message = {
                    type: "message",
                    content: messageInput.value
                };
                ws.send(JSON.stringify(message));
                messageInput.value = '';
            }
        }
        
        function addMessage(message) {
            const messages = document.getElementById('messages');
            const messageElement = document.createElement('div');
            messageElement.textContent = message;
            messages.appendChild(messageElement);
        }
    </script>
</body>
</html>
"""

@app.get("/")
async def get():
    return HTMLResponse(html)

@app.get("/health")
async def health_check():
    return {"status": "healthy", "message": "Server is running"}

@app.get("/stats")
async def get_stats():
    return {
        "active_connections": len(manager.active_connections),
        "active_rooms": len(set(manager.user_rooms.values())),
        "users": list(manager.user_rooms.keys())
    }

@app.websocket("/ws/{user_id}/{room_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str, room_id: str):
    await manager.connect(websocket, user_id, room_id)
    try:
        # Notify others that user joined
        join_message = {
            "type": "user_joined",
            "user_id": user_id,
            "room_id": room_id,
            "timestamp": datetime.now().isoformat()
        }
        await manager.broadcast_to_room(json.dumps(join_message), room_id, exclude_user=user_id)
        
        while True:
            data = await websocket.receive_text()
            message_data = json.loads(data)
            
            if message_data["type"] == "message":
                chat_message = {
                    "type": "message",
                    "message_id": str(uuid.uuid4()),
                    "user_id": user_id,
                    "room_id": room_id,
                    "content": message_data["content"],
                    "timestamp": datetime.now().isoformat()
                }
                # Broadcast to all in room except sender
                await manager.broadcast_to_room(json.dumps(chat_message), room_id, exclude_user=user_id)
                
    except WebSocketDisconnect:
        manager.disconnect(user_id)
        # Notify others that user left
        leave_message = {
            "type": "user_left",
            "user_id": user_id,
            "room_id": room_id,
            "timestamp": datetime.now().isoformat()
        }
        await manager.broadcast_to_room(json.dumps(leave_message), room_id)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)