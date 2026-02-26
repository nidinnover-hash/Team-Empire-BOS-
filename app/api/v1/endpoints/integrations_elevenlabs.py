import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.endpoints._integration_helpers import (
    CONNECT_EXCEPTIONS,
    audit_connect_success,
    audit_sync,
    handle_connect_error,
)
from app.core.deps import get_db
from app.core.rbac import require_roles
from app.schemas.integration import (
    ElevenLabsConnectRequest,
    ElevenLabsStatusRead,
    ElevenLabsTTSRequest,
    ElevenLabsTTSResult,
)
from app.services import elevenlabs_service

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Integrations"])


@router.post("/elevenlabs/connect", response_model=ElevenLabsStatusRead, status_code=201)
async def elevenlabs_connect(
    data: ElevenLabsConnectRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> ElevenLabsStatusRead:
    try:
        info = await elevenlabs_service.connect_elevenlabs(
            db, org_id=int(actor["org_id"]), api_key=data.api_key,
        )
    except CONNECT_EXCEPTIONS as exc:
        await handle_connect_error(db, integration_type="elevenlabs", actor=actor, exc=exc)
    await audit_connect_success(db, integration_type="elevenlabs", actor=actor, entity_id=info["id"])
    return ElevenLabsStatusRead(connected=True)


@router.get("/elevenlabs/status", response_model=ElevenLabsStatusRead)
async def elevenlabs_status(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> ElevenLabsStatusRead:
    status = await elevenlabs_service.get_elevenlabs_status(db, org_id=int(actor["org_id"]))
    return ElevenLabsStatusRead(**status)


@router.post("/elevenlabs/tts", response_model=ElevenLabsTTSResult)
async def elevenlabs_tts(
    data: ElevenLabsTTSRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> ElevenLabsTTSResult:
    try:
        result = await elevenlabs_service.text_to_speech(
            db, org_id=int(actor["org_id"]), text=data.text, voice_id=data.voice_id,
        )
    except ValueError as exc:
        logger.warning("elevenlabs tts failed: %s", exc)
        raise HTTPException(status_code=400, detail="TTS failed. Check connection and try again.") from exc
    await audit_sync(
        db, event_type="elevenlabs_tts", actor=actor,
        payload={"voice_id": result["voice_id"], "size": result["audio_size_bytes"]},
    )
    return ElevenLabsTTSResult(
        audio_size_bytes=result["audio_size_bytes"],
        voice_id=result["voice_id"],
        model=result["model"],
    )
