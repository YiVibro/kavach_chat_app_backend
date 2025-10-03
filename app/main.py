from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, JSONResponse
from typing import List, Dict
import json
import uuid
from datetime import datetime
import logging
import os

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

# CORS middleware - configure for Railway
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify your frontend URLs
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
        logger.info(f"User {user_id} connected to room {room_id}")

    def disconnect(self, user_id: str):
        if user_id in self.active_connections:
            del self.active_connections[user_id]
        if user_id in self.user_rooms:
            del self.user_rooms[user_id]
        logger.info(f"User {user_id} disconnected")

    async def send_personal_message(self, message: str, user_id: str):
        if user_id in self.active_connections:
            await self.active_connections[user_id].send_text(message)

    async def broadcast_to_room(self, message: str, room_id: str, exclude_user: str = None):
        disconnected_users = []
        for user_id, websocket in self.active_connections.items():
            if self.user_rooms.get(user_id) == room_id and user_id != exclude_user:
                try:
                    await websocket.send_text(message)
                except Exception as e:
                    logger.error(f"Error sending to {user_id}: {e}")
                    disconnected_users.append(user_id)
        
        # Clean up disconnected users
        for user_id in disconnected_users:
            self.disconnect(user_id)

manager = ConnectionManager()

# HTML test page for WebSocket with dynamic URL
html_template = """
<!DOCTYPE html>
<html>
<head>
    <title>Chat Test</title>
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
        .container { max-width: 800px; margin: 0 auto; background: white; padding: 20px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1); }
        .input-group { margin: 15px 0; }
        input, button { padding: 10px; margin: 5px; border: 1px solid #ddd; border-radius: 5px; }
        input { width: 200px; }
        button { background: #007bff; color: white; border: none; cursor: pointer; }
        button:hover { background: #0056b3; }
        button:disabled { background: #6c757d; cursor: not-allowed; }
        #messages { border: 1px solid #ccc; padding: 15px; height: 400px; overflow-y: scroll; margin: 15px 0; background: #fafafa; }
        .message { margin: 8px 0; padding: 8px; background: white; border-radius: 5px; border-left: 4px solid #007bff; }
        .system-message { border-left-color: #28a745; background: #f8fff9; }
        .user-message { border-left-color: #007bff; }
        .error-message { border-left-color: #dc3545; background: #fff5f5; }
        .status { padding: 10px; margin: 10px 0; border-radius: 5px; text-align: center; font-weight: bold; }
        .connected { background: #d4edda; color: #155724; border: 1px solid #c3e6cb; }
        .disconnected { background: #f8d7da; color: #721c24; border: 1px solid #f5c6cb; }
        .connecting { background: #fff3cd; color: #856404; border: 1px solid #ffeaa7; }
        .server-info { background: #e2e3e5; color: #383d41; padding: 10px; border-radius: 5px; margin: 10px 0; }
    </style>
</head>
<body>
    <div class="container">
        <h1>🚀 WebSocket Chat Test</h1>
        
        <div class="server-info">
            <strong>Server URL:</strong> <span id="serverUrl">Loading...</span>
        </div>
        
        <div class="input-group">
            <input type="text" id="userInput" placeholder="User ID" value="user_${Date.now().toString().slice(-4)}">
            <input type="text" id="roomInput" placeholder="Room ID" value="general">
            <button id="connectBtn" onclick="connect()">Connect</button>
            <button id="disconnectBtn" onclick="disconnect()" disabled>Disconnect</button>
        </div>
        
        <div id="status" class="status disconnected">Disconnected</div>
        
        <div class="input-group">
            <input type="text" id="messageInput" placeholder="Type your message here..." style="width: 400px;" disabled>
            <button onclick="sendMessage()" disabled id="sendBtn">Send Message</button>
        </div>
        
        <div id="messages"></div>
        
        <div style="margin-top: 20px; font-size: 12px; color: #666;">
            <strong>Instructions:</strong>
            <ol>
                <li>Click "Connect" to join the chat</li>
                <li>Type a message and click "Send"</li>
                <li>Open another browser tab to test multi-user chat</li>
            </ol>
        </div>
    </div>

    <script>
        var ws = null;
        var serverUrl = '';
        
        // Detect server URL
        function detectServerUrl() {
            const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
            const host = window.location.host;
            serverUrl = `${protocol}//${host}`;
            document.getElementById('serverUrl').textContent = serverUrl;
            return serverUrl;
        }
        
        function updateStatus(message, type) {
            const status = document.getElementById('status');
            status.textContent = message;
            status.className = `status ${type}`;
        }
        
        function updateUI(connected) {
            document.getElementById('connectBtn').disabled = connected;
            document.getElementById('disconnectBtn').disabled = !connected;
            document.getElementById('messageInput').disabled = !connected;
            document.getElementById('sendBtn').disabled = !connected;
        }
        
        function connect() {
            const userId = document.getElementById('userInput').value.trim();
            const roomId = document.getElementById('roomInput').value.trim();
            
            if (!userId || !roomId) {
                alert('Please enter both User ID and Room ID');
                return;
            }
            
            const baseUrl = detectServerUrl();
            const wsUrl = `${baseUrl}/ws/${encodeURIComponent(userId)}/${encodeURIComponent(roomId)}`;
            
            updateStatus('Connecting to server...', 'connecting');
            updateUI(false);
            
            console.log('Connecting to:', wsUrl);
            
            try {
                ws = new WebSocket(wsUrl);
                
                ws.onopen = function(event) {
                    console.log('WebSocket connected successfully');
                    updateStatus(`Connected as ${userId} in room ${roomId}`, 'connected');
                    updateUI(true);
                    addMessage('System: Connected to server successfully!', 'system-message');
                };
                
                ws.onmessage = function(event) {
                    console.log('Message received:', event.data);
                    try {
                        const data = JSON.parse(event.data);
                        let messageText = '';
                        let messageClass = 'system-message';
                        
                        if (data.type === 'message') {
                            messageText = `💬 ${data.user_id}: ${data.content}`;
                            messageClass = 'user-message';
                        } else if (data.type === 'user_joined') {
                            messageText = `✅ ${data.user_id} joined the room`;
                        } else if (data.type === 'user_left') {
                            messageText = `❌ ${data.user_id} left the room`;
                        } else {
                            messageText = `ℹ️ ${JSON.stringify(data)}`;
                        }
                        
                        addMessage(messageText, messageClass);
                    } catch (e) {
                        console.error('Error parsing message:', e);
                        addMessage(`📨 Raw: ${event.data}`, 'system-message');
                    }
                };
                
                ws.onclose = function(event) {
                    console.log('WebSocket closed:', event.code, event.reason);
                    updateStatus('Disconnected from server', 'disconnected');
                    updateUI(false);
                    addMessage('System: Disconnected from server', 'system-message');
                };
                
                ws.onerror = function(event) {
                    console.error('WebSocket error:', event);
                    updateStatus('Connection error - check console', 'disconnected');
                    updateUI(false);
                    addMessage('System: WebSocket connection error occurred', 'error-message');
                };
                
            } catch (error) {
                console.error('Connection error:', error);
                updateStatus(`Connection failed: ${error.message}`, 'disconnected');
                updateUI(false);
                addMessage(`System: Connection error: ${error.message}`, 'error-message');
            }
        }
        
        function disconnect() {
            if (ws) {
                ws.close(1000, 'User disconnected');
                ws = null;
            }
            updateStatus('Disconnected', 'disconnected');
            updateUI(false);
        }
        
        function sendMessage() {
            if (ws && ws.readyState === WebSocket.OPEN) {
                const messageInput = document.getElementById('messageInput');
                const message = messageInput.value.trim();
                
                if (message) {
                    const messageData = {
                        type: "message",
                        content: message
                    };
                    
                    console.log('Sending message:', messageData);
                    ws.send(JSON.stringify(messageData));
                    messageInput.value = '';
                }
            } else {
                alert('Not connected to server. Please connect first.');
            }
        }
        
        function addMessage(message, className = 'message') {
            const messages = document.getElementById('messages');
            const messageElement = document.createElement('div');
            messageElement.className = className;
            messageElement.textContent = message;
            messages.appendChild(messageElement);
            messages.scrollTop = messages.scrollHeight;
        }
        
        // Allow sending message with Enter key
        document.getElementById('messageInput').addEventListener('keypress', function(e) {
            if (e.key === 'Enter') {
                sendMessage();
            }
        });
        
        // Initialize
        detectServerUrl();
        addMessage('System: Ready to connect. Enter your User ID and Room ID, then click Connect.', 'system-message');
    </script>
</body>
</html>
"""

@app.get("/")
async def get():
    return HTMLResponse(html_template)

@app.get("/health")
async def health_check():
    return JSONResponse({
        "status": "healthy", 
        "message": "Server is running",
        "websocket_support": True,
        "active_connections": len(manager.active_connections),
        "environment": os.getenv("RAILWAY_ENVIRONMENT", "development")
    })

@app.get("/stats")
async def get_stats():
    return JSONResponse({
        "active_connections": len(manager.active_connections),
        "active_rooms": len(set(manager.user_rooms.values())),
        "users": list(manager.user_rooms.keys()),
        "rooms": list(set(manager.user_rooms.values()))
    })

@app.websocket("/ws/{user_id}/{room_id}")
async def websocket_endpoint(websocket: WebSocket, user_id: str, room_id: str):
    logger.info(f"WebSocket connection attempt: user={user_id}, room={room_id}")
    
    try:
        await manager.connect(websocket, user_id, room_id)
        
        # Notify others that user joined
        join_message = {
            "type": "user_joined",
            "user_id": user_id,
            "room_id": room_id,
            "timestamp": datetime.now().isoformat()
        }
        await manager.broadcast_to_room(json.dumps(join_message), room_id, exclude_user=user_id)
        
        # Listen for messages
        while True:
            try:
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
                    logger.info(f"Message from {user_id} in {room_id}: {message_data['content']}")
                    
                    # Broadcast to all in room except sender
                    await manager.broadcast_to_room(json.dumps(chat_message), room_id, exclude_user=user_id)
                    
            except WebSocketDisconnect:
                break
            except Exception as e:
                logger.error(f"Error processing message: {e}")
                break
                
    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected: user={user_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {e}")
    finally:
        manager.disconnect(user_id)
        # Notify others that user left
        leave_message = {
            "type": "user_left",
            "user_id": user_id,
            "room_id": room_id,
            "timestamp": datetime.now().isoformat()
        }
        await manager.broadcast_to_room(json.dumps(leave_message), room_id)

# Railway needs to know which port to use
port = int(os.getenv("PORT", 8000))

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app, 
        host="0.0.0.0", 
        port=port, 
        reload=False  # Disable reload in production
    )