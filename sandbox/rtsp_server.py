"""
Pure-Python stand-in for MediaMTX, for when the `mediamtx` binary is not
installed. Serves the replica clips as live, looping RTSP streams using only
PyAV (already a project dependency) and asyncio.

It reproduces the sandbox behaviours the ingest spine must survive, more
faithfully than a stock MediaMTX config does:

  * rtsp://127.0.0.1:8554/stream/<id>, H.264 or H.265 per clip, RTP over TCP
    (interleaved) ONLY. A client asking for UDP gets 461 Unsupported Transport.
  * Real-time pacing from PTS; each feed loops with a hard scene cut and PTS
    that stays monotonic across the loop (like `ffmpeg -stream_loop -1 -c copy`).
  * On PLAY the last buffered GOP is replayed as a burst, so the first 1-2 s
    arrive faster than real time (the documented gateway behaviour).
  * Each new session gets a random RTP timestamp base, so PTS restarts per
    session (a reconnect is a timing discontinuity for the client).

Optional stress switches:
  --loop-pts-reset   PTS goes backwards at the loop point (tests epoch handling)
  --join-mid-gop     replay starts mid-GOP, so H.265 decoders log the usual
                     "Could not find ref with POC" warnings until the next IDR

Usage (from repo root):
  .venv/bin/python sandbox/rtsp_server.py [--port 8554] [--loop-pts-reset] [--join-mid-gop]
Kill it and start it again to simulate a gateway outage.
"""
from __future__ import annotations

import argparse
import asyncio
import base64
import os
import random
import struct
from pathlib import Path

import av
from av.bitstream import BitStreamFilterContext

HERE = Path(__file__).resolve().parent
CLIPS = HERE / "clips"
MTU = 1400
PT = 96


def split_annexb(data: bytes) -> list[bytes]:
    out, i, n = [], 0, len(data)
    starts = []
    while i < n - 3:
        if data[i] == 0 and data[i + 1] == 0 and (data[i + 2] == 1 or (data[i + 2] == 0 and i + 3 < n and data[i + 3] == 1)):
            sc = 3 if data[i + 2] == 1 else 4
            starts.append((i, i + sc))
            i += sc
        else:
            i += 1
    for k, (_, s) in enumerate(starts):
        e = starts[k + 1][0] if k + 1 < len(starts) else n
        nal = data[s:e]
        while nal.endswith(b"\x00") and len(nal) > 1 and k + 1 < len(starts):
            nal = nal[:-1]
        if nal:
            out.append(nal)
    return out


def nal_type(codec: str, nal: bytes) -> int:
    return nal[0] & 0x1F if codec == "h264" else (nal[0] >> 1) & 0x3F


class Channel:
    """One looping clip, paced in real time, fanned out to subscribers."""

    def __init__(self, path: str, clip: Path, loop_pts_reset: bool):
        self.path, self.clip, self.loop_pts_reset = path, clip, loop_pts_reset
        self.codec = ""
        self.params: dict[int, bytes] = {}
        self.gop: list[tuple[int, list[bytes], bool]] = []   # (pts90k, nals, key)
        self.subs: dict[asyncio.Queue, asyncio.StreamWriter] = {}
        self.ready = asyncio.Event()

    def sdp(self, host: str) -> str:
        if self.codec == "h264":
            sps, pps = self.params.get(7, b""), self.params.get(8, b"")
            fmtp = (f"packetization-mode=1;profile-level-id={sps[1:4].hex()};"
                    f"sprop-parameter-sets={base64.b64encode(sps).decode()},{base64.b64encode(pps).decode()}")
            rtpmap = "H264/90000"
        else:
            b = lambda t: base64.b64encode(self.params.get(t, b"")).decode()
            fmtp = f"sprop-vps={b(32)};sprop-sps={b(33)};sprop-pps={b(34)}"
            rtpmap = "H265/90000"
        return "\r\n".join([
            "v=0", f"o=- 0 0 IN IP4 {host}", "s=stream", "c=IN IP4 0.0.0.0", "t=0 0",
            f"m=video 0 RTP/AVP {PT}", f"a=rtpmap:{PT} {rtpmap}", f"a=fmtp:{PT} {fmtp}",
            "a=control:trackID=0", ""])

    async def run(self) -> None:
        loop = asyncio.get_running_loop()
        offset90k = 0
        t0 = None           # wall time corresponding to pts90k == 0
        while True:
            c = av.open(str(self.clip))
            s = c.streams.video[0]
            self.codec = "h264" if s.codec_context.name == "h264" else "h265"
            bsf = BitStreamFilterContext(f"{'h264' if self.codec == 'h264' else 'hevc'}_mp4toannexb", s)
            tb = s.time_base
            last = 0
            for pkt in c.demux(s):
                if pkt.pts is None:
                    continue
                pts90k = offset90k + int(pkt.pts * tb * 90000)
                dts90k = offset90k + int((pkt.dts if pkt.dts is not None else pkt.pts) * tb * 90000)
                last = max(last, int(pkt.pts * tb * 90000) + int((pkt.duration or 0) * tb * 90000))
                key = bool(pkt.is_keyframe)          # read before the bsf takes the packet
                nals: list[bytes] = []
                for o in bsf.filter(pkt):
                    nals += split_annexb(bytes(o))
                if not nals:
                    continue
                if key:
                    for n in nals:
                        t = nal_type(self.codec, n)
                        if (self.codec == "h264" and t in (7, 8)) or (self.codec == "h265" and t in (32, 33, 34)):
                            self.params[t] = n
                    self.ready.set()
                    self.gop = []
                # pace by decode timestamp (send order) against wall clock
                if t0 is None:
                    t0 = loop.time() - dts90k / 90000
                delay = t0 + dts90k / 90000 - loop.time()
                if delay > 0:
                    await asyncio.sleep(delay)
                item = (pts90k, nals, key)
                self.gop.append(item)
                for q, w in list(self.subs.items()):
                    try:
                        q.put_nowait(item)
                    except asyncio.QueueFull:      # slow reader: drop it, like a real server
                        self.subs.pop(q, None)
                        w.close()
            c.close()
            if self.loop_pts_reset:
                offset90k = 0
                t0 = None
            else:
                offset90k += last


def rtp_packets(codec: str, nals: list[bytes], ts: int, seq: int, ssrc: int) -> tuple[list[bytes], int]:
    out = []
    payloads: list[bytes] = []
    for nal in nals:
        if len(nal) <= MTU:
            payloads.append(nal)
            continue
        if codec == "h264":
            ind = (nal[0] & 0xE0) | 28
            hdr_t = nal[0] & 0x1F
            body, head = nal[1:], lambda s, e: bytes([ind, (0x80 if s else 0) | (0x40 if e else 0) | hdr_t])
        else:
            t = (nal[0] >> 1) & 0x3F
            ph = bytes([(nal[0] & 0x81) | (49 << 1), nal[1]])
            body, head = nal[2:], lambda s, e: ph + bytes([(0x80 if s else 0) | (0x40 if e else 0) | t])
        size = MTU if len(body) > MTU else (len(body) + 1) // 2   # a FU needs >= 2 fragments
        chunks = [body[i:i + size] for i in range(0, len(body), size)]
        for k, ch in enumerate(chunks):
            payloads.append(head(k == 0, k == len(chunks) - 1) + ch)
    for k, p in enumerate(payloads):
        marker = 0x80 if k == len(payloads) - 1 else 0
        out.append(struct.pack("!BBHII", 0x80, marker | PT, seq & 0xFFFF, ts & 0xFFFFFFFF, ssrc) + p)
        seq += 1
    return out, seq


class Server:
    def __init__(self, channels: dict[str, Channel], join_mid_gop: bool):
        self.channels, self.join_mid_gop = channels, join_mid_gop

    async def handle(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
        session = f"{random.getrandbits(48):012x}"
        chan: Channel | None = None
        play_task: asyncio.Task | None = None
        try:
            while True:
                first = await reader.readexactly(1)
                if first == b"$":                       # interleaved RTCP from client
                    hdr = await reader.readexactly(3)
                    await reader.readexactly(struct.unpack("!H", hdr[1:])[0])
                    continue
                line = first + await reader.readuntil(b"\r\n")
                method, url, _ = line.decode().strip().split(" ", 2)
                headers = {}
                while True:
                    h = (await reader.readuntil(b"\r\n")).decode().strip()
                    if not h:
                        break
                    k, _, v = h.partition(":")
                    headers[k.strip().lower()] = v.strip()
                if int(headers.get("content-length", 0)):
                    await reader.readexactly(int(headers["content-length"]))
                cseq = headers.get("cseq", "0")
                path = url.split("://", 1)[-1].split("/", 1)[-1] if "://" in url else url.lstrip("/")
                path = path.split("?")[0].rstrip("/")
                if path.endswith("trackID=0"):
                    path = path[: -len("trackID=0")].rstrip("/")

                def reply(code: str, extra: dict | None = None, body: str = "") -> None:
                    hs = [f"RTSP/1.0 {code}", f"CSeq: {cseq}", "Server: prahari-replica"]
                    for k, v in (extra or {}).items():
                        hs.append(f"{k}: {v}")
                    if body:
                        hs.append(f"Content-Length: {len(body.encode())}")
                    writer.write(("\r\n".join(hs) + "\r\n\r\n" + body).encode())

                if method == "OPTIONS":
                    reply("200 OK", {"Public": "OPTIONS, DESCRIBE, SETUP, PLAY, TEARDOWN, GET_PARAMETER"})
                elif method in ("DESCRIBE", "SETUP", "PLAY") and path not in self.channels:
                    reply("404 Not Found")
                elif method == "DESCRIBE":
                    chan = self.channels[path]
                    await asyncio.wait_for(chan.ready.wait(), 10)
                    host = writer.get_extra_info("sockname")[0]
                    reply("200 OK", {"Content-Type": "application/sdp",
                                     "Content-Base": url.rstrip("/") + "/"}, chan.sdp(host))
                elif method == "SETUP":
                    chan = self.channels[path]
                    tr = headers.get("transport", "")
                    if "RTP/AVP/TCP" not in tr.upper():
                        reply("461 Unsupported Transport")
                    else:
                        reply("200 OK", {"Transport": "RTP/AVP/TCP;unicast;interleaved=0-1",
                                         "Session": f"{session};timeout=60"})
                elif method == "PLAY" and chan is not None:
                    reply("200 OK", {"Session": session, "Range": "npt=0.000-"})
                    await writer.drain()
                    play_task = asyncio.create_task(self.play(chan, writer))
                elif method == "TEARDOWN":
                    reply("200 OK", {"Session": session})
                    await writer.drain()
                    break
                elif method == "GET_PARAMETER":
                    reply("200 OK", {"Session": session})
                else:
                    reply("405 Method Not Allowed")
                await writer.drain()
        except (asyncio.IncompleteReadError, ConnectionError, asyncio.TimeoutError, ValueError, OSError):
            pass
        finally:
            if play_task:
                play_task.cancel()
            try:
                writer.close()
            except Exception:
                pass

    async def play(self, chan: Channel, writer: asyncio.StreamWriter) -> None:
        q: asyncio.Queue = asyncio.Queue(maxsize=2000)
        backlog = list(chan.gop)                     # replay the buffered GOP as a burst
        if self.join_mid_gop and len(backlog) > 2:
            backlog = backlog[random.randint(1, len(backlog) - 1):]
        chan.subs[q] = writer
        base = random.getrandbits(32)
        ssrc = random.getrandbits(32)
        seq = random.getrandbits(16)
        first_pts = backlog[0][0] if backlog else None
        try:
            async def send(item):
                nonlocal seq, first_pts
                pts90k, nals, _ = item
                if first_pts is None:
                    first_pts = pts90k
                pkts, seq = rtp_packets(chan.codec, nals, base + pts90k - first_pts, seq, ssrc)
                for p in pkts:
                    writer.write(b"$\x00" + struct.pack("!H", len(p)) + p)
                await writer.drain()
            for item in backlog:
                await send(item)
            while True:
                item = await q.get()
                await send(item)
        except (ConnectionError, OSError, asyncio.CancelledError):
            pass
        finally:
            chan.subs.pop(q, None)
            try:
                writer.close()
            except Exception:
                pass


async def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8554)
    ap.add_argument("--loop-pts-reset", action="store_true")
    ap.add_argument("--join-mid-gop", action="store_true")
    ap.add_argument("--clips", default=str(CLIPS), help="folder of camNN.mp4 files")
    ap.add_argument("--host", default="127.0.0.1")
    a = ap.parse_args()
    chans = {}
    for clip in sorted(Path(a.clips).glob("cam*.mp4")):
        i = int(clip.stem[3:])
        chans[f"stream/{i}"] = Channel(f"stream/{i}", clip, a.loop_pts_reset)
    for ch in chans.values():
        asyncio.create_task(ch.run())
    srv = Server(chans, a.join_mid_gop)
    server = await asyncio.start_server(srv.handle, a.host, a.port)
    print(f"replica RTSP on rtsp://127.0.0.1:{a.port}/stream/<1..{len(chans)}> (pid {os.getpid()}, "
          f"loop_pts_reset={a.loop_pts_reset}, join_mid_gop={a.join_mid_gop})", flush=True)
    async with server:
        await server.serve_forever()


if __name__ == "__main__":
    asyncio.run(main())
