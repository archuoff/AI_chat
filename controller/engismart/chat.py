"""Chat: every role; the data a role may see is limited inside the search (access_filters)."""
from __future__ import annotations

import json
import logging
import time

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from controller.engismart.access import Principal, access_filters
from controller.engismart.graphs.chat_graph import (
    config_for,
    delete_session,
    get_chat_graph,
    history_of,
    result_of,
    rewind_session,
    run_chat,
    turn_input,
)
from controller.engismart.helper import checked_images, public_result, record_turn, run_endpoint, thread_id
from controller.engismart.llm import warm_connections
from controller.engismart.rag import vision
from controller.engismart.validator import ChatRequest, RewindRequest

log = logging.getLogger(__name__)
router = APIRouter()


def _ms(started: float) -> int:
    return round((time.perf_counter() - started) * 1000)


@router.post("/warmup")
async def warmup(request: Request):
    """Called by the UI while the user types: pre-opens the Azure connections (see llm.warm_connections)."""
    return await run_endpoint(request, lambda p: {"started": warm_connections()}, what="/warmup")


@router.post("/chat")
async def chat(request: Request):
    def work(p: Principal, req: ChatRequest):
        started = time.perf_counter()
        res = run_chat(thread_id(p, req.session_id), req.message, access_filters(p, req.filters), checked_images(req.images))
        record_turn(p, req.session_id, res, _ms(started))
        return public_result(p, req.session_id, res)

    return await run_endpoint(request, work, body=ChatRequest, what="/chat")


@router.post("/chat/stream")
async def chat_stream(request: Request):
    """Server-sent events: status / token / reset / final / error  (each line: `data: {json}`).
    Not wrapped in the JSON envelope: it is a stream. Call it with fetch() and the `access-token` header."""
    def work(p: Principal, req: ChatRequest):
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
                record_turn(p, req.session_id, res, _ms(started))
                yield f"data: {json.dumps({'type': 'final', **public_result(p, req.session_id, res)}, default=str)}\n\n"
            except Exception as e:  # noqa: BLE001 - report to the client instead of dropping the stream
                log.exception("chat stream failed")
                yield f"data: {json.dumps({'type': 'error', 'message': f'{type(e).__name__}: {e}'})}\n\n"
            finally:
                vision.release(ref)  # images are used for this question only

        return StreamingResponse(events(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    return await run_endpoint(request, work, body=ChatRequest, what="/chat/stream")


@router.get("/chat/{session_id}/messages")
async def chat_messages(session_id: str, request: Request):
    return await run_endpoint(request, lambda p: history_of(thread_id(p, session_id)), what="/chat/messages")


@router.post("/chat/{session_id}/rewind")
async def chat_rewind(session_id: str, request: Request):
    """Edit and send: the conversation memory goes back to just after turn N, so the edited question is answered without the later turns."""
    def work(p: Principal, req: RewindRequest):
        return {"kept_messages": rewind_session(thread_id(p, session_id), req.turns)}

    return await run_endpoint(request, work, body=RewindRequest, what="/chat/rewind")


@router.delete("/chat/{session_id}")
async def chat_delete(session_id: str, request: Request):
    def work(p: Principal):
        delete_session(thread_id(p, session_id))
        return {"deleted": session_id}

    return await run_endpoint(request, work, what="/chat/delete")
