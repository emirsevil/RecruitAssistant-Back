import json
import os
from typing import Any, Optional

import httpx


LIVEAVATAR_API_BASE_URL = os.getenv("LIVEAVATAR_API_BASE_URL", "https://api.liveavatar.com").rstrip("/")
LIVEAVATAR_API_KEY = os.getenv("LIVEAVATAR_API_KEY", "")
LIVEAVATAR_AVATAR_ID = os.getenv("LIVEAVATAR_AVATAR_ID", "")
LIVEAVATAR_VOICE_ID = os.getenv("LIVEAVATAR_VOICE_ID", "")
LIVEAVATAR_LANGUAGE = os.getenv("LIVEAVATAR_LANGUAGE", "tr")
LIVEAVATAR_VIDEO_QUALITY = os.getenv("LIVEAVATAR_VIDEO_QUALITY", "high")
LIVEAVATAR_VIDEO_ENCODING = os.getenv("LIVEAVATAR_VIDEO_ENCODING", "H264")
LIVEAVATAR_MAX_SESSION_DURATION = int(os.getenv("LIVEAVATAR_MAX_SESSION_DURATION", "1200"))


class LiveAvatarConfigError(RuntimeError):
    pass


class LiveAvatarAPIError(RuntimeError):
    def __init__(self, message: str, *, status_code: int, path: str, response_body: str):
        super().__init__(message)
        self.status_code = status_code
        self.path = path
        self.response_body = response_body


def _require_config() -> None:
    missing = [
        name
        for name, value in (
            ("LIVEAVATAR_API_KEY", LIVEAVATAR_API_KEY),
            ("LIVEAVATAR_AVATAR_ID", LIVEAVATAR_AVATAR_ID),
            ("LIVEAVATAR_VOICE_ID", LIVEAVATAR_VOICE_ID),
        )
        if not value
    ]
    if missing:
        raise LiveAvatarConfigError(f"Missing LiveAvatar configuration: {', '.join(missing)}")


def _extract_data(payload: dict[str, Any]) -> dict[str, Any]:
    data = payload.get("data")
    if isinstance(data, dict):
        return data
    return payload


class LiveAvatarClient:
    def __init__(self, api_key: Optional[str] = None, base_url: Optional[str] = None):
        self.api_key = api_key or LIVEAVATAR_API_KEY
        self.base_url = (base_url or LIVEAVATAR_API_BASE_URL).rstrip("/")

    async def _request(
        self,
        method: str,
        path: str,
        *,
        json_body: Optional[dict[str, Any]] = None,
        bearer_token: Optional[str] = None,
    ) -> dict[str, Any]:
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
        }
        if bearer_token:
            headers["authorization"] = f"Bearer {bearer_token}"
        else:
            headers["X-API-KEY"] = self.api_key

        async with httpx.AsyncClient(timeout=30.0) as client:
            try:
                response = await client.request(
                    method,
                    f"{self.base_url}{path}",
                    headers=headers,
                    json=json_body,
                )
                response.raise_for_status()
            except httpx.HTTPStatusError as exc:
                response_text = exc.response.text
                error_message = f"LiveAvatar API request failed with {exc.response.status_code} on {path}"
                try:
                    error_payload = exc.response.json()
                    response_text = json.dumps(error_payload, ensure_ascii=False)
                    error_message = error_payload.get("message") or error_message
                except ValueError:
                    pass
                raise LiveAvatarAPIError(
                    error_message,
                    status_code=exc.response.status_code,
                    path=path,
                    response_body=response_text,
                ) from exc

            payload = response.json()
        return _extract_data(payload)

    async def create_session_token(self) -> dict[str, Any]:
        _require_config()
        payload = {
            "mode": "FULL",
            "avatar_id": LIVEAVATAR_AVATAR_ID,
            "avatar_persona": {
                "voice_id": LIVEAVATAR_VOICE_ID,
                "language": LIVEAVATAR_LANGUAGE,
            },
            "video_settings": {
                "quality": LIVEAVATAR_VIDEO_QUALITY,
                "encoding": LIVEAVATAR_VIDEO_ENCODING,
            },
            "max_session_duration": LIVEAVATAR_MAX_SESSION_DURATION,
        }
        data = await self._request("POST", "/v1/sessions/token", json_body=payload)
        session_token = data.get("session_token") or data.get("access_token") or data.get("token")
        session_id = data.get("session_id")
        if not session_token:
            available_keys = ", ".join(sorted(data.keys()))
            raise RuntimeError(
                "LiveAvatar session token response did not include a recognized token field. "
                f"Available keys: {available_keys or 'none'}."
            )
        return {
            "session_token": session_token,
            "session_id": session_id,
        }

    async def start_session(self, session_token: str) -> dict[str, Any]:
        data = await self._request("POST", "/v1/sessions/start", bearer_token=session_token)
        livekit_url = data.get("livekit_url")
        livekit_client_token = data.get("livekit_client_token")
        session_id = data.get("session_id")
        if not livekit_url or not livekit_client_token or not session_id:
            raise RuntimeError("LiveAvatar start response is missing required LiveKit connection fields.")
        return {
            "session_id": session_id,
            "livekit_url": livekit_url,
            "livekit_client_token": livekit_client_token,
            "max_session_duration": int(data.get("max_session_duration") or LIVEAVATAR_MAX_SESSION_DURATION),
        }

    async def keep_alive(self, session_id: str) -> dict[str, Any]:
        return await self._request("POST", "/v1/sessions/keep-alive", json_body={"session_id": session_id})

    async def stop_session(self, session_id: str, reason: str = "USER_CLOSED") -> dict[str, Any]:
        return await self._request(
            "POST",
            "/v1/sessions/stop",
            json_body={"session_id": session_id, "reason": reason},
        )
