"""Per-user usage records (questions, LLM tokens) and summaries for the Users & usage page.

The platform logs every request in tbl_chromosome_user_logs (track_module_usage); this table adds what it cannot know: tokens."""
from __future__ import annotations

from collections import defaultdict
from datetime import timedelta, timezone

from sqlalchemy import case, func, select

from .db import SessionLocal, UsageEvent, UserAccess, iso, utcnow
from .directory import user_names


def record(user_id: int, *, kind: str = "question", session_id: str = "", question: str = "",
           usage: dict | None = None, latency_ms: int = 0, mode: str = "", intent: str = "", found: bool = True) -> None:
    u = usage or {}
    with SessionLocal() as db:
        db.add(UsageEvent(user_id=user_id, kind=kind[:32], session_id=session_id[:128], question_chars=len(question),
                          input_tokens=int(u.get("input_tokens", 0)), output_tokens=int(u.get("output_tokens", 0)),
                          llm_calls=int(u.get("llm_calls", 0)), latency_ms=latency_ms, mode=(mode or "")[:32],
                          intent=(intent or "")[:32], found=found))
        db.commit()


def per_user_stats(days: int) -> dict[int, dict]:
    since = utcnow() - timedelta(days=days)
    with SessionLocal() as db:
        rows = db.execute(
            select(UsageEvent.user_id,
                   func.sum(case((UsageEvent.kind == "question", 1), else_=0)),
                   func.sum(UsageEvent.input_tokens), func.sum(UsageEvent.output_tokens),
                   func.sum(case((UsageEvent.found.is_(False), 1), else_=0)), func.avg(UsageEvent.latency_ms),
                   func.max(UsageEvent.created_at))
            .where(UsageEvent.created_at >= since).group_by(UsageEvent.user_id)).all()
    return {uid: {"questions": int(q or 0), "input_tokens": int(i or 0), "output_tokens": int(o or 0),
                  "not_found": int(nf or 0), "avg_latency_ms": int(lat or 0), "last_active": last}
            for uid, q, i, o, nf, lat, last in rows}


def known_user_ids() -> list[int]:
    """Users Engismart has seen: they asked a question or have a domain setting."""
    with SessionLocal() as db:
        used = set(db.scalars(select(UsageEvent.user_id).distinct()).all())
        configured = set(db.scalars(select(UserAccess.user_id)).all())
    return sorted(used | configured)


def summary(days: int) -> dict:
    since = utcnow() - timedelta(days=days)
    stats = per_user_stats(days)
    with SessionLocal() as db:
        events = db.execute(select(UsageEvent.created_at, UsageEvent.kind, UsageEvent.input_tokens,
                                   UsageEvent.output_tokens).where(UsageEvent.created_at >= since)).all()
    names = user_names(list(stats))
    daily: dict[str, dict] = defaultdict(lambda: {"questions": 0, "tokens": 0})
    for created, kind, i, o in events:
        day = (created if created.tzinfo is None else created.astimezone(timezone.utc)).date().isoformat()  # UTC day
        daily[day]["questions"] += kind == "question"
        daily[day]["tokens"] += (i or 0) + (o or 0)
    today = utcnow().date()
    series = [{"date": (today - timedelta(days=n)).isoformat(), **daily[(today - timedelta(days=n)).isoformat()]}
              for n in range(min(days, 30) - 1, -1, -1)]
    per_user = []
    for uid, s in sorted(stats.items(), key=lambda kv: -(kv[1]["input_tokens"] + kv[1]["output_tokens"])):
        n = names.get(uid, {})
        per_user.append({"user_id": uid, "username": n.get("username", f"#{uid}"), "display_name": n.get("display_name", ""),
                         **s, "last_active": iso(s["last_active"])})
    return {
        "days": days,
        "totals": {
            "questions": sum(s["questions"] for s in stats.values()),
            "input_tokens": sum(s["input_tokens"] for s in stats.values()),
            "output_tokens": sum(s["output_tokens"] for s in stats.values()),
            "not_found": sum(s["not_found"] for s in stats.values()),
            "active_users": sum(1 for s in stats.values() if s["questions"]),
            "users": len(known_user_ids()),
        },
        "per_user": per_user,
        "daily": series,
    }
