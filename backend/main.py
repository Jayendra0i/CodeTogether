
import asyncio
import json
import secrets
import string
import os
from backend.ai_assistant import router as ai_router

from typing import Dict, Optional

from fastapi import (
    FastAPI,
    HTTPException,
    WebSocket,
    WebSocketDisconnect,
    Depends,
    Request,
)
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, EmailStr, Field
from datetime import datetime, timedelta, timezone
from sqlalchemy import text
from jose import jwt, JWTError

from backend.database import engine, Base, test_connection
from backend import models
from backend.models import User, Room, CodeFile, ChatMessage
from backend.executor import execute_code

from backend.auth import (
    router as auth_router,
    get_current_user,
    SECRET_KEY,
    ALGORITHM,
    SessionLocal,
)


app = FastAPI(
    title="Collaborative Code Editor",
    description="Real-time collaborative coding platform",
    version="2.1.0",
)


# ==================================================
# CORS
# ==================================================

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "https://codetogether-frontend-jagd.onrender.com",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ==================================================
# AUTHENTICATION ROUTER
# ==================================================
app.include_router(ai_router)
app.include_router(auth_router)


@app.middleware("http")
async def enforce_guest_room_scope(request: Request, call_next):
    authorization = request.headers.get("authorization", "")
    token = authorization.removeprefix("Bearer ")
    try:
        claims = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM]) if token else {}
    except JWTError:
        claims = {}
    if claims.get("guest"):
        if request.url.path == "/ai/assistant" and request.method == "POST":
            return await call_next(request)
        allowed_room = str(claims.get("room_code", "")).upper()
        parts = request.url.path.strip("/").split("/")
        requested_room = None
        if parts and parts[0] in {"rooms", "chat", "get-code"} and len(parts) > 1:
            requested_room = parts[1]
        elif request.url.path == "/join-room":
            requested_room = request.query_params.get("room_code")
        elif request.url.path in {"/execute", "/save-code"}:
            # These handlers validate their room after parsing the request body.
            return await call_next(request)
        elif parts and parts[0] == "files" and len(parts) > 1:
            db = SessionLocal()
            try:
                file = db.query(CodeFile).filter(CodeFile.id == parts[1]).first()
                room = db.query(Room).filter(Room.id == file.room_id).first() if file else None
                requested_room = room.room_code if room else None
            finally:
                db.close()
        if not requested_room or str(requested_room).upper() != allowed_room:
            return JSONResponse(status_code=403, content={"detail": "Guest access is limited to the invited room"})
    return await call_next(request)


# ==================================================
# REQUEST MODELS
# ==================================================

class RoomCreate(BaseModel):
    username: Optional[str] = "Guest"


class GuestJoin(BaseModel):
    invite_token: str = Field(min_length=20, max_length=2048)
    name: str = Field(min_length=2, max_length=100)
    email: EmailStr


class CodeSave(BaseModel):
    room_code: str
    filename: str
    language: str = "python"
    content: str


class FileCreate(BaseModel):
    filename: str
    language: str = "python"
    content: str = ""


class FileUpdate(BaseModel):
    filename: Optional[str] = None
    language: Optional[str] = None
    content: Optional[str] = None


class ChatMessageCreate(BaseModel):
    username: Optional[str] = None
    message: str


class CodeExecuteRequest(BaseModel):
    language: str
    code: str
    stdin: str = ""
    room_code: Optional[str] = None


# ==================================================
# WEBSOCKET CONNECTION MANAGER
# ==================================================

class ConnectionManager:

    def __init__(self):
        self.active_connections: Dict[
            str, Dict[WebSocket, str]
        ] = {}

    async def connect(
        self,
        websocket: WebSocket,
        room_code: str,
        username: str,
    ):

        await websocket.accept()

        if room_code not in self.active_connections:
            self.active_connections[room_code] = {}

        self.active_connections[room_code][websocket] = username

        await self.broadcast_participants(room_code)

    def disconnect(
        self,
        websocket: WebSocket,
        room_code: str,
    ):

        if room_code in self.active_connections:

            self.active_connections[room_code].pop(
                websocket,
                None
            )

            if not self.active_connections[room_code]:
                del self.active_connections[room_code]

    async def broadcast_participants(self, room_code: str):

        if room_code not in self.active_connections:
            return

        participants = list(
            self.active_connections[room_code].values()
        )

        await self.broadcast_room(
            room_code,
            {
                "type": "participants",
                "participants": participants,
            },
        )

    async def broadcast(
        self,
        message: dict,
        room_code: str,
        sender: WebSocket,
    ):

        if room_code not in self.active_connections:
            return

        for connection in list(
            self.active_connections[room_code].keys()
        ):

            if connection != sender:

                try:
                    await connection.send_json(message)

                except Exception:
                    self.disconnect(connection, room_code)

    async def broadcast_room(
        self,
        room_code: str,
        message: dict,
    ):

        if room_code not in self.active_connections:
            return

        for connection in list(
            self.active_connections[room_code].keys()
        ):

            try:
                await connection.send_json(message)

            except Exception:
                self.disconnect(connection, room_code)


manager = ConnectionManager()


# ==================================================
# DATABASE STARTUP
# ==================================================

@app.on_event("startup")
def startup():

    test_connection()

    Base.metadata.create_all(bind=engine)

    print("CodeTogether backend started successfully!")


# ==================================================
# HELPER FUNCTIONS
# ==================================================

def serialize_file(file):

    return {
        "id": file.id,
        "filename": file.filename,
        "language": file.language,
        "content": file.content or "",
    }


def serialize_chat(message):

    return {
        "id": message.id,
        "username": message.username,
        "message": message.message,
        "created_at": (
            message.created_at.isoformat()
            if message.created_at
            else None
        ),
    }


def get_room(db, room_code: str):

    return (
        db.query(Room)
        .filter(Room.room_code == room_code.upper())
        .first()
    )


def create_invitation_token(room_code: str):
    return jwt.encode(
        {
            "invite": True,
            "room_code": room_code,
            "exp": datetime.now(timezone.utc) + timedelta(days=30),
        },
        SECRET_KEY,
        algorithm=ALGORITHM,
    )


def get_websocket_user(token: Optional[str]):

    if not token:
        return None

    db = SessionLocal()

    try:

        payload = jwt.decode(
            token,
            SECRET_KEY,
            algorithms=[ALGORITHM],
        )

        if payload.get("guest"):
            return type("Guest", (), {
                "username": payload.get("name", "Guest"),
                "email": payload.get("email", ""),
                "is_active": True,
                "room_code": payload.get("room_code", ""),
            })()

        user_id = payload.get("sub")

        if not user_id:
            return None

        try:
            user_id = int(user_id)
        except (ValueError, TypeError):
            return None

        user = (
            db.query(User)
            .filter(User.id == user_id)
            .first()
        )

        if not user or not user.is_active:
            return None

        return user

    except JWTError:
        return None

    finally:
        db.close()


# ==================================================
# BASIC ROUTES
# ==================================================

@app.get("/")
def home():

    return {
        "message": "Welcome to CodeTogether API",
        "status": "running",
        "version": "2.1.0",
    }


@app.get("/health")
def health():

    return {
        "status": "healthy",
    }


@app.get("/database-status")
def database_status():

    try:

        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))

        return {
            "status": "connected",
            "database": engine.url.database,
        }

    except Exception as error:

        print("Database status error:", repr(error))

        raise HTTPException(
            status_code=500,
            detail="Database connection failed",
        )


# ==================================================
# CREATE ROOM
# ==================================================

@app.post("/guest/join")
def guest_join(data: GuestJoin):
    db = SessionLocal()
    try:
        try:
            invitation = jwt.decode(data.invite_token, SECRET_KEY, algorithms=[ALGORITHM])
        except JWTError:
            raise HTTPException(status_code=404, detail="Invitation link is invalid or expired")
        if not invitation.get("invite") or not invitation.get("room_code"):
            raise HTTPException(status_code=404, detail="Invitation link is invalid or expired")
        room = get_room(db, invitation["room_code"])
        if not room:
            raise HTTPException(status_code=404, detail="Invitation link is invalid or expired")
        name = data.name.strip()
        if len(name) < 2:
            raise HTTPException(status_code=422, detail="Name must contain at least 2 characters")
        payload = {
            "sub": "guest",
            "guest": True,
            "name": name,
            "email": str(data.email).lower().strip(),
            "room_code": room.room_code,
            "exp": datetime.now(timezone.utc) + timedelta(days=7),
        }
        return {
            "access_token": jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM),
            "token_type": "bearer",
            "room_code": room.room_code,
            "user": {"name": name, "email": str(data.email).lower().strip()},
        }
    finally:
        db.close()


@app.get("/invite/{invite_token}")
def check_invite(invite_token: str):
    try:
        invitation = jwt.decode(invite_token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        raise HTTPException(status_code=404, detail="Invitation link is invalid or expired")
    if not invitation.get("invite") or not invitation.get("room_code"):
        raise HTTPException(status_code=404, detail="Invitation link is invalid or expired")
    db = SessionLocal()
    try:
        room = get_room(db, invitation["room_code"])
        if not room:
            raise HTTPException(status_code=404, detail="Invitation link is invalid or expired")
        return {"room_code": room.room_code, "valid": True}
    finally:
        db.close()

@app.post("/create-room")
def create_room(
    data: RoomCreate,
    current_user: User = Depends(get_current_user),
):

    db = SessionLocal()

    try:

        room_code = "".join(
            secrets.choice(
                string.ascii_uppercase + string.digits
            )
            for _ in range(8)
        )

        while get_room(db, room_code):

            room_code = "".join(
                secrets.choice(
                    string.ascii_uppercase + string.digits
                )
                for _ in range(8)
            )

        room = Room(room_code=room_code)

        db.add(room)
        db.commit()
        db.refresh(room)

        return {
            "success": True,
            "room_code": room.room_code,
            "room_id": room.room_code,
            "invitation_token": create_invitation_token(room.room_code),
            "username": current_user.username,
        }

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


# ==================================================
# JOIN ROOM
# ==================================================

@app.post("/join-room")
def join_room(
    room_code: str,
    current_user: User = Depends(get_current_user),
):

    db = SessionLocal()

    try:

        room = get_room(db, room_code)

        if not room:

            raise HTTPException(
                status_code=404,
                detail="Room not found",
            )

        if getattr(current_user, "guest", False) and room.room_code != current_user.room_code:
            raise HTTPException(status_code=403, detail="Guest access is limited to the invited room")

        return {
            "success": True,
            "message": "Joined room successfully",
            "room_code": room.room_code,
            "room_id": room.room_code,
            "invitation_token": create_invitation_token(room.room_code),
            "username": current_user.username,
        }

    finally:
        db.close()


# ==================================================
# CREATE FILE
# ==================================================

@app.post("/rooms/{room_code}/files")
async def create_file(
    room_code: str,
    data: FileCreate,
    current_user: User = Depends(get_current_user),
):

    filename = data.filename.strip()

    if not filename:
        raise HTTPException(
            status_code=400,
            detail="Filename cannot be empty",
        )

    db = SessionLocal()

    try:

        room = get_room(db, room_code)

        if not room:

            raise HTTPException(
                status_code=404,
                detail="Room not found",
            )

        if getattr(current_user, "guest", False) and room.room_code != current_user.room_code:
            raise HTTPException(status_code=403, detail="Guest access is limited to the invited room")

        existing_file = (
            db.query(CodeFile)
            .filter(
                CodeFile.room_id == room.id,
                CodeFile.filename == filename,
            )
            .first()
        )

        if existing_file:

            raise HTTPException(
                status_code=400,
                detail="File already exists",
            )

        new_file = CodeFile(
            filename=filename,
            language=data.language,
            content=data.content,
            room_id=room.id,
        )

        db.add(new_file)
        db.commit()
        db.refresh(new_file)

        file_data = serialize_file(new_file)

        await manager.broadcast_room(
            room.room_code,
            {
                "type": "file_created",
                "file": file_data,
            },
        )

        return {
            "success": True,
            "file": file_data,
            "file_id": file_data["id"],
            "filename": file_data["filename"],
            "language": file_data["language"],
            "content": file_data["content"],
        }

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


# ==================================================
# GET ALL FILES
# ==================================================

@app.get("/rooms/{room_code}/files")
def get_files(
    room_code: str,
    current_user: User = Depends(get_current_user),
):

    db = SessionLocal()

    try:

        room = get_room(db, room_code)

        if not room:

            raise HTTPException(
                status_code=404,
                detail="Room not found",
            )

        files = (
            db.query(CodeFile)
            .filter(CodeFile.room_id == room.id)
            .order_by(CodeFile.id.asc())
            .all()
        )

        file_list = [
            serialize_file(file)
            for file in files
        ]

        return {
            "files": file_list,
        }

    finally:
        db.close()


# ==================================================
# GET SINGLE FILE
# ==================================================

@app.get("/files/{file_id}")
def get_file(
    file_id: int,
    current_user: User = Depends(get_current_user),
):

    db = SessionLocal()

    try:

        file = (
            db.query(CodeFile)
            .filter(CodeFile.id == file_id)
            .first()
        )

        if not file:

            raise HTTPException(
                status_code=404,
                detail="File not found",
            )

        return serialize_file(file)

    finally:
        db.close()


# ==================================================
# UPDATE / RENAME FILE
# ==================================================

@app.put("/files/{file_id}")
async def update_file(
    file_id: int,
    data: FileUpdate,
    current_user: User = Depends(get_current_user),
):

    db = SessionLocal()

    try:

        file = (
            db.query(CodeFile)
            .filter(CodeFile.id == file_id)
            .first()
        )

        if not file:

            raise HTTPException(
                status_code=404,
                detail="File not found",
            )

        room = (
            db.query(Room)
            .filter(Room.id == file.room_id)
            .first()
        )

        if not room:

            raise HTTPException(
                status_code=404,
                detail="Room not found",
            )

        old_filename = file.filename

        update_data = data.model_dump(
            exclude_unset=True
        )

        if "filename" in update_data:

            if not update_data["filename"] or not update_data["filename"].strip():

                raise HTTPException(
                    status_code=400,
                    detail="Filename cannot be empty",
                )

            update_data["filename"] = update_data["filename"].strip()

            if update_data["filename"] != old_filename:

                duplicate = (
                    db.query(CodeFile)
                    .filter(
                        CodeFile.room_id == file.room_id,
                        CodeFile.filename == update_data["filename"],
                        CodeFile.id != file_id,
                    )
                    .first()
                )

                if duplicate:

                    raise HTTPException(
                        status_code=400,
                        detail="A file with this name already exists",
                    )

        for key, value in update_data.items():
            setattr(file, key, value)

        db.commit()
        db.refresh(file)

        file_data = serialize_file(file)

        if old_filename != file.filename:

            await manager.broadcast_room(
                room.room_code,
                {
                    "type": "file_renamed",
                    "file": file_data,
                    "file_id": file.id,
                    "filename": file.filename,
                    "old_filename": old_filename,
                },
            )

        return {
            "success": True,
            "file": file_data,
        }

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


# ==================================================
# DELETE FILE
# ==================================================

@app.delete("/files/{file_id}")
async def delete_file(
    file_id: int,
    current_user: User = Depends(get_current_user),
):

    db = SessionLocal()

    try:

        file = (
            db.query(CodeFile)
            .filter(CodeFile.id == file_id)
            .first()
        )

        if not file:

            raise HTTPException(
                status_code=404,
                detail="File not found",
            )

        room = (
            db.query(Room)
            .filter(Room.id == file.room_id)
            .first()
        )

        if not room:

            raise HTTPException(
                status_code=404,
                detail="Room not found",
            )

        room_code = room.room_code
        deleted_file = serialize_file(file)

        db.delete(file)
        db.commit()

        await manager.broadcast_room(
            room_code,
            {
                "type": "file_deleted",
                "file_id": file_id,
                "filename": deleted_file["filename"],
            },
        )

        return {
            "success": True,
            "message": "File deleted successfully",
        }

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


# ==================================================
# SAVE CODE
# ==================================================

@app.post("/save-code")
def save_code(
    data: CodeSave,
    current_user: User = Depends(get_current_user),
):

    db = SessionLocal()

    try:

        room = get_room(db, data.room_code)

        if not room:

            raise HTTPException(
                status_code=404,
                detail="Room not found",
            )

        if getattr(current_user, "guest", False) and room.room_code != current_user.room_code:
            raise HTTPException(status_code=403, detail="Guest access is limited to the invited room")

        file = (
            db.query(CodeFile)
            .filter(
                CodeFile.room_id == room.id,
                CodeFile.filename == data.filename,
            )
            .first()
        )

        if file:

            file.content = data.content
            file.language = data.language

        else:

            file = CodeFile(
                filename=data.filename,
                language=data.language,
                content=data.content,
                room_id=room.id,
            )

            db.add(file)

        db.commit()
        db.refresh(file)

        return {
            "success": True,
            "message": "Code saved successfully",
            "file": serialize_file(file),
        }

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


# ==================================================
# GET CODE
# ==================================================

@app.get("/get-code/{room_code}")
def get_code(
    room_code: str,
    current_user: User = Depends(get_current_user),
):

    db = SessionLocal()

    try:

        room = get_room(db, room_code)

        if not room:

            raise HTTPException(
                status_code=404,
                detail="Room not found",
            )

        files = (
            db.query(CodeFile)
            .filter(CodeFile.room_id == room.id)
            .order_by(CodeFile.id.asc())
            .all()
        )

        return [
            serialize_file(file)
            for file in files
        ]

    finally:
        db.close()


# ==================================================
# SEND CHAT MESSAGE
# ==================================================

@app.post("/chat/{room_code}/send")
async def send_chat_message(
    room_code: str,
    data: ChatMessageCreate,
    current_user: User = Depends(get_current_user),
):

    clean_message = data.message.strip()

    if not clean_message:

        raise HTTPException(
            status_code=400,
            detail="Message cannot be empty",
        )

    if len(clean_message) > 2000:

        raise HTTPException(
            status_code=400,
            detail="Message is too long",
        )

    db = SessionLocal()

    try:

        room = get_room(db, room_code)

        if not room:

            raise HTTPException(
                status_code=404,
                detail="Room not found",
            )

        chat_message = ChatMessage(
            room_code=room.room_code,
            username=current_user.username,
            message=clean_message,
        )

        db.add(chat_message)
        db.commit()
        db.refresh(chat_message)

        message_data = serialize_chat(chat_message)

        await manager.broadcast_room(
            room.room_code,
            {
                "type": "chat_message",
                "message": message_data,
            },
        )

        return {
            "success": True,
            "message": message_data,
        }

    except Exception:
        db.rollback()
        raise

    finally:
        db.close()


# ==================================================
# GET CHAT MESSAGES
# ==================================================

@app.get("/chat/{room_code}")
def get_chat_messages(
    room_code: str,
    current_user: User = Depends(get_current_user),
):

    db = SessionLocal()

    try:

        room = get_room(db, room_code)

        if not room:

            raise HTTPException(
                status_code=404,
                detail="Room not found",
            )

        messages = (
            db.query(ChatMessage)
            .filter(ChatMessage.room_code == room.room_code)
            .order_by(ChatMessage.id.asc())
            .all()
        )

        return [
            serialize_chat(message)
            for message in messages
        ]

    finally:
        db.close()


# ==================================================
# EXECUTE CODE
# ==================================================

@app.post("/execute")
async def run_code(
    data: CodeExecuteRequest,
    current_user: User = Depends(get_current_user),
):

    if os.getenv("CODE_EXECUTION_ENABLED", "true").lower() != "true":
        raise HTTPException(
            status_code=503,
            detail="Code execution is disabled on this hosted deployment.",
        )

    if data.room_code:

        db = SessionLocal()

        try:

            room = get_room(db, data.room_code)

            if not room:

                raise HTTPException(
                    status_code=404,
                    detail="Room not found",
                )

            if getattr(current_user, "guest", False) and room.room_code != current_user.room_code:
                raise HTTPException(status_code=403, detail="Guest access is limited to the invited room")

            room_code = room.room_code

        finally:
            db.close()

    else:
        if getattr(current_user, "guest", False):
            raise HTTPException(status_code=403, detail="Guest code execution must be linked to the invited room")
        room_code = None

    result = await asyncio.to_thread(
        execute_code,
        data.language,
        data.code,
        data.stdin,
    )

    exit_code = result.get("exit_code", 0)
    error = result.get("error", "")

    response = {
        "success": exit_code == 0 and not error,
        "output": result.get("output", ""),
        "error": error,
        "execution_time": result.get("execution_time", 0),
        "exit_code": exit_code,
    }

    if room_code:

        await manager.broadcast_room(
            room_code,
            {
                "type": "execution_result",
                "result": response,
                "username": current_user.username,
                "language": data.language,
            },
        )

    return response


# ==================================================
# WEBSOCKET COLLABORATION
# ==================================================

@app.websocket("/ws/{room_code}")
async def websocket_endpoint(
    websocket: WebSocket,
    room_code: str,
    token: Optional[str] = None,
):

    # Verify JWT token
    user = get_websocket_user(token)

    if not user:

        await websocket.close(
            code=1008,
            reason="Authentication required",
        )

        return

    if getattr(user, "room_code", room_code).upper() != room_code.upper():
        await websocket.close(code=1008, reason="Guest access is limited to the invited room")
        return

    # Verify room
    db = SessionLocal()

    try:

        room = get_room(db, room_code)

        if not room:

            await websocket.close(
                code=1008,
                reason="Room not found",
            )

            return

        room_code = room.room_code

    finally:
        db.close()

    username = user.username

    await manager.connect(
        websocket,
        room_code,
        username,
    )

    try:

        while True:

            raw_data = await websocket.receive_text()

            try:
                message = json.loads(raw_data)
            except json.JSONDecodeError:
                continue

            message_type = message.get("type")

            # ----------------------------------
            # LIVE CODE UPDATE
            # ----------------------------------

            if message_type == "code":

                updated_code = message.get(
                    "content",
                    message.get("code", ""),
                )

                await manager.broadcast(
                    {
                        "type": "code",
                        "code": updated_code,
                        "content": updated_code,
                        "file_id": message.get("file_id"),
                        "filename": message.get("filename", ""),
                        "username": username,
                    },
                    room_code,
                    websocket,
                )

            # ----------------------------------
            # LANGUAGE UPDATE
            # ----------------------------------

            elif message_type == "language":

                await manager.broadcast(
                    {
                        "type": "language",
                        "language": message.get(
                            "language",
                            "python",
                        ),
                        "file_id": message.get("file_id"),
                        "filename": message.get("filename", ""),
                        "username": username,
                    },
                    room_code,
                    websocket,
                )

    except WebSocketDisconnect:

        manager.disconnect(
            websocket,
            room_code,
        )

        await manager.broadcast_participants(room_code)

    except Exception as error:

        print("WebSocket error:", repr(error))

        manager.disconnect(
            websocket,
            room_code,
        )

        await manager.broadcast_participants(room_code)
