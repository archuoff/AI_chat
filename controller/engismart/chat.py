"""Chat: every role; the data a role may see is limited inside the search (access_filters)."""
from __future__ import annotations

import json
import logging
import re
import time

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse

from controller.engismart.envelope import EnvelopeRoute
from controller.engismart.helper import checked_images, public_result, record_turn, thread_id
from controller.engismart.validator import ChatRequest, RewindRequest
from services.engismart.access import Principal, access_filters, current_user
from services.engismart.graphs.chat_graph import (
    config_for,
    delete_session,
    get_chat_graph,
    history_of,
    result_of,
    rewind_session,
    run_chat,
    turn_input,
)
from services.engismart.llm import warm_connections
from services.engismart.rag import vision

log = logging.getLogger(__name__)
router = APIRouter(route_class=EnvelopeRoute)
_NOT_FOUND_RE = re.compile(r"\s*I couldn.t find", re.I)  # offline + LLM wording of "not in the documents"


def _found(res: dict) -> bool:
    return not _NOT_FOUND_RE.match(res.get("answer") or "")


@router.post("/warmup")
def warmup(_: Principal = Depends(current_user)):
    """Called by the UI while the user types: pre-opens the Azure connections (see llm.warm_connections)."""
    return {"started": warm_connections()}


@router.post("/chat")
def chat(req: ChatRequest, p: Principal = Depends(current_user)):
    started = time.perf_counter()
    res = run_chat(thread_id(p, req.session_id), req.message, access_filters(p, req.filters), checked_images(req.images))
    record_turn(p, req.session_id, req.message, res, started, _found(res))
    return public_result(p, req.session_id, res)


@router.post("/chat/stream")
def chat_stream(req: ChatRequest, p: Principal = Depends(current_user)):
    """Server-sent events: status / token / reset / final / error  (each line: `data: {json}`).
    Not wrapped in the JSON envelope: it is a stream. Call it with fetch() and the `access-token` header."""
    thread = thread_id(p, req.session_id)
    filters = access_filters(p, req.filters)
    images = checked_images(req.images)

    def events():
        started = time.perf_counter()
        graph = get_chat_graph()
        ref = vision.hold(images)
        try:
            for mode, chunk in graph.stream(turn_input(req.message, filters, ref), config_for(thread),
                                            stream_mode=["custom", "updates"]):
                if mode == "custom":
                    yield f"data: {json.dumps(chunk)}\n\n"
            res = result_of(thread)
            record_turn(p, req.session_id, req.message, res, started, _found(res))
            yield f"data: {json.dumps({'type': 'final', **public_result(p, req.session_id, res)}, default=str)}\n\n"
        except Exception as e:  # noqa: BLE001 - report to the client instead of dropping the stream
            log.exception("chat stream failed")
            yield f"data: {json.dumps({'type': 'error', 'message': f'{type(e).__name__}: {e}'})}\n\n"
        finally:
            vision.release(ref)  # images are used for this question only

    return StreamingResponse(events(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@router.get("/chat/{session_id}/messages")
def chat_messages(session_id: str, p: Principal = Depends(current_user)):
    return history_of(thread_id(p, session_id))


@router.post("/chat/{session_id}/rewind")
def chat_rewind(session_id: str, req: RewindRequest, p: Principal = Depends(current_user)):
    """Edit and send: the conversation memory goes back to just after turn N, so the edited question is answered without the later turns."""
    return {"kept_messages": rewind_session(thread_id(p, session_id), req.turns)}


@router.delete("/chat/{session_id}")
def chat_delete(session_id: str, p: Principal = Depends(current_user)):
    delete_session(thread_id(p, session_id))
    return {"deleted": session_id}
