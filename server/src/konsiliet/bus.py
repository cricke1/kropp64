"""Händelsebuss. Allt som händer sparas i events-tabellen och skickas live till appen och webben.

Händelsetyper (payload-fält inom parentes) som klienterna förstår:

  sample.live      (metric, ts, value)                 senaste värde, för live-mätare
  vakt.anomaly     (metric, z, window, detail)          vakten hittade något
  consult.start    (consult_id, trigger, members)       konsiliet kallas in
  agent.move       (consult_id, agent, to)              agenten går till en plats i kontoret
  agent.think      (consult_id, agent)                  agenten tänker (visa "...")
  agent.tool       (consult_id, agent, tool, args)      agenten slår upp något
  agent.say        (consult_id, agent, to, text, cites) agenten säger något, med källor
  agent.handoff    (consult_id, agent, to, item)        agenten räcker över ett dokument
  review.strike    (consult_id, claim, reason)          granskaren stryker ett påstående
  consult.verdict  (consult_id, verdict)                slutbedömning
  alert.raise      (level, title, body)                 larm till mobilen
  sync.1177        (status, ...)                        journalhämtning: loggar_in, qr (png base64, kvar),
                                                        bankid_lank (url), inloggad, hamtar, klar, misslyckades
  nudge.move       (title, body)                        stillasittandevakten
  brief.morgon     (datum, text, fakta)                 morgonbrief med återhämtningspoäng
"""
from __future__ import annotations

import asyncio
from typing import Any

from . import db


class Bus:
    def __init__(self) -> None:
        self._subs: set[asyncio.Queue[dict[str, Any]]] = set()
        self._loop: asyncio.AbstractEventLoop | None = None

    def bind(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def subscribe(self) -> asyncio.Queue[dict[str, Any]]:
        q: asyncio.Queue[dict[str, Any]] = asyncio.Queue(maxsize=1000)
        self._subs.add(q)
        return q

    def unsubscribe(self, q: asyncio.Queue[dict[str, Any]]) -> None:
        self._subs.discard(q)

    def publish(self, kind: str, payload: dict[str, Any], persist: bool = True) -> dict[str, Any]:
        """Trådsäker. Kan anropas från agenttrådar."""
        ev = db.add_event(kind, payload) if persist else {"id": None, "ts": None, "kind": kind, "payload": payload}
        if self._loop is not None:
            self._loop.call_soon_threadsafe(self._fanout, ev)
        return ev

    def _fanout(self, ev: dict[str, Any]) -> None:
        for q in list(self._subs):
            try:
                q.put_nowait(ev)
            except asyncio.QueueFull:
                pass  # långsam klient tappar händelser hellre än att stoppa systemet


bus = Bus()
