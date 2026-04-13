"""
Core orchestrator for a single voice interview session.

Manages the lifecycle of:
- Cartesia STT WebSocket (Ink-Whisper) for real-time transcription
- Cartesia TTS WebSocket (Sonic-3) for AI speech synthesis
- OpenAI GPT for conversational pacing and evaluation
- State machine for turn management and interruption handling
"""
import asyncio
import json
import os
import uuid
import base64
import struct
from typing import Callable, Optional, Literal

import websockets
from dotenv import load_dotenv

from utils.ai_conversation import (
    generate_turkish_questions,
    generate_intro_text,
    generate_interviewer_response,
)
from utils.ai_evaluator import evaluate_interview

load_dotenv()

CARTESIA_API_KEY = os.getenv("CARTESIA_API_KEY")
if not CARTESIA_API_KEY:
    print("⚠️ [WARNING] CARTESIA_API_KEY is missing in .env file! TTS will not work.")
else:
    print(f"✅ [INFO] CARTESIA_API_KEY found (length: {len(CARTESIA_API_KEY)})")
CARTESIA_STT_URL = "wss://api.cartesia.ai/stt/websocket"
CARTESIA_TTS_URL = "wss://api.cartesia.ai/tts/websocket"
CARTESIA_VERSION = "2025-04-16"
VOICE_ID = "0f95596c-09c4-4418-99fe-5c107e0713c0"  
SessionState = Literal["idle", "ai_speaking", "listening", "processing", "evaluating", "done"]


class VoiceInterviewSession:
    """
    Manages a single voice interview session.

    Lifecycle:
    1. start() → generates questions, opens Cartesia WS connections, speaks intro
    2. handle_audio_chunk() → forwards mic audio to STT
    3. handle_interrupt() → cancels TTS, switches to listening
    4. (internal) on STT final → sends to GPT → speaks response
    5. end() → final evaluation, cleanup
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
    ):
        self.send_json = send_json
        self.send_binary = send_binary
        self.workspace_id = workspace_id
        self.categories = categories
        self.difficulty = difficulty
        self.interview_type = interview_type
        self.job_description = job_description
        self.interview_id = interview_id

        # Interview state
        self.state: SessionState = "idle"
        self.questions: list = []
        self.current_question_index: int = 0
        self.follow_up_count: int = 0
        self.conversation_history: list = []  # Full dialogue for GPT context
        self.qa_pairs: list = []  # question/answer pairs for final evaluation
        self.current_candidate_transcript: str = ""

        # Cartesia connections
        self._tts_ws: Optional[websockets.WebSocketClientProtocol] = None
        self._current_tts_context_id: Optional[str] = None

        # Async tasks
        self._tts_listener_task: Optional[asyncio.Task] = None
        self._stt_listener_task: Optional[asyncio.Task] = None  # reserved for future STT streaming

        # Control flags
        self._is_running = False

        # Evaluation results (stored for DB persistence)
        self.last_evaluation: dict = {}

    async def start(self):
        """Initialize the session: generate questions, connect to Cartesia, speak intro."""
        self._is_running = True

        # Generate Turkish questions via GPT
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
        # Connect to Cartesia TTS
        await self._connect_tts()

        # Notify frontend
        await self.send_json({
            "type": "session_started",
            "interview_id": self.interview_id,
            "questions": self.questions,
        })

        # Generate and speak intro
        first_q = self.questions[0].get("question", "")
        intro_text = await loop.run_in_executor(
            None,
            generate_intro_text,
            self.job_description,
            self.difficulty,
            self.interview_type,
            first_q,
        )

        self.conversation_history.append({
            "role": "interviewer",
            "text": intro_text,
            "type": "intro",
        })

        await self._speak_text(intro_text, question_index=0)



    async def handle_submit_answer(self, transcript: str):
        """User uploaded answer via REST. Process the given transcript."""
        if self.state != "listening":
            return

        self.current_candidate_transcript = transcript.strip()
        if not self.current_candidate_transcript:
            # No meaningful speech detected — notify frontend
            await self.send_json({"type": "error", "message": "Ses algılanamadı. Lütfen tekrar deneyin."})
            self.state = "listening"
            return

        self.state = "processing"
        await self._process_candidate_answer(transcript)

    async def handle_pass_question(self):
        """Skip the current question and move to the next one."""
        if self.state == "done" or self.state == "evaluating":
            return

        # Cancel any active TTS first
        await self._cancel_tts()

        # Save as passed
        self._save_current_answer(passed=True)
        self.current_question_index += 1
        self.follow_up_count = 0
        self.current_candidate_transcript = ""

        if self.current_question_index < len(self.questions):
            # Move to next question
            next_q = self.questions[self.current_question_index]
            transition_text = f"Tamam, bir sonraki soruya geçelim. {next_q.get('question', '')}"

            self.conversation_history.append({
                "role": "interviewer",
                "text": transition_text,
                "action": "next_question",
            })

            await self.send_json({
                "type": "next_question",
                "question_index": self.current_question_index,
            })
            await self._speak_text(transition_text, question_index=self.current_question_index)
        else:
            # No more questions — evaluate
            await self._run_evaluation()

    async def handle_interrupt(self):
        """Cancel current TTS playback and switch to listening mode."""
        if self.state != "ai_speaking":
            return

        print(f"[Session] Interrupt received during TTS context: {self._current_tts_context_id}")

        # Cancel active TTS context
        await self._cancel_tts()

        # Mark the partial AI utterance in history
        if self.conversation_history and self.conversation_history[-1].get("role") == "interviewer":
            self.conversation_history[-1]["interrupted"] = True

        # Switch to listening
        self.state = "listening"
        self.current_candidate_transcript = ""
        await self.send_json({"type": "ai_done_speaking"})

    async def end_session(self):
        """End the session early — finalize current answer and run evaluation."""
        if self.state == "done" or self.state == "evaluating":
            return

        # Cancel any active TTS
        await self._cancel_tts()

        # Save current transcript if any
        if self.current_candidate_transcript.strip():
            self._save_current_answer()

        await self._run_evaluation()

    async def _cancel_tts(self):
        """Cancel any active TTS playback."""
        if self._tts_ws and self._current_tts_context_id:
            try:
                cancel_msg = {
                    "context_id": self._current_tts_context_id,
                    "cancel": True,
                }
                await self._tts_ws.send(json.dumps(cancel_msg))
                print(f"[TTS] Cancelled context: {self._current_tts_context_id}")
            except Exception as e:
                print(f"Error cancelling TTS context: {e}")
            self._current_tts_context_id = None

    async def handle_audio_chunk(self, audio_bytes: bytes):
        """Handle raw microphone audio from the frontend (no-op: STT is done via REST /transcribe)."""
        # Audio transcription is handled via the REST endpoint /voice-interview/transcribe.
        # This method exists so the WebSocket handler can safely forward binary frames.
        pass

    async def cleanup(self):
        """Close all connections and cancel tasks."""
        self._is_running = False

        # Close TTS
        if self._tts_ws:
            try:
                await self._tts_ws.close()
            except Exception:
                pass

        # Cancel listener tasks safely
        for task in [self._stt_listener_task, self._tts_listener_task]:
            if task and not task.done():
                task.cancel()



    async def _process_candidate_answer(self, transcript: str):
        """Process candidate's answer: save, ask GPT, speak response."""
        # Save to conversation history
        self.conversation_history.append({
            "role": "candidate",
            "text": transcript,
        })

        current_q = self.questions[self.current_question_index]

        # Get GPT response in a thread (blocking call)
        remaining = self.questions[self.current_question_index + 1:]
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

        # Save to conversation history
        self.conversation_history.append({
            "role": "interviewer",
            "text": response_text,
            "action": action,
        })

        if action == "next_question":
            # Save the Q&A pair for final evaluation
            self._save_current_answer()
            self.current_question_index += 1
            self.follow_up_count = 0
            self.current_candidate_transcript = ""

            if self.current_question_index < len(self.questions):
                await self.send_json({
                    "type": "next_question",
                    "question_index": self.current_question_index,
                })
                await self._speak_text(response_text, question_index=self.current_question_index)
            else:
                # All questions done — cancel TTS and run evaluation directly
                # Don't speak wrap-up text to avoid audio leaking into evaluation screen
                await self._cancel_tts()
                await self._run_evaluation()

        elif action == "follow_up":
            self.follow_up_count += 1
            self.current_candidate_transcript = ""  # Reset for the follow-up answer
            await self._speak_text(response_text, question_index=self.current_question_index)

        elif action == "wrap_up":
            self._save_current_answer()
            await self._cancel_tts()
            await self._run_evaluation()

    def _save_current_answer(self, passed: bool = False):
        """Save the current question's answer to qa_pairs."""
        if self.current_question_index < len(self.questions):
            q = self.questions[self.current_question_index]
            self.qa_pairs.append({
                "question": q.get("question", ""),
                "topic": q.get("topic", ""),
                "answer": "(Pas geçildi)" if passed else (self.current_candidate_transcript.strip() or "(Cevap verilmedi)"),
            })

    # ─── Cartesia TTS ────────────────────────────────────────────────

    async def _connect_tts(self):
        """Open WebSocket connection to Cartesia TTS (Sonic-3)."""
        headers = {
            "X-API-Key": CARTESIA_API_KEY,
            "Cartesia-Version": CARTESIA_VERSION,
        }

        try:
            self._tts_ws = await websockets.connect(CARTESIA_TTS_URL, additional_headers=headers)
            self._tts_listener_task = asyncio.create_task(self._tts_listener())
            print("[TTS] Connected to Cartesia Sonic-3")
        except Exception as e:
            print(f"[TTS] Connection error: {e}")
            await self.send_json({"type": "error", "message": f"TTS bağlantı hatası: {str(e)}"})

    async def _tts_listener(self):
        """Listen for TTS audio chunks from Cartesia and forward to frontend."""
        try:
            async for message in self._tts_ws:
                if not self._is_running:
                    break

                # Stop forwarding audio if we're done or evaluating
                if self.state in ("evaluating", "done"):
                    continue

                try:
                    # Try to parse as JSON first
                    data = json.loads(message)
                    msg_type = data.get("type", "")

                    if msg_type == "chunk":
                        # Decode base64 audio data and send as binary
                        audio_b64 = data.get("data", "")
                        if audio_b64:
                            audio_bytes = base64.b64decode(audio_b64)
                            await self.send_binary(audio_bytes)

                    elif msg_type == "done":
                        context_id = data.get("context_id", "")
                        if context_id == self._current_tts_context_id:
                            # TTS finished speaking — switch to listening
                            if self.state == "ai_speaking":
                                self.state = "listening"
                                self.current_candidate_transcript = ""
                                await self.send_json({"type": "ai_done_speaking"})

                    elif msg_type == "error":
                        err_msg = data.get('error', 'Unknown Cartesia error')
                        err_context = data.get('context_id', '')
                        # Ignore errors for cancelled/stale contexts (expected after _cancel_tts)
                        if err_context and err_context != self._current_tts_context_id:
                            print(f"[TTS] Ignoring stale error for cancelled context {err_context}: {err_msg}")
                        else:
                            print(f"[TTS] Cartesia API Error: {err_msg}")
                            await self.send_json({"type": "error", "message": f"Ses üretim hatası (Cartesia): {err_msg}"})

                except json.JSONDecodeError:
                    # Binary message (shouldn't happen with Cartesia TTS, but handle it)
                    pass

        except websockets.exceptions.ConnectionClosed:
            print("[TTS] Connection closed")
        except Exception as e:
            print(f"[TTS] Listener error: {e}")

    async def _speak_text(self, text: str, question_index: int = 0):
        """Send text to Cartesia TTS and stream audio to frontend."""
        if not self._tts_ws or not self._is_running:
            return

        self.state = "ai_speaking"
        self._current_tts_context_id = str(uuid.uuid4())[:20]

        # Notify frontend that AI is about to speak
        await self.send_json({
            "type": "ai_speaking",
            "transcript": text,
            "question_index": question_index,
        })

        # Send TTS request
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
        except Exception as e:
            print(f"[TTS] Send error: {e}")
            self.state = "listening"
            await self.send_json({"type": "ai_done_speaking"})

    # ─── Evaluation ──────────────────────────────────────────────────

    async def _run_evaluation(self):
        """Run final evaluation using existing ai_evaluator."""
        # Cancel any active TTS before evaluating
        await self._cancel_tts()

        if not self.qa_pairs:
            self.last_evaluation = {
                "results": [],
                "overall_score": 0,
                "overall_feedback": "Değerlendirilecek cevap bulunamadı.",
            }
            await self.send_json({
                "type": "evaluation",
                **self.last_evaluation,
            })
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

        # Store for DB persistence
        self.last_evaluation = evaluation

        await self.send_json({
            "type": "evaluation",
            "results": evaluation.get("results", []),
            "overall_score": evaluation.get("overall_score", 0),
            "overall_feedback": evaluation.get("overall_feedback", ""),
        })

        await self.send_json({"type": "session_complete"})
        self.state = "done"
