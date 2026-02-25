from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.deps import get_db
from app.core.rbac import require_roles
from app.logs.audit import record_action
from app.schemas.data_collection import (
    BrandingPowerReport,
    CloneProTrainingRequest,
    CloneProTrainingResult,
    DataCollectRequest,
    DataCollectResult,
    EthicalBoundaryReport,
    FraudDetectionResult,
    FraudLayerReport,
    MediaEditingLayerReport,
    MediaProjectCreate,
    MediaProjectOut,
    MobileCaptureAnalyzeRequest,
    MobileCaptureAnalyzeResult,
    MobileCaptureUploadAnalyzeResult,
    MeetingCoachingRequest,
    MeetingCoachingResult,
    NewsDigestRequest,
    NewsDigestResult,
    PhotoCharacterStudyResult,
    SocialManagementLayerReport,
    ThreatDetectionResult,
    ThreatLayerReport,
    ThreatTrainRequest,
    ThreatTrainResult,
)
from app.services import data_collection as data_collection_service

router = APIRouter(prefix="/data", tags=["Data Collection"])


@router.post("/collect", response_model=DataCollectResult)
async def collect_data(
    data: DataCollectRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> DataCollectResult:
    org_id = int(actor["org_id"])
    try:
        result = await data_collection_service.ingest_data(
            db=db,
            org_id=org_id,
            data=data,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await record_action(
        db=db,
        event_type="data_collected",
        actor_user_id=int(actor["id"]),
        organization_id=org_id,
        entity_type="data_ingest",
        entity_id=result.created_ids[0] if result.created_ids else None,
        payload_json={
            "source": data.source,
            "target": data.target,
            "count": result.ingested_count,
        },
    )
    return result


@router.post("/train-pro", response_model=CloneProTrainingResult)
async def train_clone_pro(
    data: CloneProTrainingRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> CloneProTrainingResult:
    org_id = int(actor["org_id"])
    try:
        result = await data_collection_service.train_clone_pro(
            db=db,
            org_id=org_id,
            data=data,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await record_action(
        db=db,
        event_type="clone_trained_pro",
        actor_user_id=int(actor["id"]),
        organization_id=org_id,
        entity_type="training",
        entity_id=None,
        payload_json={
            "source": data.source,
            "profile_memory_written": result.profile_memory_written,
            "daily_context_written": result.daily_context_written,
            "notes_written": result.notes_written,
        },
    )
    return result


@router.post("/meeting-coach", response_model=MeetingCoachingResult)
async def meeting_coach(
    data: MeetingCoachingRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> MeetingCoachingResult:
    org_id = int(actor["org_id"])
    try:
        result = await data_collection_service.analyze_meeting_transcript(
            db=db,
            org_id=org_id,
            data=data,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await record_action(
        db=db,
        event_type="meeting_coached",
        actor_user_id=int(actor["id"]),
        organization_id=org_id,
        entity_type="training",
        entity_id=result.note_id,
        payload_json={
            "objective": data.objective,
            "tone_profile": result.tone_profile,
            "consent_confirmed": bool(data.consent_confirmed),
        },
    )
    return result


@router.post("/mobile-capture/analyze", response_model=MobileCaptureAnalyzeResult)
async def mobile_capture_analyze(
    data: MobileCaptureAnalyzeRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> MobileCaptureAnalyzeResult:
    org_id = int(actor["org_id"])
    try:
        result = await data_collection_service.analyze_mobile_capture(
            db=db,
            org_id=org_id,
            data=data,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await record_action(
        db=db,
        event_type="mobile_capture_analyzed",
        actor_user_id=int(actor["id"]),
        organization_id=org_id,
        entity_type="training",
        entity_id=result.note_id,
        payload_json={
            "source": data.source,
            "device_type": data.device_type,
            "capture_type": data.capture_type,
            "wanted_count": result.wanted_count,
            "unwanted_count": result.unwanted_count,
            "policy_draft_count": len(result.policy_rule_ids),
        },
    )
    return result


@router.post("/mobile-capture/upload-analyze", response_model=MobileCaptureUploadAnalyzeResult)
async def mobile_capture_upload_analyze(
    file: UploadFile = File(...),
    source: str = Form("mobile_capture_upload"),
    device_type: str = Form("mobile"),
    capture_type: str = Form("screenshot"),
    wanted_topics: str = Form(""),
    unwanted_topics: str = Form(""),
    create_policy_drafts: bool = Form(True),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> MobileCaptureUploadAnalyzeResult:
    org_id = int(actor["org_id"])
    file_bytes = await file.read()
    if len(file_bytes) > 8 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 8MB)")
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    try:
        extracted_text, ocr_engine = data_collection_service.extract_text_from_image_bytes(file_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail="Failed to extract text from image") from exc

    try:
        result = await data_collection_service.analyze_mobile_capture(
            db=db,
            org_id=org_id,
            data=MobileCaptureAnalyzeRequest(
                source=source,
                device_type="tablet" if device_type.strip().lower() == "tablet" else "mobile",
                capture_type="photo" if capture_type.strip().lower() == "photo" else "screenshot",
                content_text=extracted_text,
                wanted_topics=data_collection_service.parse_topic_tokens(wanted_topics),
                unwanted_topics=data_collection_service.parse_topic_tokens(unwanted_topics),
                create_policy_drafts=bool(create_policy_drafts),
            ),
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await record_action(
        db=db,
        event_type="mobile_capture_uploaded_and_analyzed",
        actor_user_id=int(actor["id"]),
        organization_id=org_id,
        entity_type="training",
        entity_id=result.note_id,
        payload_json={
            "source": source,
            "filename": file.filename or "unknown",
            "device_type": device_type,
            "capture_type": capture_type,
            "wanted_count": result.wanted_count,
            "unwanted_count": result.unwanted_count,
            "policy_draft_count": len(result.policy_rule_ids),
            "ocr_engine": ocr_engine,
        },
    )
    return MobileCaptureUploadAnalyzeResult(
        **result.model_dump(),
        filename=file.filename or "unknown",
        extracted_chars=len(extracted_text),
        ocr_engine=ocr_engine,
    )


@router.post("/photo-character/upload-analyze", response_model=PhotoCharacterStudyResult)
async def photo_character_upload_analyze(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> PhotoCharacterStudyResult:
    org_id = int(actor["org_id"])
    file_bytes = await file.read()
    if len(file_bytes) > 8 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="File too large (max 8MB)")
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    try:
        extracted_text, ocr_engine = data_collection_service.extract_text_from_image_bytes(file_bytes)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=400, detail="Failed to extract text from image") from exc

    try:
        result = await data_collection_service.analyze_photo_character(
            db=db,
            org_id=org_id,
            extracted_text=extracted_text,
            ocr_engine=ocr_engine,
            filename=file.filename or "unknown",
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await record_action(
        db=db,
        event_type="photo_character_analyzed",
        actor_user_id=int(actor["id"]),
        organization_id=org_id,
        entity_type="training",
        entity_id=result.note_id,
        payload_json={
            "filename": file.filename or "unknown",
            "traits": result.traits[:5],
            "confidence": result.confidence,
            "ocr_engine": ocr_engine,
        },
    )
    return result


@router.post("/threats/detect", response_model=ThreatDetectionResult)
async def detect_threats(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> ThreatDetectionResult:
    org_id = int(actor["org_id"])
    result = await data_collection_service.detect_threats(db=db, org_id=org_id)

    await record_action(
        db=db,
        event_type="threat_detection_scan",
        actor_user_id=int(actor["id"]),
        organization_id=org_id,
        entity_type="security",
        entity_id=None,
        payload_json={
            "scope": result.scope,
            "signals_found": result.signals_found,
            "severity_breakdown": result.severity_breakdown,
            "policy_drafts_created": result.policy_drafts_created,
        },
    )
    return result


@router.post("/threats/train", response_model=ThreatTrainResult)
async def train_threats(
    data: ThreatTrainRequest,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> ThreatTrainResult:
    org_id = int(actor["org_id"])
    try:
        result = await data_collection_service.train_threat_signals(
            db=db,
            org_id=org_id,
            data=data,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await record_action(
        db=db,
        event_type="threat_training",
        actor_user_id=int(actor["id"]),
        organization_id=org_id,
        entity_type="security",
        entity_id=None,
        payload_json={
            "action": data.action,
            "processed": result.processed,
            "policies_activated": result.policies_activated,
            "policies_dismissed": result.policies_dismissed,
        },
    )
    return result


@router.get("/threats/layer", response_model=ThreatLayerReport)
async def threat_layer(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> ThreatLayerReport:
    org_id = int(actor["org_id"])
    return await data_collection_service.get_threat_layer_report(db=db, org_id=org_id)


@router.get("/branding/power", response_model=BrandingPowerReport)
async def branding_power(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> BrandingPowerReport:
    org_id = int(actor["org_id"])
    return await data_collection_service.get_branding_power_report(db=db, org_id=org_id)


@router.post("/fraud/detect", response_model=FraudDetectionResult)
async def detect_fraud(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN")),
) -> FraudDetectionResult:
    org_id = int(actor["org_id"])
    result = await data_collection_service.detect_fraud(db=db, org_id=org_id)

    await record_action(
        db=db,
        event_type="fraud_detection_scan",
        actor_user_id=int(actor["id"]),
        organization_id=org_id,
        entity_type="security",
        entity_id=None,
        payload_json={
            "scope": result.scope,
            "signals_found": result.signals_found,
            "total_anomalies": result.total_anomalies,
        },
    )
    return result


@router.get("/fraud/layer", response_model=FraudLayerReport)
async def fraud_layer(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> FraudLayerReport:
    org_id = int(actor["org_id"])
    return await data_collection_service.get_fraud_layer_report(db=db, org_id=org_id)


@router.post("/news/digest", response_model=NewsDigestResult)
async def news_digest(
    data: NewsDigestRequest = NewsDigestRequest(),
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> NewsDigestResult:
    org_id = int(actor["org_id"])
    result = await data_collection_service.generate_news_digest(
        db=db, org_id=org_id, data=data,
    )

    await record_action(
        db=db,
        event_type="news_digest_generated",
        actor_user_id=int(actor["id"]),
        organization_id=org_id,
        entity_type="intelligence",
        entity_id=None,
        payload_json={
            "items_count": len(result.items),
            "interests_matched": result.interests_matched,
        },
    )
    return result


@router.get("/ethics/boundary", response_model=EthicalBoundaryReport)
async def ethical_boundary(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> EthicalBoundaryReport:
    org_id = int(actor["org_id"])
    return await data_collection_service.get_ethical_boundary_report(db=db, org_id=org_id)


@router.post("/media/projects", response_model=MediaProjectOut, status_code=201)
async def create_media_project(
    data: MediaProjectCreate,
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> MediaProjectOut:
    org_id = int(actor["org_id"])
    result = await data_collection_service.create_media_project(
        db=db, org_id=org_id, data=data, actor_user_id=int(actor["id"]),
    )

    await record_action(
        db=db,
        event_type="media_project_created",
        actor_user_id=int(actor["id"]),
        organization_id=org_id,
        entity_type="media_project",
        entity_id=result.id,
        payload_json={
            "title": data.title,
            "media_type": data.media_type,
            "platform": data.platform,
            "quality_score": result.quality_score,
        },
    )
    return result


@router.get("/media/layer", response_model=MediaEditingLayerReport)
async def media_editing_layer(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> MediaEditingLayerReport:
    org_id = int(actor["org_id"])
    return await data_collection_service.get_media_editing_layer(db=db, org_id=org_id)


@router.get("/social/management-layer", response_model=SocialManagementLayerReport)
async def social_management_layer(
    db: AsyncSession = Depends(get_db),
    actor: dict = Depends(require_roles("CEO", "ADMIN", "MANAGER")),
) -> SocialManagementLayerReport:
    org_id = int(actor["org_id"])
    return await data_collection_service.get_social_management_layer(db=db, org_id=org_id)
