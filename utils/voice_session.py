"""
Core orchestrator for a single voice interview session.

Manages the lifecycle of:
- Cartesia TTS WebSocket (Sonic-3) for the existing RPM transport
- Browser TTS fallback when Cartesia is unavailable
- LiveAvatar FULL session keep-alive / fallback handling
- OpenAI GPT for conversational pacing and evaluation
- State machine for turn management and interruption handling
"""
import asyncio
import base64
import json
import os
import re
import uuid
from contextlib import suppress
from typing import Callable, Literal, Optional

import websockets
from dotenv import load_dotenv

from utils.ai_conversation import (
    generate_intro_text,
    generate_interviewer_response,
    generate_turkish_questions,
)
from utils.ai_evaluator import evaluate_interview
from utils.liveavatar_client import LiveAvatarClient
from database import SessionLocal
from crud.interview import get_interview, update_interview, update_interview_feedback

load_dotenv()

CARTESIA_API_KEY = os.getenv("CARTESIA_API_KEY")
if not CARTESIA_API_KEY:
    print("[WARNING] CARTESIA_API_KEY is missing in .env file! TTS will not work.")
else:
    print(f"[INFO] CARTESIA_API_KEY found (length: {len(CARTESIA_API_KEY)})")
CARTESIA_STT_URL = "wss://api.cartesia.ai/stt/websocket"
CARTESIA_TTS_URL = "wss://api.cartesia.ai/tts/websocket"
CARTESIA_VERSION = "2026-03-01"
VOICE_ID = "0f95596c-09c4-4418-99fe-5c107e0713c0"
LIVEAVATAR_KEEPALIVE_INTERVAL_SECONDS = 45

SessionState = Literal["idle", "ai_speaking", "listening", "processing", "evaluating", "done"]
AvatarProvider = Literal["rpm_cartesia", "liveavatar_full"]
OutputMode = Literal["cartesia_stream", "liveavatar", "browser_tts"]


class VoiceInterviewSession:
    """
    Manages a single voice interview session.

    Lifecycle:
    1. start() → generates questions, initializes output transport, speaks intro
    2. handle_submit_answer() → saves answer, gets GPT response, speaks next turn
    3. handle_interrupt() → cancels current output and switches to listening
    4. handle_avatar_done_speaking() → client ack for LiveAvatar turn completion
    5. end_session() / cleanup() → evaluation and resource cleanup
    """

    def __init__(
        self,
        send_json: Callable,
        send_binary: Callable,
        workspace_id: int,
        categories: str,
        difficulty: str,
        interview_type: str,
        job_description: str,
        interview_id: int,
        requested_avatar_provider: AvatarProvider = "rpm_cartesia",
        liveavatar_session_id: Optional[str] = None,
        cv_data: Optional[dict] = None,
    ):
        self.send_json = send_json
        self.send_binary = send_binary
        self.workspace_id = workspace_id
        self.categories = categories
        self.difficulty = difficulty
        self.interview_type = interview_type
        self.job_description = job_description
        self.interview_id = interview_id
        self.requested_avatar_provider = requested_avatar_provider
        self.active_avatar_provider: AvatarProvider = requested_avatar_provider
        self.active_output_mode: OutputMode = (
            "liveavatar" if requested_avatar_provider == "liveavatar_full" else "cartesia_stream"
        )
        self.liveavatar_session_id = liveavatar_session_id
        self.cv_data = cv_data

        self.state: SessionState = "idle"
        self.questions: list = []
        self.current_question_index = 0
        self.follow_up_count = 0
        self.conversation_history: list = []
        self.qa_pairs: list = []
        self.current_candidate_transcript = ""
        self.current_accumulated_answer = ""
        self.active_utterance_id: Optional[str] = None
        self.last_interviewer_text: Optional[str] = None

        self._tts_ws: Optional[websockets.WebSocketClientProtocol] = None
        self._current_tts_context_id: Optional[str] = None
        self._tts_listener_task: Optional[asyncio.Task] = None
        self._stt_listener_task: Optional[asyncio.Task] = None
        self.keepalive_task: Optional[asyncio.Task] = None
        self._liveavatar_client = LiveAvatarClient()
        self._last_tts_error: Optional[str] = None
        self._is_running = False
        self._is_wrapping_up = False
        self._completed = False
        self._evaluation_done = asyncio.Event()

        self.last_evaluation: dict = {}
        self.delivery_metadata: dict = {
            "initial_avatar_provider": requested_avatar_provider,
            "final_avatar_provider": requested_avatar_provider,
            "initial_output_mode": self.active_output_mode,
            "final_output_mode": self.active_output_mode,
            "liveavatar_session_id": liveavatar_session_id,
            "fallback_used": False,
            "fallback_reason": None,
        }

    async def start(self):
        """Initialize the session: generate questions, initialize transport, speak intro."""
        self._is_running = True

        loop = asyncio.get_event_loop()
        self.questions = await loop.run_in_executor(
            None,
            generate_turkish_questions,
            self.job_description,
            self.categories,
            self.difficulty,
            self.interview_type,
            self.cv_data,
        )

        if not self.questions:
            await self.send_json({"type": "error", "message": "Sorular üretilemedi."})
            return

        if self.active_avatar_provider == "rpm_cartesia":
            ready = await self._ensure_tts_connected(emit_error=False)
            if not ready:
                await self._switch_to_browser_tts(
                    self._last_tts_error or "Cartesia ses bağlantısı kurulamadı."
                )
        elif self.liveavatar_session_id:
            self.active_output_mode = "liveavatar"
            self.delivery_metadata["final_output_mode"] = "liveavatar"
            self.keepalive_task = asyncio.create_task(self._keep_liveavatar_session_alive())

        await self.send_json(
            {
                "type": "session_started",
                "interview_id": self.interview_id,
                "questions": self.questions,
                "avatar_provider": self.active_avatar_provider,
                "output_mode": self.active_output_mode,
            }
        )

        first_q = self.questions[0].get("question", "")
        intro_text = await loop.run_in_executor(
            None,
            generate_intro_text,
            self.job_description,
            self.difficulty,
            self.interview_type,
            first_q,
        )

        await self._speak_text(intro_text, question_index=0, entry_type="intro")

    async def handle_submit_answer(self, transcript: str):
        """User uploaded answer via REST. Process the given transcript."""
        if self.state != "listening":
            return
        if self._is_wrapping_up:
            # Interview is winding down — ignore further answers
            return

        self.current_candidate_transcript = transcript.strip()
        if not self.current_candidate_transcript:
            await self.send_json({"type": "error", "message": "Ses algılanamadı. Lütfen tekrar deneyin."})
            self.state = "listening"
            return
            
        if self.current_accumulated_answer:
            self.current_accumulated_answer += f"\n\n[Devam Eden Cevap]: {self.current_candidate_transcript}"
        else:
            self.current_accumulated_answer = self.current_candidate_transcript

        self.state = "processing"
        await self._process_candidate_answer(transcript)

    async def handle_pass_question(self):
        """Skip the current question and move to the next one."""
        if self.state in ("done", "evaluating"):
            return
        if self._is_wrapping_up:
            # Already speaking the goodbye — don't repeat the wrap-up flow
            return

        await self._cancel_current_output()

        self._save_current_answer(passed=True)
        self.current_question_index += 1
        self.follow_up_count = 0
        self.current_candidate_transcript = ""
        self.current_accumulated_answer = ""

        if self.current_question_index < len(self.questions):
            next_q = self.questions[self.current_question_index]
            transition_text = f"Tamam, bir sonraki soruya geçelim. {next_q.get('question', '')}"

            await self.send_json({"type": "next_question", "question_index": self.current_question_index})
            await self._speak_text(
                transition_text,
                question_index=self.current_question_index,
                action="next_question",
            )
        else:
            # No more questions — speak goodbye then evaluate
            goodbye_text = "Mülakatımız burada sona erdi. Katılımınız için teşekkür ederim, size en kısa sürede geri dönüş yapacağız. İyi günler!"
            self.conversation_history.append({
                "role": "interviewer",
                "text": goodbye_text,
                "action": "wrap_up",
            })
            self._is_wrapping_up = True
            await self._speak_text(goodbye_text, question_index=self.current_question_index)

    async def handle_interrupt(self):
        """Cancel current playback and switch to listening mode."""
        if self.state != "ai_speaking":
            return
        if self._is_wrapping_up:
            return

        await self._cancel_current_output()

        if self.conversation_history and self.conversation_history[-1].get("role") == "interviewer":
            self.conversation_history[-1]["interrupted"] = True

        self.active_utterance_id = None
        self.state = "listening"
        self.current_candidate_transcript = ""
        await self.send_json({"type": "ai_done_speaking"})

    async def handle_avatar_done_speaking(self, utterance_id: str):
        """Client acknowledgement that a LiveAvatar utterance finished."""
        if self.active_output_mode not in ("liveavatar", "browser_tts"):
            return
        if self.state != "ai_speaking":
            return
        if utterance_id != self.active_utterance_id:
            return

        self.active_utterance_id = None
        if self._is_wrapping_up:
            self._is_wrapping_up = False
            await self.send_json({"type": "ai_done_speaking", "wrap_up": True})
        else:
            self.state = "listening"
            self.current_candidate_transcript = ""
            await self.send_json({"type": "ai_done_speaking"})

    async def handle_avatar_output_error(self, utterance_id: Optional[str], reason: str):
        """Fallback to the existing Cartesia transport if LiveAvatar fails."""
        if self.active_avatar_provider != "liveavatar_full":
            return

        self.delivery_metadata["fallback_used"] = True
        self.delivery_metadata["fallback_reason"] = reason
        await self._switch_to_rpm_cartesia(reason)

        if self.state == "ai_speaking" and self.last_interviewer_text:
            if utterance_id and self.active_utterance_id and utterance_id != self.active_utterance_id:
                return
            await self._send_tts_request(self.last_interviewer_text)

    async def end_session(self):
        """End the session early — finalize current answer and run evaluation."""
        # Already finished — re-emit the saved evaluation so a frontend that
        # may have just started waiting on "session_complete" can transition
        # cleanly. Without this, clicking End after the AI's auto-wrap-up
        # leaves the UI hanging on the active interview screen.
        if self.state == "done":
            if self.last_evaluation:
                await self.send_json({
                    "type": "evaluation",
                    "results": self.last_evaluation.get("results", []),
                    "overall_score": self.last_evaluation.get("overall_score", 0),
                    "overall_feedback": self.last_evaluation.get("overall_feedback", ""),
                })
            await self.send_json({"type": "session_complete"})
            return

        if self.state == "evaluating":
            # Evaluation already kicked off — do nothing, the events are coming.
            return

        await self._cancel_current_output()

        if self.current_candidate_transcript.strip():
            self._save_current_answer()

        await self._run_evaluation()

    async def handle_audio_chunk(self, audio_bytes: bytes):
        """Handle raw microphone audio from the frontend (no-op: STT is done via REST /transcribe)."""
        pass

    async def cleanup(self):
        """Close all connections and cancel tasks."""
        self._is_running = False

        await self._stop_liveavatar_session("USER_CLOSED")

        if self._tts_ws:
            with suppress(Exception):
                await self._tts_ws.close()

        for task in (self._stt_listener_task, self._tts_listener_task):
            if task and not task.done():
                task.cancel()
                with suppress(asyncio.CancelledError):
                    await task

    async def _keep_liveavatar_session_alive(self):
        """Ping the LiveAvatar session while the interview is active."""
        while self._is_running and self.active_avatar_provider == "liveavatar_full" and self.liveavatar_session_id:
            await asyncio.sleep(LIVEAVATAR_KEEPALIVE_INTERVAL_SECONDS)
            if not self._is_running or self.active_avatar_provider != "liveavatar_full" or not self.liveavatar_session_id:
                return
            try:
                await self._liveavatar_client.keep_alive(self.liveavatar_session_id)
            except Exception as exc:
                await self.handle_avatar_output_error(
                    self.active_utterance_id,
                    f"LiveAvatar keep-alive failed: {exc}",
                )
                return

    async def _cancel_keepalive_task(self):
        """Cancel the keep-alive task safely, even if called from within the task itself."""
        task = self.keepalive_task
        if not task:
            return

        self.keepalive_task = None
        if task.done():
            return

        task.cancel()
        if task is asyncio.current_task():
            return

        with suppress(asyncio.CancelledError):
            await task

    async def _stop_liveavatar_session(self, reason: str):
        """Stop the remote LiveAvatar session and prevent further keep-alives."""
        await self._cancel_keepalive_task()

        session_id = self.liveavatar_session_id
        if not session_id:
            return

        self.liveavatar_session_id = None
        try:
            await self._liveavatar_client.stop_session(session_id, reason)
        except Exception as exc:
            print(f"[LiveAvatar] stop_session failed for {session_id}: {exc}")

    async def _process_candidate_answer(self, transcript: str):
        """Process candidate's answer: save, ask GPT, speak response."""
        self.conversation_history.append({"role": "candidate", "text": transcript})

        current_q = self.questions[self.current_question_index]
        remaining = self.questions[self.current_question_index + 1 :]
        loop = asyncio.get_event_loop()
        gpt_response = await loop.run_in_executor(
            None,
            generate_interviewer_response,
            self.conversation_history,
            current_q,
            remaining,
            self.job_description,
            self.difficulty,
            self.follow_up_count,
        )

        response_text = gpt_response.get("response_text", "Devam edelim.")
        action = gpt_response.get("action", "next_question")

        if action == "next_question":
            self._save_current_answer()
            self.current_question_index += 1
            self.follow_up_count = 0
            self.current_candidate_transcript = ""
            self.current_accumulated_answer = ""

            if self.current_question_index < len(self.questions):
                await self.send_json({"type": "next_question", "question_index": self.current_question_index})
                await self._speak_text(
                    response_text,
                    question_index=self.current_question_index,
                    action=action,
                )
            else:
                # All questions done — speak the goodbye text, then evaluate after TTS finishes
                self._is_wrapping_up = True
                await self._speak_text(response_text, question_index=self.current_question_index)

        elif action == "follow_up":
            self.follow_up_count += 1
            self.current_candidate_transcript = ""  # Reset for the follow-up answer
            self.current_accumulated_answer += f"\n\n[Mülakatçı Takip Sorusu]: {response_text.strip()}"
            await self._speak_text(response_text, question_index=self.current_question_index)

        elif action == "wrap_up":
            self._save_current_answer()
            self._is_wrapping_up = True
            await self._speak_text(response_text, question_index=self.current_question_index)

    def _save_current_answer(self, passed: bool = False):
        """Save the current question's answer to qa_pairs."""
        if self.current_question_index < len(self.questions):
            q = self.questions[self.current_question_index]
            self.qa_pairs.append({
                "question": q.get("question", ""),
                "topic": q.get("topic", ""),
                "answer": "(Pas geçildi)" if passed else (self.current_accumulated_answer.strip() or "(Cevap verilmedi)"),
            })
        # Snapshot in-progress state to DB so a refresh can resume from this point.
        try:
            asyncio.create_task(self._persist_progress())
        except RuntimeError:
            # No running loop (shouldn't happen in normal flow) — skip persistence.
            pass

    async def _persist_progress(self):
        """Snapshot current qa_pairs / conversation_history / question index to DB.

        This runs after each `_save_current_answer` so that if the user refreshes
        the page mid-interview, `resume_from_db` can rebuild the session.
        Skips if the session has already been finalised (so a late task can't
        overwrite the saved evaluation feedback).
        """
        if not self.interview_id:
            return
        if self._completed:
            return
        snapshot = {
            "qa_pairs": self.qa_pairs,
            "conversation_history": self.conversation_history,
            "current_question_index": self.current_question_index,
            "in_progress": True,
        }
        loop = asyncio.get_event_loop()

        def _write():
            db = SessionLocal()
            try:
                update_interview_feedback(
                    db=db,
                    interview_id=self.interview_id,
                    feedback=json.dumps(snapshot, ensure_ascii=False),
                )
            finally:
                db.close()

        await loop.run_in_executor(None, _write)

    async def resume_from_db(self):
        """Rebuild a session from the persisted DB state and re-ask the current question.

        Used when the frontend sends `resume_session` after a page refresh —
        the user picks up exactly at the question they left off on, and the AI
        re-speaks that question from scratch.
        """
        self._is_running = True

        loop = asyncio.get_event_loop()

        def _read():
            db = SessionLocal()
            try:
                iv = get_interview(db, self.interview_id)
                if not iv:
                    return None
                questions = []
                if iv.transcript and iv.transcript != "[voice_session_started]":
                    try:
                        questions = json.loads(iv.transcript)
                    except json.JSONDecodeError:
                        questions = []
                snapshot = {}
                if iv.feedback:
                    try:
                        snapshot = json.loads(iv.feedback)
                    except json.JSONDecodeError:
                        snapshot = {}
                return {"questions": questions, "snapshot": snapshot}
            finally:
                db.close()

        data = await loop.run_in_executor(None, _read)
        if not data or not data["questions"]:
            await self.send_json({"type": "error", "message": "Mülakat verisi bulunamadı."})
            return

        self.questions = data["questions"]
        snapshot = data["snapshot"] or {}
        self.qa_pairs = snapshot.get("qa_pairs", []) or []
        self.conversation_history = snapshot.get("conversation_history", []) or []
        # Resume picks up at the next un-answered question
        self.current_question_index = min(
            len(self.qa_pairs),
            max(0, len(self.questions) - 1),
        )
        # Drop any partial in-progress answer state for the current question.
        self.follow_up_count = 0
        self.current_candidate_transcript = ""
        self.current_accumulated_answer = ""

        if self.active_avatar_provider == "rpm_cartesia":
            ready = await self._ensure_tts_connected(emit_error=False)
            if not ready:
                await self._switch_to_browser_tts(
                    self._last_tts_error or "Cartesia ses bağlantısı kurulamadı."
                )
        elif self.liveavatar_session_id:
            self.active_output_mode = "liveavatar"
            self.delivery_metadata["final_output_mode"] = "liveavatar"

        await self.send_json({
            "type": "session_started",
            "interview_id": self.interview_id,
            "questions": self.questions,
            "resumed": True,
            "current_question_index": self.current_question_index,
            "qa_pairs": self.qa_pairs,
            "conversation_history": self.conversation_history,
            "avatar_provider": self.active_avatar_provider,
            "output_mode": self.active_output_mode,
        })

        # If all questions were already answered, jump straight to evaluation.
        if len(self.qa_pairs) >= len(self.questions):
            self._is_wrapping_up = True
            await self._run_evaluation()
            return

        current_q = self.questions[self.current_question_index].get("question", "")
        resume_text = (
            "Tekrar hoş geldiniz. Kaldığımız yerden devam edelim. "
            f"Sorumuza dönelim: {current_q}"
        )
        self.conversation_history.append({
            "role": "interviewer",
            "text": resume_text,
            "action": "resume",
        })
        await self._speak_text(resume_text, question_index=self.current_question_index)

    async def _ensure_tts_connected(self, *, emit_error: bool = True) -> bool:
        """Ensure the Cartesia WebSocket is connected."""
        if self._tts_ws:
            state = getattr(self._tts_ws, "state", None)
            state_name = getattr(state, "name", str(state)).upper() if state is not None else ""
            if not state_name or state_name == "OPEN":
                return True
        return await self._connect_tts(emit_error=emit_error)

    def _extract_http_status(self, exc: Exception) -> Optional[int]:
        """Best-effort extraction of an HTTP status code from a WebSocket handshake error."""
        for attr in ("status_code", "status"):
            value = getattr(exc, attr, None)
            if isinstance(value, int):
                return value

        response = getattr(exc, "response", None)
        if response is not None:
            for attr in ("status_code", "status"):
                value = getattr(response, attr, None)
                if isinstance(value, int):
                    return value

        match = re.search(r"HTTP\s+(\d{3})", str(exc))
        if match:
            return int(match.group(1))
        return None

    def _format_tts_connection_error(self, exc: Exception) -> str:
        """Translate low-level Cartesia connection failures into actionable messages."""
        status_code = self._extract_http_status(exc)
        if status_code == 401:
            return "Cartesia TTS kimlik doğrulaması başarısız oldu (HTTP 401). API anahtarını kontrol edin."
        if status_code == 402:
            return (
                "Cartesia TTS erişimi reddedildi (HTTP 402). "
                "API anahtarını, planı veya kredi durumunu kontrol edin."
            )
        if status_code == 403:
            return "Cartesia TTS erişimi engellendi (HTTP 403). Hesap yetkilerini kontrol edin."
        if status_code == 429:
            return "Cartesia TTS eşzamanlı kullanım sınırına ulaştı (HTTP 429). Biraz sonra tekrar deneyin."
        if status_code is not None:
            return f"Cartesia TTS bağlantısı kurulamadı (HTTP {status_code})."
        return f"Cartesia TTS bağlantısı kurulamadı: {exc}"

    def _format_tts_api_error(self, payload: dict) -> str:
        """Normalize Cartesia runtime error payloads across API versions."""
        title = (payload.get("title") or "").strip()
        message = (payload.get("message") or payload.get("error") or "").strip()
        if title and message and message != title:
            return f"{title}: {message}"
        if message:
            return message
        if title:
            return title
        return "Bilinmeyen Cartesia hatası"

    async def _switch_to_browser_tts(self, reason: str, *, include_current_utterance: bool = False):
        """Fallback to local browser speech synthesis when server-side TTS is unavailable."""
        if self.active_output_mode == "browser_tts" and not include_current_utterance:
            return
        if self._tts_ws:
            with suppress(Exception):
                await self._tts_ws.close()
        self._tts_ws = None
        self._current_tts_context_id = None

        self.active_output_mode = "browser_tts"
        self.delivery_metadata["fallback_used"] = True
        self.delivery_metadata["fallback_reason"] = reason
        self.delivery_metadata["final_output_mode"] = "browser_tts"

        await self.send_json({
            "type": "error",
            "message": f"{reason} Tarayıcı seslendirmesine geçildi.",
            "recoverable": True,
        })

        payload = {
            "type": "output_mode_switched",
            "output_mode": "browser_tts",
            "reason": reason,
        }
        if include_current_utterance and self.last_interviewer_text and self.active_utterance_id:
            payload["transcript"] = self.last_interviewer_text
            payload["utterance_id"] = self.active_utterance_id
        await self.send_json(payload)

    async def _connect_tts(self, *, emit_error: bool = True) -> bool:
        """Open WebSocket connection to Cartesia TTS (Sonic-3)."""
        if not CARTESIA_API_KEY:
            await self.send_json({"type": "error", "message": "Cartesia yapılandırması eksik."})
            return False

        headers = {
            "Authorization": f"Bearer {CARTESIA_API_KEY}",
            "X-API-Key": CARTESIA_API_KEY,
            "Cartesia-Version": CARTESIA_VERSION,
        }

        try:
            self._tts_ws = await websockets.connect(CARTESIA_TTS_URL, additional_headers=headers)
            self._tts_listener_task = asyncio.create_task(self._tts_listener())
            self.active_output_mode = "cartesia_stream"
            self.delivery_metadata["final_output_mode"] = "cartesia_stream"
            self._last_tts_error = None
            print("[TTS] Connected to Cartesia Sonic-3")
            return True
        except Exception as exc:
            self._tts_ws = None
            self._last_tts_error = self._format_tts_connection_error(exc)
            print(f"[TTS] Connection error: {exc} -> {self._last_tts_error}")
            if emit_error:
                await self.send_json({
                    "type": "error",
                    "message": self._last_tts_error,
                    "recoverable": True,
                })
            return False

    async def _tts_listener(self):
        """Listen for TTS audio chunks from Cartesia and forward to frontend."""
        try:
            async for message in self._tts_ws:
                if not self._is_running:
                    break
                if self.state in ("evaluating", "done"):
                    continue

                try:
                    data = json.loads(message)
                    msg_type = data.get("type", "")

                    if msg_type == "chunk":
                        chunk_context = data.get("context_id", "")
                        if chunk_context == self._current_tts_context_id:
                            audio_b64 = data.get("data", "")
                            if audio_b64:
                                audio_bytes = base64.b64decode(audio_b64)
                                await self.send_binary(audio_bytes)

                    elif msg_type == "done":
                        context_id = data.get("context_id", "")
                        if context_id == self._current_tts_context_id:
                            if self._is_wrapping_up:
                                self._is_wrapping_up = False
                                await self.send_json({"type": "ai_done_speaking", "wrap_up": True})
                            elif self.state == "ai_speaking":
                                self.state = "listening"
                                self.current_candidate_transcript = ""
                                await self.send_json({"type": "ai_done_speaking"})

                    elif msg_type == "error":
                        err_msg = self._format_tts_api_error(data)
                        err_context = data.get("context_id", "")
                        if err_context and err_context != self._current_tts_context_id:
                            print(f"[TTS] Ignoring stale error for cancelled context {err_context}: {err_msg}")
                        else:
                            print(f"[TTS] Cartesia API Error: {err_msg}")
                            await self._switch_to_browser_tts(
                                f"Cartesia ses üretimi başarısız oldu: {err_msg}",
                                include_current_utterance=True,
                            )

                except json.JSONDecodeError:
                    pass

        except websockets.exceptions.ConnectionClosed:
            print("[TTS] Connection closed")
            if self._is_running and self.state == "ai_speaking" and self.active_output_mode == "cartesia_stream":
                await self._switch_to_browser_tts(
                    "Cartesia bağlantısı konuşma sırasında kapandı.",
                    include_current_utterance=True,
                )
        except Exception as exc:
            print(f"[TTS] Listener error: {exc}")
            if self._is_running and self.state == "ai_speaking" and self.active_output_mode == "cartesia_stream":
                await self._switch_to_browser_tts(
                    f"Cartesia dinleyicisi hata verdi: {exc}",
                    include_current_utterance=True,
                )

    async def _speak_text(
        self,
        text: str,
        *,
        question_index: int = 0,
        action: Optional[str] = None,
        entry_type: Optional[str] = None,
        append_history: bool = True,
    ):
        """Dispatch interviewer text through the active avatar provider."""
        if not self._is_running:
            return

        if append_history:
            history_entry = {"role": "interviewer", "text": text}
            if action:
                history_entry["action"] = action
            if entry_type:
                history_entry["type"] = entry_type
            self.conversation_history.append(history_entry)

        self.state = "ai_speaking"
        self.active_utterance_id = str(uuid.uuid4())[:20]
        self.last_interviewer_text = text
        self.delivery_metadata["final_avatar_provider"] = self.active_avatar_provider
        self.delivery_metadata["final_output_mode"] = self.active_output_mode

        await self.send_json(
            {
                "type": "ai_speaking",
                "transcript": text,
                "question_index": question_index,
                "utterance_id": self.active_utterance_id,
                "avatar_provider": self.active_avatar_provider,
                "output_mode": self.active_output_mode,
                "wrap_up": self._is_wrapping_up,
            }
        )

        if self.active_output_mode == "cartesia_stream":
            await self._send_tts_request(text)

    async def _send_tts_request(self, text: str):
        """Send interviewer text to Cartesia for streamed playback."""
        ready = await self._ensure_tts_connected(emit_error=False)
        if not ready:
            await self._switch_to_browser_tts(
                self._last_tts_error or "Cartesia ses bağlantısı kurulamadı.",
                include_current_utterance=True,
            )
            return

        self._current_tts_context_id = str(uuid.uuid4())[:20]
        tts_request = {
            "model_id": "sonic-3",
            "transcript": text,
            "voice": {
                "mode": "id",
                "id": VOICE_ID,
            },
            "language": "tr",
            "context_id": self._current_tts_context_id,
            "output_format": {
                "container": "raw",
                "encoding": "pcm_f32le",
                "sample_rate": 24000,
            },
            "continue": False,
        }

        try:
            await self._tts_ws.send(json.dumps(tts_request))
        except Exception as exc:
            print(f"[TTS] Send error: {exc}")
            self._current_tts_context_id = None
            await self._switch_to_browser_tts(
                f"Cartesia ses aktarımı başarısız oldu: {exc}",
                include_current_utterance=True,
            )

    async def _cancel_current_output(self):
        """Cancel the active transport if there is one."""
        if self.active_output_mode == "cartesia_stream":
            await self._cancel_tts()
        self._current_tts_context_id = None

    async def _cancel_tts(self):
        """Cancel any active Cartesia playback."""
        if self._tts_ws and self._current_tts_context_id:
            try:
                await self._tts_ws.send(
                    json.dumps({"context_id": self._current_tts_context_id, "cancel": True})
                )
                print(f"[TTS] Cancelled context: {self._current_tts_context_id}")
            except Exception as exc:
                print(f"Error cancelling TTS context: {exc}")

    async def _switch_to_rpm_cartesia(self, reason: str):
        """Switch the active output provider to the existing Cartesia path."""
        if self.active_avatar_provider == "rpm_cartesia":
            return

        self.active_avatar_provider = "rpm_cartesia"
        self.delivery_metadata["final_avatar_provider"] = "rpm_cartesia"
        self.active_output_mode = "cartesia_stream"
        self.delivery_metadata["final_output_mode"] = "cartesia_stream"

        await self._stop_liveavatar_session("SERVER_FALLBACK")

        await self.send_json(
            {
                "type": "avatar_provider_switched",
                "avatar_provider": "rpm_cartesia",
                "reason": reason,
            }
        )

        ready = await self._ensure_tts_connected(emit_error=False)
        if not ready:
            await self._switch_to_browser_tts(
                self._last_tts_error or f"{reason} Ayrıca Cartesia da kullanılamadı.",
                include_current_utterance=True,
            )

    async def _run_evaluation(self):
        """Run final evaluation using the existing evaluator."""
        await self._cancel_current_output()
        self.active_utterance_id = None
        await self._stop_liveavatar_session("INTERVIEW_COMPLETED")

        if not self.qa_pairs:
            self.last_evaluation = {
                "results": [],
                "overall_score": 0,
                "overall_feedback": "Değerlendirilecek cevap bulunamadı.",
            }
            await self._mark_completed()
            await self.send_json({
                "type": "evaluation",
                **self.last_evaluation,
            })
            await self.send_json({"type": "session_complete"})
            self.state = "done"
            self._evaluation_done.set()
            return

        self.state = "evaluating"
        await self.send_json({"type": "evaluating"})

        loop = asyncio.get_event_loop()
        evaluation = await loop.run_in_executor(
            None,
            lambda: evaluate_interview(
                qa_pairs=self.qa_pairs,
                job_description=self.job_description,
                difficulty=self.difficulty,
                interview_type=self.interview_type,
            ),
        )

        self.last_evaluation = evaluation

        # Persist results + flip status to "completed" BEFORE notifying the
        # frontend, so even if the user clicks "Start Another Interview" the
        # instant they see the results panel, the row is already finalised.
        # This also short-circuits any late `_persist_progress` task from
        # accidentally re-writing an `in_progress` snapshot.
        await self._mark_completed()

        await self.send_json({
            "type": "evaluation",
            "results": evaluation.get("results", []),
            "overall_score": evaluation.get("overall_score", 0),
            "overall_feedback": evaluation.get("overall_feedback", ""),
        })

        await self.send_json({"type": "session_complete"})
        self.state = "done"
        self._evaluation_done.set()

    async def _mark_completed(self):
        """Write the final evaluation feedback + status='completed' to the DB.

        Called from inside `_run_evaluation` so completion is durable regardless
        of whether the WS handler's outer `_save_session_to_db` runs (it can be
        skipped if the client disconnects mid-flow).
        """
        if not self.interview_id:
            return
        feedback = {
            "qa_pairs": self.qa_pairs,
            "conversation_history": self.conversation_history,
        }
        if self.last_evaluation:
            feedback["results"] = self.last_evaluation.get("results", [])
            feedback["overall_score"] = self.last_evaluation.get("overall_score", 0)
            feedback["overall_feedback"] = self.last_evaluation.get("overall_feedback", "")

        # Capture finality flag so the disconnect handler knows not to re-snapshot.
        self._completed = True

        loop = asyncio.get_event_loop()

        def _write():
            db = SessionLocal()
            try:
                update_interview_feedback(
                    db=db,
                    interview_id=self.interview_id,
                    feedback=json.dumps(feedback, ensure_ascii=False),
                )
                update_interview(
                    db=db,
                    interview_id=self.interview_id,
                    overall_score=self.last_evaluation.get("overall_score", 0)
                    if self.last_evaluation
                    else None,
                    status="completed",
                )
            except Exception as e:
                print(f"[Session] _mark_completed write failed: {e}")
            finally:
                db.close()

        await loop.run_in_executor(None, _write)

    async def wait_for_evaluation(self, timeout: float = 120):
        """Wait for evaluation to complete (used by WS handler for DB persistence)."""
        try:
            await asyncio.wait_for(self._evaluation_done.wait(), timeout=timeout)
        except asyncio.TimeoutError:
            print("[Session] Evaluation timed out")
