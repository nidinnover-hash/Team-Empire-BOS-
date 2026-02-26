from __future__ import annotations

import re
from collections import Counter

from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.data_collection import (
    MeetingCoachingRequest,
    MeetingCoachingResult,
)
from app.schemas.note import NoteCreate
from app.services import memory as memory_service
from app.services import note as note_service
from app.services.data_collection._shared import (
    _CLOSE_WORDS,
    _EMPATHY_WORDS,
    _FILLER_WORDS,
    _MAX_PRO_ITEM_CHARS,
    _OBJECTION_WORDS,
)


def _coaching_sentences(transcript: str) -> list[str]:
    clean = re.sub(r"\s+", " ", transcript or "").strip()
    if not clean:
        return []
    parts = re.split(r"(?<=[.!?])\s+", clean)
    return [p.strip() for p in parts if p.strip()]


async def analyze_meeting_transcript(
    db: AsyncSession,
    org_id: int,
    data: MeetingCoachingRequest,
) -> MeetingCoachingResult:
    if not data.consent_confirmed:
        raise ValueError("consent_confirmed must be true before processing real conversations")

    text = (data.transcript or "").strip()
    if not text:
        raise ValueError("transcript is required")

    lowered = text.lower()
    words = re.findall(r"[a-zA-Z']+", lowered)
    word_count = len(words)
    question_count = text.count("?")
    filler_count = sum(1 for w in words if w in _FILLER_WORDS)
    empathy_count = sum(1 for w in words if w in _EMPATHY_WORDS)
    close_hits = sum(lowered.count(token) for token in _CLOSE_WORDS)
    objection_hits = sum(lowered.count(token) for token in _OBJECTION_WORDS)
    sentence_count = max(1, len(_coaching_sentences(text)))
    avg_sentence_words = round(word_count / sentence_count, 1)

    strengths: list[str] = []
    improvements: list[str] = []
    if question_count >= 4:
        strengths.append("Strong discovery questioning pattern.")
    else:
        improvements.append("Ask more discovery questions to understand customer needs earlier.")
    if empathy_count >= 2:
        strengths.append("Good empathy language and support framing.")
    else:
        improvements.append("Add empathy phrases before pitching solutions.")
    if close_hits >= 2:
        strengths.append("Conversation includes clear next-step or closing intent.")
    else:
        improvements.append("End with one clear next step and decision checkpoint.")
    if avg_sentence_words <= 22:
        strengths.append("Messaging is concise and easy to follow.")
    else:
        improvements.append("Reduce sentence length for clearer delivery in live calls.")
    if filler_count > 8:
        improvements.append("Reduce filler words for stronger executive presence.")

    tone_profile = "consultative"
    if empathy_count <= 1 and question_count <= 2:
        tone_profile = "pitch-heavy"
    elif empathy_count >= 3 and question_count >= 4:
        tone_profile = "advisor-led"

    common_terms = Counter([w for w in words if len(w) >= 5]).most_common(3)
    top_term_str = ", ".join(t for t, _ in common_terms) if common_terms else "none"

    memory_keys: list[str] = []
    for key, value in [
        ("sales.talk.tone_profile", tone_profile),
        ("sales.talk.discovery_questions", str(question_count)),
        ("sales.talk.next_step_focus", str(close_hits)),
    ]:
        await memory_service.upsert_profile_memory(
            db=db,
            organization_id=org_id,
            key=key,
            value=value[:_MAX_PRO_ITEM_CHARS],
            category="learned",
        )
        memory_keys.append(key)

    coach_note = await note_service.create_note(
        db=db,
        organization_id=org_id,
        data=NoteCreate(
            title=f"Meeting Coaching - {(data.speaker_name or 'Speaker').strip()[:60]}",
            content=(
                f"Objective: {data.objective}\n"
                f"Tone Profile: {tone_profile}\n"
                f"Word Count: {word_count}\n"
                f"Questions: {question_count}\n"
                f"Filler Words: {filler_count}\n"
                f"Top Terms: {top_term_str}\n"
                f"Strengths: {' | '.join(strengths[:4]) or 'n/a'}\n"
                f"Improvements: {' | '.join(improvements[:5]) or 'n/a'}"
            ),
            tags="meeting,conversation,coaching,sales",
        ),
    )

    return MeetingCoachingResult(
        objective=data.objective,
        tone_profile=tone_profile,
        strengths=strengths[:5],
        improvement_areas=improvements[:6],
        sales_signals={
            "question_count": question_count,
            "empathy_count": empathy_count,
            "close_signal_count": close_hits,
            "objection_signal_count": objection_hits,
            "filler_count": filler_count,
        },
        memory_keys=memory_keys,
        note_id=coach_note.id,
        message=(
            "Conversation coaching generated. Transcript converted into clone-ready "
            "talk and sales improvement signals."
        ),
    )
