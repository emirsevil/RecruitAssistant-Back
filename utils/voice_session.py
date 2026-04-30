"""
Core orchestrator for a single voice interview session.

Manages the lifecycle of:
- Cartesia TTS WebSocket (Sonic-3) for the existing RPM transport
- LiveAvatar FULL session keep-alive / fallback handling
- OpenAI GPT for conversational pacing and evaluation
- State machine for turn management and interruption handling
"""
import asyncio
import base64
import json
import os
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

load_dotenv()

CARTESIA_API_KEY = os.getenv("CARTESIA_API_KEY")
if not CARTESIA_API_KEY:
    print("⚠️ [WARNING] CARTESIA_API_KEY is missing in .env file! TTS fallback will not work.")
else:
    print(f"✅ [INFO] CARTESIA_API_KEY found (length: {len(CARTESIA_API_KEY)})")
CARTESIA_TTS_URL = "wss://api.cartesia.ai/tts/websocket"
CARTESIA_VERSION = "2025-04-16"
VOICE_ID = "0f95596c-09c4-4418-99fe-5c107e0713c0"
LIVEAVATAR_KEEPALIVE_INTERVAL_SECONDS = 45

SessionState = Literal["idle", "ai_speaking", "listening", "processing", "evaluating", "done"]
AvatarProvider = Literal["rpm_cartesia", "liveavatar_full"]


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
        self.liveavatar_session_id = liveavatar_session_id

        self.state: SessionState = "idle"
        self.questions: list = []
        self.current_question_index = 0
        self.follow_up_count = 0
        self.conversation_history: list = []
        self.qa_pairs: list = []
        self.current_candidate_transcript = ""
        self.active_utterance_id: Optional[str] = None
        self.last_interviewer_text: Optional[str] = None

        self._tts_ws: Optional[websockets.WebSocketClientProtocol] = None
        self._current_tts_context_id: Optional[str] = None
        self._tts_listener_task: Optional[asyncio.Task] = None
        self._stt_listener_task: Optional[asyncio.Task] = None
        self.keepalive_task: Optional[asyncio.Task] = None
        self._liveavatar_client = LiveAvatarClient()
        self._is_running = False

        self.last_evaluation: dict = {}
        self.delivery_metadata: dict = {
            "initial_avatar_provider": requested_avatar_provider,
            "final_avatar_provider": requested_avatar_provider,
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
        )

        if not self.questions:
            await self.send_json({"type": "error", "message": "Sorular üretilemedi."})
            return

        if self.active_avatar_provider == "rpm_cartesia":
            ready = await self._ensure_tts_connected()
            if not ready:
                return
        elif self.liveavatar_session_id:
            self.keepalive_task = asyncio.create_task(self._keep_liveavatar_session_alive())

        await self.send_json(
            {
                "type": "session_started",
                "interview_id": self.interview_id,
                "questions": self.questions,
                "avatar_provider": self.active_avatar_provider,
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

        self.current_candidate_transcript = transcript.strip()
        if not self.current_candidate_transcript:
            await self.send_json({"type": "error", "message": "Ses algılanamadı. Lütfen tekrar deneyin."})
            self.state = "listening"
            return

        self.state = "processing"
        await self._process_candidate_answer(transcript)

    async def handle_pass_question(self):
        """Skip the current question and move to the next one."""
        if self.state in ("done", "evaluating"):
            return

        await self._cancel_current_output()

        self._save_current_answer(passed=True)
        self.current_question_index += 1
        self.follow_up_count = 0
        self.current_candidate_transcript = ""

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
            await self._run_evaluation()

    async def handle_interrupt(self):
        """Cancel current playback and switch to listening mode."""
        if self.state != "ai_speaking":
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
        if self.active_avatar_provider != "liveavatar_full":
            return
        if self.state != "ai_speaking":
            return
        if utterance_id != self.active_utterance_id:
            return

        self.active_utterance_id = None
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
        """End the session early and run evaluation."""
        if self.state in ("done", "evaluating"):
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

            if self.current_question_index < len(self.questions):
                await self.send_json({"type": "next_question", "question_index": self.current_question_index})
                await self._speak_text(
                    response_text,
                    question_index=self.current_question_index,
                    action=action,
                )
            else:
                await self._cancel_current_output()
                await self._run_evaluation()

        elif action == "follow_up":
            self.follow_up_count += 1
            self.current_candidate_transcript = ""
            await self._speak_text(
                response_text,
                question_index=self.current_question_index,
                action=action,
            )

        elif action == "wrap_up":
            self._save_current_answer()
            await self._cancel_current_output()
            await self._run_evaluation()

    def _save_current_answer(self, passed: bool = False):
        """Save the current question's answer to qa_pairs."""
        if self.current_question_index < len(self.questions):
            q = self.questions[self.current_question_index]
            self.qa_pairs.append(
                {
                    "question": q.get("question", ""),
                    "topic": q.get("topic", ""),
                    "answer": "(Pas geçildi)"
                    if passed
                    else (self.current_candidate_transcript.strip() or "(Cevap verilmedi)"),
                }
            )

    async def _ensure_tts_connected(self) -> bool:
        """Ensure the Cartesia WebSocket is connected."""
        if self._tts_ws:
            state = getattr(self._tts_ws, "state", None)
            state_name = getattr(state, "name", str(state)).upper() if state is not None else ""
            if not state_name or state_name == "OPEN":
                return True
        return await self._connect_tts()

    async def _connect_tts(self) -> bool:
        """Open WebSocket connection to Cartesia TTS (Sonic-3)."""
        if not CARTESIA_API_KEY:
            await self.send_json({"type": "error", "message": "Cartesia yapılandırması eksik."})
            return False

        headers = {
            "X-API-Key": CARTESIA_API_KEY,
            "Cartesia-Version": CARTESIA_VERSION,
        }

        try:
            self._tts_ws = await websockets.connect(CARTESIA_TTS_URL, additional_headers=headers)
            self._tts_listener_task = asyncio.create_task(self._tts_listener())
            print("[TTS] Connected to Cartesia Sonic-3")
            return True
        except Exception as exc:
            print(f"[TTS] Connection error: {exc}")
            await self.send_json({"type": "error", "message": f"TTS bağlantı hatası: {exc}"})
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
                        audio_b64 = data.get("data", "")
                        if audio_b64:
                            audio_bytes = base64.b64decode(audio_b64)
                            await self.send_binary(audio_bytes)

                    elif msg_type == "done":
                        context_id = data.get("context_id", "")
                        if context_id == self._current_tts_context_id and self.state == "ai_speaking":
                            self._current_tts_context_id = None
                            self.active_utterance_id = None
                            self.state = "listening"
                            self.current_candidate_transcript = ""
                            await self.send_json({"type": "ai_done_speaking"})

                    elif msg_type == "error":
                        err_msg = data.get("error", "Unknown Cartesia error")
                        err_context = data.get("context_id", "")
                        if err_context and err_context != self._current_tts_context_id:
                            print(f"[TTS] Ignoring stale error for cancelled context {err_context}: {err_msg}")
                        else:
                            print(f"[TTS] Cartesia API Error: {err_msg}")
                            await self.send_json({"type": "error", "message": f"Ses üretim hatası (Cartesia): {err_msg}"})

                except json.JSONDecodeError:
                    pass

        except websockets.exceptions.ConnectionClosed:
            print("[TTS] Connection closed")
        except Exception as exc:
            print(f"[TTS] Listener error: {exc}")

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

        await self.send_json(
            {
                "type": "ai_speaking",
                "transcript": text,
                "question_index": question_index,
                "utterance_id": self.active_utterance_id,
                "avatar_provider": self.active_avatar_provider,
            }
        )

        if self.active_avatar_provider == "rpm_cartesia":
            await self._send_tts_request(text)

    async def _send_tts_request(self, text: str):
        """Send interviewer text to Cartesia for streamed playback."""
        ready = await self._ensure_tts_connected()
        if not ready:
            self.active_utterance_id = None
            self.state = "listening"
            await self.send_json({"type": "ai_done_speaking"})
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
            self.active_utterance_id = None
            self.state = "listening"
            await self.send_json({"type": "error", "message": f"Ses üretim hatası (Cartesia): {exc}"})
            await self.send_json({"type": "ai_done_speaking"})

    async def _cancel_current_output(self):
        """Cancel the active transport if there is one."""
        if self.active_avatar_provider == "rpm_cartesia":
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

        await self._stop_liveavatar_session("SERVER_FALLBACK")

        await self.send_json(
            {
                "type": "avatar_provider_switched",
                "avatar_provider": "rpm_cartesia",
                "reason": reason,
            }
        )

        ready = await self._ensure_tts_connected()
        if not ready:
            self.active_utterance_id = None
            self.state = "listening"
            await self.send_json({"type": "ai_done_speaking"})

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
            await self.send_json({"type": "evaluation", **self.last_evaluation})
            await self.send_json({"type": "session_complete"})
            self.state = "done"
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
                language="tr",
            ),
        )

        self.last_evaluation = evaluation
        await self.send_json(
            {
                "type": "evaluation",
                "results": evaluation.get("results", []),
                "overall_score": evaluation.get("overall_score", 0),
                "overall_feedback": evaluation.get("overall_feedback", ""),
            }
        )
        await self.send_json({"type": "session_complete"})
        self.state = "done"
