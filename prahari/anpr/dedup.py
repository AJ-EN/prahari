"""
PlateDeduper: one vehicle, many frames -> one PlateEvent.

A car crossing a camera is sampled in 3-20 consecutive frames. Every frame
produces a PlateEvent, often with slightly different reads (GJ01AB1234,
GJ01A81234, GJ01AB1234 ...). Downstream wants one sighting per pass.

Grouping rule (per camera, per epoch):
  * an event joins an open cluster when its plate (grammar-corrected if
    available, else raw) is within `max_distance` of the cluster's current
    best plate under `plate_grammar.confusion_distance`, AND its ts is
    within `window_s` of the cluster's last-seen ts;
  * the cluster keeps the highest-quality read, where quality prefers a
    grammar-valid read, then ocr_conf * det_conf;
  * a cluster closes when no matching read arrives for `window_s` seconds
    (by FrameSample.ts, never wall-clock), on epoch change, or on flush().

Emission modes:
  "best"  (default) emit each cluster's best read when the cluster closes.
          One event per pass, the best one, at the cost of ~window_s latency.
  "first" emit the first read of a cluster immediately and suppress the rest.
          Lowest latency for live watchlist alerts; the emitted read may not
          be the best.

Epoch change (camera reconnect / timestamp discontinuity) closes every open
cluster for that camera, emitting pending bests in "best" mode, then resets.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from prahari.common.contracts import PlateEvent
from prahari.common.plate_grammar import confusion_distance


def _key(ev: PlateEvent) -> str:
    return ev.plate or ev.raw_text


def read_quality(ev: PlateEvent) -> tuple[int, float]:
    return (1 if ev.plate else 0, ev.ocr_conf * ev.det_conf)


@dataclass
class _Cluster:
    best: PlateEvent
    last_ts: float
    count: int = 1
    emitted: bool = False


@dataclass
class _CamState:
    epoch: int
    clusters: list[_Cluster] = field(default_factory=list)


class PlateDeduper:
    def __init__(self, window_s: float = 8.0, max_distance: float = 1.0, mode: str = "best"):
        if mode not in ("best", "first"):
            raise ValueError("mode must be 'best' or 'first'")
        self.window_s = window_s
        self.max_distance = max_distance
        self.mode = mode
        self._cams: dict[str, _CamState] = {}

    def push(self, ev: PlateEvent, epoch: int) -> list[PlateEvent]:
        """Offer one event. Returns the events that should be emitted now
        (possibly empty, possibly several closed clusters)."""
        out: list[PlateEvent] = []
        st = self._cams.get(ev.camera_id)
        if st is None or st.epoch != epoch:
            if st is not None:
                out.extend(self._close_all(st))
            st = self._cams[ev.camera_id] = _CamState(epoch)

        out.extend(self._expire(st, ev.ts))

        key = _key(ev)
        match: _Cluster | None = None
        best_d = None
        if key:
            for c in st.clusters:
                d = confusion_distance(key, _key(c.best))
                if d <= self.max_distance and (best_d is None or d < best_d):
                    match, best_d = c, d
        if match is None:
            c = _Cluster(best=ev, last_ts=ev.ts)
            st.clusters.append(c)
            if self.mode == "first":
                c.emitted = True
                out.append(ev)
        else:
            match.count += 1
            match.last_ts = max(match.last_ts, ev.ts)
            if read_quality(ev) > read_quality(match.best):
                match.best = ev
        return out

    def push_many(self, events: list[PlateEvent], epoch: int) -> list[PlateEvent]:
        out: list[PlateEvent] = []
        for ev in events:
            out.extend(self.push(ev, epoch))
        return out

    def tick(self, camera_id: str, now_ts: float) -> list[PlateEvent]:
        """Close clusters that have gone quiet, e.g. on a frame with no plates."""
        st = self._cams.get(camera_id)
        return self._expire(st, now_ts) if st else []

    def flush(self, camera_id: str | None = None) -> list[PlateEvent]:
        out: list[PlateEvent] = []
        for cam in ([camera_id] if camera_id else list(self._cams)):
            st = self._cams.get(cam)
            if st:
                out.extend(self._close_all(st))
        return out

    def open_clusters(self, camera_id: str) -> int:
        st = self._cams.get(camera_id)
        return len(st.clusters) if st else 0

    # ------------------------------------------------------------------

    def _expire(self, st: _CamState, now_ts: float) -> list[PlateEvent]:
        out, keep = [], []
        for c in st.clusters:
            if abs(now_ts - c.last_ts) > self.window_s:
                if self.mode == "best" and not c.emitted:
                    out.append(c.best)
            else:
                keep.append(c)
        st.clusters = keep
        return out

    def _close_all(self, st: _CamState) -> list[PlateEvent]:
        out = [c.best for c in st.clusters if self.mode == "best" and not c.emitted]
        st.clusters = []
        return out
