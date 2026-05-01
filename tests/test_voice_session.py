import asyncio
import os
import sys
import types


os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")

project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if project_root not in sys.path:
    sys.path.append(project_root)

ai_conversation = types.ModuleType("utils.ai_conversation")
ai_conversation.generate_intro_text = lambda *args, **kwargs: ""
ai_conversation.generate_interviewer_response = lambda *args, **kwargs: {}
ai_conversation.generate_turkish_questions = lambda *args, **kwargs: []
sys.modules["utils.ai_conversation"] = ai_conversation

ai_evaluator = types.ModuleType("utils.ai_evaluator")
ai_evaluator.evaluate_interview = lambda *args, **kwargs: {}
sys.modules["utils.ai_evaluator"] = ai_evaluator

liveavatar_client = types.ModuleType("utils.liveavatar_client")


class LiveAvatarClient:
    async def keep_alive(self, *args, **kwargs):
        return {}

    async def stop_session(self, *args, **kwargs):
        return {}


liveavatar_client.LiveAvatarClient = LiveAvatarClient
sys.modules["utils.liveavatar_client"] = liveavatar_client

database = types.ModuleType("database")
database.SessionLocal = lambda: None
sys.modules["database"] = database

crud_interview = types.ModuleType("crud.interview")
crud_interview.get_interview = lambda *args, **kwargs: None
crud_interview.update_interview = lambda *args, **kwargs: None
crud_interview.update_interview_feedback = lambda *args, **kwargs: None
sys.modules["crud.interview"] = crud_interview

from utils.voice_session import VoiceInterviewSession


def build_session(output_mode: str):
    messages: list[dict] = []

    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())

    async def send_json(payload: dict):
        messages.append(payload)

    async def send_binary(_payload: bytes):
        return None

    session = VoiceInterviewSession(
        send_json=send_json,
        send_binary=send_binary,
        workspace_id=1,
        categories="Genel",
        difficulty="junior",
        interview_type="hr",
        job_description="Test job description",
        interview_id=1,
        requested_avatar_provider="liveavatar_full" if output_mode == "liveavatar" else "rpm_cartesia",
    )
    session.active_output_mode = output_mode
    session.state = "ai_speaking"
    session.active_utterance_id = "utt-1"
    session.current_candidate_transcript = "Test transcript"
    return session, messages


def test_handle_avatar_done_speaking_liveavatar_normal_turn():
    session, messages = build_session("liveavatar")

    asyncio.run(session.handle_avatar_done_speaking("utt-1"))

    assert session.active_utterance_id is None
    assert session.state == "listening"
    assert session.current_candidate_transcript == ""
    assert messages == [{"type": "ai_done_speaking"}]


def test_handle_avatar_done_speaking_liveavatar_wrap_up():
    session, messages = build_session("liveavatar")
    session._is_wrapping_up = True

    asyncio.run(session.handle_avatar_done_speaking("utt-1"))

    assert session.active_utterance_id is None
    assert session._is_wrapping_up is False
    assert session.state == "ai_speaking"
    assert session.current_candidate_transcript == "Test transcript"
    assert messages == [{"type": "ai_done_speaking", "wrap_up": True}]


def test_handle_avatar_done_speaking_browser_tts_normal_turn():
    session, messages = build_session("browser_tts")

    asyncio.run(session.handle_avatar_done_speaking("utt-1"))

    assert session.active_utterance_id is None
    assert session.state == "listening"
    assert session.current_candidate_transcript == ""
    assert messages == [{"type": "ai_done_speaking"}]


def test_handle_avatar_done_speaking_browser_tts_wrap_up():
    session, messages = build_session("browser_tts")
    session._is_wrapping_up = True

    asyncio.run(session.handle_avatar_done_speaking("utt-1"))

    assert session.active_utterance_id is None
    assert session._is_wrapping_up is False
    assert session.state == "ai_speaking"
    assert session.current_candidate_transcript == "Test transcript"
    assert messages == [{"type": "ai_done_speaking", "wrap_up": True}]


def test_handle_interrupt_ignored_during_wrap_up():
    session, messages = build_session("liveavatar")
    session._is_wrapping_up = True

    asyncio.run(session.handle_interrupt())

    assert session.active_utterance_id == "utt-1"
    assert session.state == "ai_speaking"
    assert session.current_candidate_transcript == "Test transcript"
    assert messages == []
