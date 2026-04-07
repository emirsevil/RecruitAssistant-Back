"""
FastAPI WebSocket endpoint for real-time voice interviews.

Handles:
- WebSocket connection lifecycle
- JSON control messages (start_session, interrupt, end_session)
- Binary audio forwarding (microphone PCM data from frontend)
- Session creation with database interaction
"""
import json
import os
import time
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, UploadFile, File, HTTPException
from sqlalchemy.orm import Session
from openai import OpenAI

from database import SessionLocal
from crud.workspace import get_workspace
from crud.interview import create_interview, update_interview_feedback, update_interview
from utils.voice_session import VoiceInterviewSession

router = APIRouter(tags=["Voice Interview"])
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

@router.post("/voice-interview/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    """Transcribe uploaded audio file using OpenAI Whisper API."""
    try:
        # OpenAI requires a tuple of (filename, file_like_object, content_type)
        response = client.audio.transcriptions.create(
            model="whisper-1",
            file=(file.filename, file.file, file.content_type),
            language="tr"
        )
        return {"transcript": response.text}
    except Exception as e:
        print(f"STT Error: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def get_db_session() -> Session:
    """Create a database session for the WebSocket handler."""
    db = SessionLocal()
    try:
        return db
    except Exception:
        db.close()
        raise

async def _save_session_to_db(session, db, interview_id, session_start_time):
    """Save the final session data to the database."""
    if not (db and interview_id):
        return

    try:
        duration = int(time.time() - session_start_time) if session_start_time else None
        evaluation_data = {
            "qa_pairs": session.qa_pairs,
            "conversation_history": session.conversation_history,
        }

        # Merge evaluation results into feedback if available
        if hasattr(session, 'last_evaluation') and session.last_evaluation:
            evaluation_data["results"] = session.last_evaluation.get("results", [])
            evaluation_data["overall_score"] = session.last_evaluation.get("overall_score", 0)
            evaluation_data["overall_feedback"] = session.last_evaluation.get("overall_feedback", "")

        update_interview_feedback(
            db=db,
            interview_id=interview_id,
            feedback=json.dumps(evaluation_data, ensure_ascii=False),
        )
        update_interview(
            db=db,
            interview_id=interview_id,
            overall_score=session.last_evaluation.get("overall_score", 0) if hasattr(session, 'last_evaluation') and session.last_evaluation else None,
            duration_seconds=duration,
            status="completed",
        )
    except Exception as e:
        print(f"[WS] Error saving to DB: {e}")


@router.websocket("/ws/voice-interview")
async def voice_interview_websocket(websocket: WebSocket):
    """
    WebSocket endpoint for real-time voice-dialogued mock interviews.

    Protocol:
    - Client sends JSON messages for control (start_session, interrupt, end_session)
    - Client sends binary messages for microphone audio (PCM s16le 16kHz mono)
    - Server sends JSON messages for status updates
    - Server sends binary messages for TTS audio (PCM f32le 24kHz mono)
    """
    await websocket.accept()
    print("[WS] Client connected")

    session: VoiceInterviewSession | None = None
    db: Session | None = None
    interview_id: int | None = None
    session_start_time: float | None = None

    async def send_json(data: dict):
        """Send a JSON message to the client."""
        try:
            await websocket.send_json(data)
        except Exception as e:
            print(f"[WS] Error sending JSON: {e}")

    async def send_binary(data: bytes):
        """Send binary audio data to the client."""
        try:
            await websocket.send_bytes(data)
        except Exception as e:
            print(f"[WS] Error sending binary: {e}")

    try:
        while True:
            message = await websocket.receive()

            if message.get("type") == "websocket.disconnect":
                break

            # Handle text (JSON) messages
            if "text" in message:
                try:
                    data = json.loads(message["text"])
                except json.JSONDecodeError:
                    await send_json({"type": "error", "message": "Geçersiz JSON mesajı"})
                    continue

                msg_type = data.get("type", "")

                if msg_type == "start_session":
                    if session is not None:
                        await send_json({"type": "error", "message": "Oturum zaten aktif"})
                        continue

                    # Extract config
                    workspace_id = data.get("workspace_id", 1)
                    categories = data.get("categories", "Genel")
                    difficulty = data.get("difficulty", "junior")
                    interview_type = data.get("interview_type", "hr")

                    # Validate workspace
                    db = get_db_session()
                    workspace = get_workspace(db, workspace_id)
                    if not workspace:
                        await send_json({"type": "error", "message": "Çalışma alanı bulunamadı"})
                        db.close()
                        db = None
                        continue

                    if not workspace.job_description:
                        await send_json({"type": "error", "message": "Çalışma alanında iş tanımı yok"})
                        db.close()
                        db = None
                        continue

                    job_description = workspace.job_description

                    # Create interview record in DB with full metadata
                    interview = create_interview(
                        db=db,
                        workspace_id=workspace_id,
                        interview_type=interview_type,
                        transcript="[voice_session_started]",
                        difficulty=difficulty,
                        categories=categories,
                        mode="voice",
                        status="in_progress",
                    )
                    interview_id = interview.id
                    session_start_time = time.time()

                    # Create the voice session
                    session = VoiceInterviewSession(
                        send_json=send_json,
                        send_binary=send_binary,
                        workspace_id=workspace_id,
                        categories=categories,
                        difficulty=difficulty,
                        interview_type=interview_type,
                        job_description=job_description,
                        interview_id=interview.id,
                    )

                    # Start the session (async: generates questions, connects to Cartesia, speaks intro)
                    await session.start()

                elif msg_type == "interrupt":
                    if session:
                        await session.handle_interrupt()

                elif msg_type == "submit_answer":
                    if session:
                        # Frontend now sends the transcript generated by the Whisper API REST call
                        transcript = data.get("transcript", "")
                        await session.handle_submit_answer(transcript=transcript)
                        if session.state == "done":
                            await _save_session_to_db(session, db, interview_id, session_start_time)

                elif msg_type == "pass_question":
                    if session:
                        await session.handle_pass_question()
                        if session.state == "done":
                            await _save_session_to_db(session, db, interview_id, session_start_time)

                elif msg_type == "end_session":
                    if session:
                        await session.end_session()
                        await _save_session_to_db(session, db, interview_id, session_start_time)

                else:
                    await send_json({"type": "error", "message": f"Bilinmeyen mesaj tipi: {msg_type}"})

            # Handle binary messages (microphone audio)
            elif "bytes" in message:
                if session:
                    await session.handle_audio_chunk(message["bytes"])

    except WebSocketDisconnect:
        print("[WS] Client disconnected")
        # Mark as cancelled if session was in progress
        if db and interview_id:
            try:
                from crud.interview import get_interview
                iv = get_interview(db, interview_id)
                if iv and iv.status == "in_progress":
                    # Save whatever qa_pairs and conversation history exist so far
                    if session:
                        await _save_session_to_db(session, db, interview_id, session_start_time)
                    
                    duration = int(time.time() - session_start_time) if session_start_time else None
                    update_interview(db=db, interview_id=interview_id, status="cancelled", duration_seconds=duration)
            except Exception:
                pass
    except Exception as e:
        print(f"[WS] Unexpected error: {e}")
        try:
            await send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        # Cleanup
        if session:
            await session.cleanup()
        if db:
            db.close()
        print("[WS] Connection cleaned up")
