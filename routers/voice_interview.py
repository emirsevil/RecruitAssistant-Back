"""
FastAPI WebSocket endpoint for real-time voice interviews.

Handles:
- WebSocket connection lifecycle
- JSON control messages (start_session, interrupt, end_session)
- Binary audio forwarding (microphone PCM data from frontend)
- Session creation with database interaction
"""
import asyncio
import json
import os
import time
from typing import Optional
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, UploadFile, File, HTTPException, Depends
from sqlalchemy.orm import Session
from openai import OpenAI

from database import SessionLocal, get_db
from crud.workspace import get_workspace
from crud.interview import create_interview, update_interview_feedback, update_interview
from schemas.interview import LiveAvatarBootstrapRequest, LiveAvatarBootstrapResponse, LiveAvatarStopRequest
from utils.voice_session import VoiceInterviewSession
from utils.liveavatar_client import LiveAvatarClient, LiveAvatarConfigError, LiveAvatarAPIError
from routers.auth import get_current_user, get_current_user_ws
import models

router = APIRouter(tags=["Voice Interview"])

# NOTE: This OpenAI client is used ONLY for Whisper STT (speech-to-text).
# Whisper is an OpenAI-only API with no equivalent in Gemini or other providers.
# All other LLM calls (question generation, conversation, evaluation) go through
# the centralized provider in utils/ai_client.py.
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
liveavatar_client = LiveAvatarClient()

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
            "delivery_metadata": getattr(session, "delivery_metadata", {}),
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
            avatar_provider=getattr(session, "active_avatar_provider", "rpm_cartesia"),
        )
    except Exception as e:
        print(f"[WS] Error saving to DB: {e}")


@router.post("/voice-interview/liveavatar/bootstrap", response_model=LiveAvatarBootstrapResponse)
async def bootstrap_liveavatar_session(
    request: LiveAvatarBootstrapRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Create and start a LiveAvatar session, then return frontend-safe LiveKit credentials."""
    workspace = get_workspace(db, request.workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Çalışma alanı bulunamadı")
    if workspace.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Bu workspace'e erişim yetkiniz yok")

    try:
        token_data = await liveavatar_client.create_session_token()
        session_data = await liveavatar_client.start_session(token_data["session_token"])
    except LiveAvatarConfigError as exc:
        raise HTTPException(status_code=500, detail=str(exc)) from exc
    except LiveAvatarAPIError as exc:
        detail = (
            f"LiveAvatar {exc.path} returned {exc.status_code}: "
            f"{exc.response_body or str(exc)}"
        )
        raise HTTPException(status_code=502, detail=detail) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LiveAvatar başlatılamadı: {exc}") from exc

    return LiveAvatarBootstrapResponse(
        provider="liveavatar_full",
        liveavatar_session_id=session_data["session_id"],
        livekit_url=session_data["livekit_url"],
        livekit_client_token=session_data["livekit_client_token"],
        max_session_duration=session_data["max_session_duration"],
    )


@router.post("/voice-interview/liveavatar/stop")
async def stop_liveavatar_session(
    request: LiveAvatarStopRequest,
    db: Session = Depends(get_db),
    current_user: models.User = Depends(get_current_user),
):
    """Stop a bootstrap-created LiveAvatar session that never became a full interview session."""
    workspace = get_workspace(db, request.workspace_id)
    if not workspace:
        raise HTTPException(status_code=404, detail="Çalışma alanı bulunamadı")
    if workspace.user_id != current_user.id:
        raise HTTPException(status_code=403, detail="Bu workspace'e erişim yetkiniz yok")

    try:
        await liveavatar_client.stop_session(
            request.liveavatar_session_id,
            request.reason or "CLIENT_ABORTED",
        )
    except LiveAvatarAPIError as exc:
        if exc.status_code == 404:
            return {"stopped": True, "already_closed": True}
        detail = (
            f"LiveAvatar {exc.path} returned {exc.status_code}: "
            f"{exc.response_body or str(exc)}"
        )
        raise HTTPException(status_code=502, detail=detail) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"LiveAvatar durdurulamadı: {exc}") from exc

    return {"stopped": True}


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

    session: Optional[VoiceInterviewSession] = None
    db: Optional[Session] = None
    interview_id: Optional[int] = None
    session_start_time: Optional[float] = None
    duration_limit_task: Optional[asyncio.Task] = None

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
                    avatar_provider = data.get("avatar_provider", "rpm_cartesia")
                    liveavatar_session_id = data.get("liveavatar_session_id")
                    # Duration limit in seconds (default 10 min, max 30 min, min 60s)
                    raw_duration = data.get("duration_limit")
                    duration_limit = min(max(int(raw_duration or 600), 60), 1800)

                    if avatar_provider == "liveavatar_full" and not liveavatar_session_id:
                        await send_json({
                            "type": "error",
                            "message": "LiveAvatar oturumu eksik. Klasik avatar moduna geri dönülüyor.",
                        })
                        avatar_provider = "rpm_cartesia"

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

                    # For HR interviews, resolve the candidate's CV (workspace's
                    # generated CV → user's base CV). HR sessions cannot run
                    # without one — the prompt grounds questions in the CV.
                    cv_data = None
                    if interview_type == "hr":
                        from crud.cv import resolve_user_cv
                        cv_data, _cv_source = resolve_user_cv(db, current_user.id, workspace)
                        if cv_data is None:
                            await send_json({
                                "type": "error",
                                "message": "İK mülakatı için önce CV oluşturmanız veya yüklemeniz gerekir.",
                                "code": "MISSING_CV",
                            })
                            db.close()
                            db = None
                            continue

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

                    # ── DEMO MODE: 1 interview per workspace ───────────
                    from models import Interview as _Interview
                    existing_iv = (
                        db.query(_Interview)
                        .filter(
                            _Interview.workspace_id == workspace_id,
                            _Interview.status != "cancelled",
                        )
                        .count()
                    )
                    if existing_iv >= 1:
                        await send_json({
                            "type": "error",
                            "message": "Demo mode: only 1 interview allowed per workspace.",
                            "code": "DEMO_INTERVIEW_LIMIT_REACHED",
                        })
                        db.close()
                        db = None
                        continue
                    # ── END DEMO MODE ──────────────────────────────────

                    # Create interview record in DB with full metadata
                    interview = create_interview(
                        db=db,
                        workspace_id=workspace_id,
                        interview_type=interview_type,
                        transcript="[voice_session_started]",
                        difficulty=difficulty,
                        categories=categories,
                        mode="avatar" if avatar_provider == "liveavatar_full" else "voice",
                        status="in_progress",
                        avatar_provider=avatar_provider,
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
                        requested_avatar_provider=avatar_provider,
                        liveavatar_session_id=liveavatar_session_id,
                        cv_data=cv_data,
                    )

                    # Start the session (async: generates questions, connects to Cartesia, speaks intro)
                    await session.start()

                    # Server-side duration limit enforcement.
                    # The FRONTEND tracks fair "listening-only" time (pauses during
                    # AI speaking / processing). This backend guard is a hard
                    # wall-clock safety net at 2× the user-selected duration to
                    # prevent runaway sessions even if the client misbehaves.
                    hard_limit = duration_limit * 2

                    async def _duration_guard(limit_secs: int):
                        """Auto-end the interview after the hard wall-clock limit."""
                        await asyncio.sleep(limit_secs)
                        if session and session.state not in ("evaluating", "done"):
                            print(f"[WS] Hard duration limit reached ({limit_secs}s wall-clock) — ending session.")
                            await send_json({
                                "type": "error",
                                "message": "Süre doldu. Mülakat sona erdiriliyor.",
                                "recoverable": False,
                            })
                            await session.end_session()
                            await session.wait_for_evaluation()
                            await _save_session_to_db(session, db, interview_id, session_start_time)

                    duration_limit_task = asyncio.create_task(_duration_guard(hard_limit))

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

                elif msg_type == "avatar_done_speaking":
                    if session:
                        await session.handle_avatar_done_speaking(data.get("utterance_id", ""))

                elif msg_type == "avatar_output_error":
                    if session:
                        await session.handle_avatar_output_error(
                            data.get("utterance_id"),
                            data.get("reason", "LiveAvatar output failed"),
                        )

                elif msg_type == "end_session":
                    if session:
                        if duration_limit_task and not duration_limit_task.done():
                            duration_limit_task.cancel()
                        await session.end_session()
                        await session.wait_for_evaluation()
                        await _save_session_to_db(session, db, interview_id, session_start_time)

                elif msg_type == "start_evaluation":
                    # Frontend signals that goodbye audio playback finished
                    if session:
                        if duration_limit_task and not duration_limit_task.done():
                            duration_limit_task.cancel()
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
                from crud.interview import get_interview
                iv = get_interview(db, interview_id)
                if iv and iv.status == "in_progress":
                    # Save whatever qa_pairs and conversation history exist so far
                    if session:
                        await _save_session_to_db(session, db, interview_id, session_start_time)
                    
                    duration = int(time.time() - session_start_time) if session_start_time else None
                    update_interview(
                        db=db,
                        interview_id=interview_id,
                        status="cancelled",
                        duration_seconds=duration,
                        avatar_provider=getattr(session, "active_avatar_provider", "rpm_cartesia") if session else "rpm_cartesia",
                    )
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
        if duration_limit_task and not duration_limit_task.done():
            duration_limit_task.cancel()
        if session:
            await session.cleanup()
        if db:
            db.close()
        print("[WS] Connection cleaned up")
