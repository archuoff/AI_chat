"""The conversations the users see: one row per answered question in tbl_engismart_chat_turn, with the answer and its sources.

The model's memory is kept by LangGraph (chat_graph.py). These rows are what the list of conversations and the history show, so they
come from the server and survive a browser cache clear. Every query is filtered by the owner (user_id): nobody reads another person's rows."""
from __future__ import annotations

import json
import logging
from datetime import datetime

from sqlalchemy import func

from models.model import models
from models.orm_models import ChatTurn

log = logging.getLogger(__name__)
TITLE_CHARS = 60


def _title(question: str) -> str:
    q = " ".join((question or "").split())
    return q if len(q) <= TITLE_CHARS else q[:TITLE_CHARS - 1] + "…"


def _turn(t: ChatTurn) -> dict:
    return {"turn_no": t.turn_no, "question": t.question, "answer": t.answer, "sources": json.loads(t.sources or "[]"),
            "mode": t.mode, "created_on": t.created_on.isoformat() if t.created_on else None}


def save_turn(user_id: int, session_id: str, question: str, res: dict) -> int:
    """Stores the answered question as the next turn of the conversation. Returns its number (1, 2, ...)."""
    with models() as db:
        last = db.session.query(func.max(ChatTurn.turn_no)).filter(
            ChatTurn.user_id == user_id, ChatTurn.session_id == session_id).scalar() or 0
        turn_no = last + 1
        db.session.add(ChatTurn(user_id=user_id, session_id=session_id, turn_no=turn_no, question=question,
                                answer=res.get("answer") or "", sources=json.dumps(res.get("sources") or [], default=str),
                                mode=(res.get("mode") or "")[:32], created_on=datetime.now()))
        db.session.commit()
    return turn_no


def list_sessions(user_id: int) -> list[dict]:
    """The user's conversations, most recent first. The title is the first question."""
    with models() as db:
        agg = db.session.query(ChatTurn.session_id, func.min(ChatTurn.created_on), func.max(ChatTurn.created_on),
                               func.count(ChatTurn.id)).filter(ChatTurn.user_id == user_id).group_by(ChatTurn.session_id).all()
        firsts = dict(db.session.query(ChatTurn.session_id, ChatTurn.question).filter(
            ChatTurn.user_id == user_id, ChatTurn.turn_no == 1).all())
    out = [{"session_id": s, "title": _title(firsts.get(s, "")), "turns": n,
            "started_on": a.isoformat(), "updated_on": b.isoformat()} for s, a, b, n in agg]
    return sorted(out, key=lambda x: x["updated_on"], reverse=True)


def list_turns(user_id: int, session_id: str) -> list[dict]:
    with models() as db:
        rows = db.session.query(ChatTurn).filter(
            ChatTurn.user_id == user_id, ChatTurn.session_id == session_id).order_by(ChatTurn.turn_no).all()
        return [_turn(t) for t in rows]


def delete_turns_after(user_id: int, session_id: str, turns: int) -> int:
    """Rewind: removes the turns after the first `turns` ones (the same cut as the model's memory). Returns the rows removed."""
    with models() as db:
        n = db.session.query(ChatTurn).filter(ChatTurn.user_id == user_id, ChatTurn.session_id == session_id,
                                              ChatTurn.turn_no > turns).delete(synchronize_session=False)
        db.session.commit()
    return n


def delete_session_rows(user_id: int, session_id: str) -> int:
    with models() as db:
        n = db.session.query(ChatTurn).filter(ChatTurn.user_id == user_id,
                                              ChatTurn.session_id == session_id).delete(synchronize_session=False)
        db.session.commit()
    return n
