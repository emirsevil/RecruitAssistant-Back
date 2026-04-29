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
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, UploadFile, File, HTTPException, Depends
from sqlalchemy.orm import Session
from openai import OpenAI

from database import SessionLocal, get_db
from crud.workspace import get_workspace
from crud.interview import create_interview, update_interview_feedback, update_interview
from utils.voice_session import VoiceInterviewSession
from routers.auth import get_current_user, get_current_user_ws
import models

router = APIRouter(tags=["Voice Interview"])

# NOTE: This OpenAI client is used ONLY for Whisper STT (speech-to-text).
# Whisper is an OpenAI-only API with no equivalent in Gemini or other providers.
# All other LLM calls (question generation, conversation, evaluation) go through
# the centralized provider in utils/ai_client.py.
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

@router.post("/voice-interview/transcribe")
async def transcribe_audio(
    file: UploadFile = File(...),
    current_user: models.User = Depends(get_current_user)
):
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
async def voice_interview_websocket(
    websocket: WebSocket,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user_ws)
):
    """
    WebSocket endpoint for real-time voice-dialogued mock interviews.
    """
    await websocket.accept()
    print(f"[WS] Client {current_user.email} connected")

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

                if msg_type == "resume_session":
                    if session is not None:
                        await send_json({"type": "error", "message": "Oturum zaten aktif"})
                        continue

                    resume_id = data.get("interview_id")
                    if not resume_id:
                        await send_json({"type": "error", "message": "interview_id gerekli"})
                        continue

                    db = get_db_session()
                    iv = None
                    try:
                        from crud.interview import get_interview as _get_iv
                        iv = _get_iv(db, int(resume_id))
                    except Exception as e:
                        print(f"[WS] resume lookup failed: {e}")
                        iv = None

                    if not iv:
                        await send_json({"type": "error", "message": "Mülakat bulunamadı"})
                        db.close()
                        db = None
                        continue

                    workspace = get_workspace(db, iv.workspace_id)
                    if not workspace or workspace.user_id != current_user.id:
                        await send_json({"type": "error", "message": "Bu mülakata erişim yetkiniz yok"})
                        db.close()
                        db = None
                        continue

                    if iv.status not in ("in_progress", None):
                        await send_json({
                            "type": "error",
                            "message": "Bu mülakat artık devam ettirilemez.",
                        })
                        db.close()
                        db = None
                        continue

                    interview_id = iv.id
                    session_start_time = time.time()
                    session = VoiceInterviewSession(
                        send_json=send_json,
                        send_binary=send_binary,
                        workspace_id=iv.workspace_id,
                        categories=iv.categories or "Genel",
                        difficulty=iv.difficulty or "junior",
                        interview_type=iv.interview_type or "hr",
                        job_description=workspace.job_description or "",
                        interview_id=iv.id,
                    )
                    await session.resume_from_db()

                elif msg_type == "start_session":
                    if session is not None:
                        await send_json({"type": "error", "message": "Oturum zaten aktif"})
                        continue

                    # Extract config
                    workspace_id = data.get("workspace_id", 1)
                    raw_categories = data.get("categories", "Genel")
                    categories = ", ".join(raw_categories) if isinstance(raw_categories, list) else raw_categories
                    difficulty = data.get("difficulty", "junior")
                    interview_type = data.get("interview_type", "hr")

                    # Validate workspace and ownership
                    db = get_db_session()
                    workspace = get_workspace(db, workspace_id)
                    if not workspace:
                        await send_json({"type": "error", "message": "Çalışma alanı bulunamadı"})
                        db.close()
                        db = None
                        continue
                    
                    if workspace.user_id != current_user.id:
                        await send_json({"type": "error", "message": "Bu workspace'e erişim yetkiniz yok"})
                        db.close()
                        db = None
                        continue

                    if not workspace.job_description:
                        await send_json({"type": "error", "message": "Çalışma alanında iş tanımı yok"})
                        db.close()
                        db = None
                        continue

                    job_description = workspace.job_description

                    # Auto-cancel any stale in-progress interviews in this
                    # workspace before creating a new one. Without this, rows
                    # left behind by abandoned/refreshed sessions would pile
                    # up forever in the DB.
                    try:
                        from crud.interview import list_interviews as _list_iv
                        for old in _list_iv(db, user_id=current_user.id, workspace_id=workspace_id):
                            if (old.status or "completed") == "in_progress":
                                update_interview(db=db, interview_id=old.id, status="cancelled")
                    except Exception as e:
                        print(f"[WS] auto-cancel stale in_progress failed: {e}")

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

                elif msg_type == "pass_question":
                    if session:
                        await session.handle_pass_question()

                elif msg_type == "end_session":
                    if session:
                        await session.end_session()
                        await session.wait_for_evaluation()
                        await _save_session_to_db(session, db, interview_id, session_start_time)

                elif msg_type == "start_evaluation":
                    # Frontend signals that goodbye audio playback finished
                    if session:
                        await session._run_evaluation()
                        await _save_session_to_db(session, db, interview_id, session_start_time)

                else:
                    await send_json({"type": "error", "message": f"Bilinmeyen mesaj tipi: {msg_type}"})

            # Handle binary messages (microphone audio)
            elif "bytes" in message:
                if session:
                    await session.handle_audio_chunk(message["bytes"])

    except WebSocketDisconnect:
        print("[WS] Client disconnected")
        # Keep status as "in_progress" so the user can resume after a refresh.
        # Snapshot whatever qa_pairs / conversation_history exist so far —
        # but ONLY if the session hasn't already been completed (otherwise we'd
        # stomp the freshly saved evaluation feedback and the row would look
        # in-progress on the next visit even though the user finished it).
        if db and interview_id and session:
            try:
                from crud.interview import get_interview as _get_iv
                iv = _get_iv(db, interview_id)
                if iv and iv.status == "in_progress" and not getattr(session, "_completed", False):
                    await session._persist_progress()
            except Exception as e:
                print(f"[WS] progress snapshot failed: {e}")
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
