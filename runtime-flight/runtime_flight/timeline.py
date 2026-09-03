"""Build a viewable cook-path waterfall from fal_cook / takes logs."""

from __future__ import annotations

import html
import json
from pathlib import Path
from typing import Any

SPAN_COLORS = {
    "hero_upload": "#64748B",
    "submit": "#475569",
    "in_queue": "#94A3B8",
    "in_progress": "#F59E0B",
    "poll": "#F59E0B",
    "fal_wait": "#D97706",
    "inference": "#D4E04A",
    "after_denoise": "#9A3412",
    "result": "#FB923C",
    "download": "#3B82F6",
    "validate": "#8B5CF6",
    "extract": "#10B981",
    "upload_frame": "#EF4444",
    "copy": "#14B8A6",
    "post": "#A78BFA",
    "all cooks": "#1C1D16",
}

SPAN_LABELS = {
    "hero_upload": "hero upload",
    "submit": "queue POST",
    "in_queue": "IN_QUEUE",
    "in_progress": "IN_PROGRESS",
    "poll": "poll to COMPLETED",
    "fal_wait": "fal wait (queue + IN_PROGRESS)",
    "inference": "fal inference (reported)",
    "after_denoise": "after denoise (encode / publish / unknown)",
    "result": "result GET",
    "download": "download mp4",
    "validate": "validate",
    "extract": "last-frame extract",
    "upload_frame": "frame upload",
    "copy": "copy to ready",
    "post": "post (unsplit)",
    "all cooks": "all cooks",
}


def load_cook_rows(root: Path) -> list[dict[str, Any]]:
    root = Path(root)
    if root.is_file():
        return _load_file(root)
    for relative in (
        "fal_cook.jsonl",
        "logs/fal_cook.jsonl",
        "takes.jsonl",
        "logs/takes.jsonl",
        "summary.json",
    ):
        path = root / relative
        if path.is_file():
            return _load_file(path)
    raise FileNotFoundError(f"no cook log in {root}")


def _load_file(path: Path) -> list[dict[str, Any]]:
    if path.suffix == ".json":
        raw = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(raw, dict) and isinstance(raw.get("takes"), list):
            return [row for row in raw["takes"] if isinstance(row, dict)]
        raise ValueError("summary.json must contain a takes array")
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        if isinstance(item, dict):
            rows.append(item)
    return rows


def spans_from_row(row: dict[str, Any]) -> list[dict[str, Any]]:
    existing = row.get("spans")
    if isinstance(existing, list) and existing:
        return [span for span in existing if isinstance(span, dict)]
    spans: list[dict[str, Any]] = []
    t_hero = _num(row.get("t_hero_s"))
    if t_hero and t_hero > 0:
        spans.append(_span("hero_upload", -t_hero, 0, "wall"))
    cursor = 0.0
    t_submit = _num(row.get("t_submit_s")) or 0.0
    if t_submit > 0:
        spans.append(_span("submit", 0.0, t_submit, "wall"))
    cursor = t_submit
    t_completed = _num(row.get("t_completed_s"))
    samples = row.get("status_samples")
    poll_spans = _spans_from_samples(samples, offset=t_submit, end_s=t_completed)
    if poll_spans:
        spans.extend(poll_spans)
        cursor = max(span["end_s"] for span in poll_spans)
    elif t_completed is not None and t_completed > cursor:
        spans.append(_span("poll", cursor, t_completed, "wall"))
        cursor = t_completed
    t_inference = _num(row.get("t_inference_s"))
    if t_inference and t_inference > 0:
        first = _num(row.get("t_first_progress_s"))
        start = t_submit + (first if first is not None else 0.0)
        end = start + t_inference
        if t_completed is not None:
            end = min(end, t_completed)
        spans.append(
            _span(
                "inference",
                start,
                end,
                "fal",
                "payload.timings.inference; start inferred from first IN_PROGRESS",
            )
        )
    t_result = _num(row.get("t_result_s"))
    if t_result and t_result > 0:
        spans.append(_span("result", cursor, cursor + t_result, "wall"))
        cursor += t_result
    t_download = _num(row.get("t_download_s"))
    if t_download and t_download > 0:
        spans.append(_span("download", cursor, cursor + t_download, "wall"))
        cursor += t_download
    staged = (
        ("validate", row.get("t_validate_s")),
        ("extract", row.get("t_extract_s")),
        ("upload_frame", row.get("t_upload_frame_s")),
        ("copy", row.get("t_copy_s")),
    )
    if any(_num(value) for _, value in staged):
        for name, value in staged:
            seconds = _num(value)
            if seconds and seconds > 0:
                spans.append(_span(name, cursor, cursor + seconds, "wall"))
                cursor += seconds
    else:
        t_post = _num(row.get("t_post_s"))
        if t_post and t_post > 0:
            spans.append(_span("post", cursor, cursor + t_post, "wall"))
    return spans


def _spans_from_samples(
    samples: Any, *, offset: float, end_s: float | None
) -> list[dict[str, Any]]:
    if not isinstance(samples, list) or len(samples) < 1:
        return []
    points: list[tuple[float, str, int | None]] = []
    for sample in samples:
        if not isinstance(sample, dict):
            continue
        t_s = _num(sample.get("t_s"))
        status = sample.get("status")
        if t_s is None or not isinstance(status, str) or status == "":
            continue
        position = sample.get("queue_position")
        pos = position if isinstance(position, int) and not isinstance(position, bool) else None
        points.append((t_s, status, pos))
    if not points:
        return []
    spans: list[dict[str, Any]] = []
    for index, (t_s, status, pos) in enumerate(points):
        start = offset + t_s
        if index + 1 < len(points):
            stop = offset + points[index + 1][0]
        elif end_s is not None:
            stop = max(end_s, start)
        else:
            stop = start
        name = {
            "IN_QUEUE": "in_queue",
            "IN_PROGRESS": "in_progress",
        }.get(status)
        if name is None:
            continue
        if stop <= start:
            continue
        detail = f"queue_position={pos}" if pos is not None else None
        spans.append(_span(name, start, stop, "poll", detail))
    return spans


def _span(
    name: str, start_s: float, end_s: float, source: str, detail: str | None = None
) -> dict[str, Any]:
    start_s = round(float(start_s), 3)
    end_s = round(float(end_s), 3)
    return {
        "name": name,
        "label": SPAN_LABELS.get(name, name),
        "start_s": start_s,
        "end_s": end_s,
        "dur_s": round(end_s - start_s, 3),
        "source": source,
        "detail": detail,
        "color": SPAN_COLORS.get(name, "#64748B"),
    }


def _num(value: Any) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return float(value)


def flame_tree_from_row(row: dict[str, Any]) -> dict[str, Any]:
    """Inclusive cook tree. Inference nests under IN_PROGRESS; leftover is after_denoise."""
    spans = spans_from_row(row)
    dur = {name: 0.0 for name in SPAN_LABELS}
    for span in spans:
        name = str(span.get("name") or "")
        dur[name] = dur.get(name, 0.0) + float(span.get("dur_s") or 0.0)

    children: list[dict[str, Any]] = []
    if dur["hero_upload"] > 0:
        children.append(_flame_node("hero_upload", dur["hero_upload"]))
    if dur["submit"] > 0:
        children.append(_flame_node("submit", dur["submit"]))

    queue = dur["in_queue"]
    progress = dur["in_progress"] if dur["in_progress"] > 0 else dur["poll"]
    infer = dur["inference"]
    wait_children: list[dict[str, Any]] = []
    if queue > 0:
        wait_children.append(_flame_node("in_queue", queue))
    if progress > 0:
        nested: list[dict[str, Any]] = []
        used = min(infer, progress) if infer > 0 else 0.0
        if used > 0:
            nested.append(_flame_node("inference", used))
        leftover = round(progress - used, 3)
        if leftover > 0:
            nested.append(_flame_node("after_denoise", leftover))
        wait_children.append(_flame_node("in_progress", progress, nested))
    wait = round(queue + progress, 3)
    if wait > 0:
        children.append(_flame_node("fal_wait", wait, wait_children))

    if dur["result"] > 0:
        children.append(_flame_node("result", dur["result"]))
    if dur["download"] > 0:
        children.append(_flame_node("download", dur["download"]))

    post_parts = [
        ("validate", dur["validate"]),
        ("extract", dur["extract"]),
        ("upload_frame", dur["upload_frame"]),
        ("copy", dur["copy"]),
    ]
    post_sum = round(sum(value for _, value in post_parts), 3)
    if post_sum > 0:
        children.append(
            _flame_node(
                "post",
                post_sum,
                [_flame_node(name, value) for name, value in post_parts if value > 0],
            )
        )
    elif dur["post"] > 0:
        children.append(_flame_node("post", dur["post"]))

    child_sum = round(sum(child["value"] for child in children), 3)
    cook = _num(row.get("t_cook_s")) or 0.0
    root_val = max(child_sum, round(cook + dur["hero_upload"], 3))
    take = row.get("take", "?")
    return _flame_node(f"take {take}", root_val, children)


def merge_flame_trees(trees: list[dict[str, Any]]) -> dict[str, Any]:
    children = [child for tree in trees for child in (tree.get("children") or [])]
    return _flame_node(
        "all cooks",
        round(sum(float(tree.get("value") or 0.0) for tree in trees), 3),
        _merge_flame_children(children),
    )


def _merge_flame_children(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    order: list[str] = []
    for node in nodes:
        name = str(node.get("name") or "")
        if name not in grouped:
            order.append(name)
            grouped[name] = []
        grouped[name].append(node)
    merged: list[dict[str, Any]] = []
    for name in order:
        group = grouped[name]
        kids = [
            child
            for node in group
            for child in (node.get("children") or [])
        ]
        merged.append(
            _flame_node(
                name,
                sum(float(node.get("value") or 0.0) for node in group),
                _merge_flame_children(kids),
            )
        )
    return merged


def _flame_node(
    name: str, value: float, children: list[dict[str, Any]] | None = None
) -> dict[str, Any]:
    kids = [child for child in (children or []) if float(child.get("value") or 0.0) > 0]
    return {
        "name": name,
        "label": SPAN_LABELS.get(name, name),
        "value": round(float(value), 3),
        "color": SPAN_COLORS.get(name, "#1C1D16"),
        "children": kids,
    }


def session_offsets(rows: list[dict[str, Any]]) -> list[float]:
    offsets: list[float] = []
    cursor = 0.0
    for row in rows:
        offsets.append(round(cursor, 3))
        cook = _num(row.get("t_cook_s"))
        if cook is None:
            spans = spans_from_row(row)
            if spans:
                cook = max(span["end_s"] for span in spans)
        cursor += cook or 0.0
    return offsets


def render_timeline_html(
    rows: list[dict[str, Any]],
    *,
    title: str = "H3 cook timeline",
    duration_s: float | None = None,
) -> str:
    prepared: list[dict[str, Any]] = []
    offsets = session_offsets(rows)
    play = duration_s
    for index, row in enumerate(rows):
        if play is None:
            play = _num(row.get("duration_s"))
        spans = spans_from_row(row)
        flame = flame_tree_from_row(row)
        prepared.append(
            {
                "take": row.get("take", index + 1),
                "status": row.get("status"),
                "request_id": row.get("request_id"),
                "t_inference_s": row.get("t_inference_s"),
                "t_cook_s": row.get("t_cook_s"),
                "t_completed_s": row.get("t_completed_s"),
                "spans": spans,
                "flame": flame,
                "offset_s": offsets[index],
            }
        )
    payload = json.dumps(
        {
            "takes": prepared,
            "play_s": play or 5,
            "merged_flame": merge_flame_trees(
                [item["flame"] for item in prepared]
            ),
        },
        separators=(",", ":"),
    )
    return _HTML_PAGE.replace("__TITLE__", html.escape(title)).replace(
        "__PAYLOAD__", payload
    )


def write_timeline(
    root: Path,
    *,
    title: str | None = None,
    duration_s: float | None = None,
) -> Path:
    root = Path(root)
    search = root if root.is_dir() else root.parent
    rows = load_cook_rows(search)
    if duration_s is None:
        for row in rows:
            duration_s = _num(row.get("duration_s"))
            if duration_s is not None:
                break
    html_path = search / "timeline.html"
    if (search / "logs").is_dir() and not (search / "fal_cook.jsonl").is_file():
        html_path = search / "logs" / "timeline.html"
    if search.name == "logs":
        html_path = search / "timeline.html"
    page = render_timeline_html(
        rows, title=title or f"cook timeline · {search.name}", duration_s=duration_s
    )
    html_path.write_text(page, encoding="utf-8")
    if search.name == "logs":
        parent_copy = search.parent / "timeline.html"
        parent_copy.write_text(page, encoding="utf-8")
    return html_path


_HTML_PAGE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>__TITLE__</title>
<style>
:root { --bg:#11120C; --ink:#F4F1E6; --muted:#A39B86; --line:#2A2B22; --play:#D4E04A; }
* { box-sizing:border-box; }
body { margin:0; background:var(--bg); color:var(--ink); font:14px/1.45 ui-sans-serif,system-ui,sans-serif; }
main { max-width:1100px; margin:0 auto; padding:28px 20px 64px; }
h1 { font-size:22px; font-weight:650; margin:0 0 6px; }
.sub { color:var(--muted); margin:0 0 20px; }
.toolbar { display:flex; flex-wrap:wrap; gap:8px; margin:0 0 16px; }
button { background:#1C1D16; color:var(--ink); border:1px solid var(--line); border-radius:999px; padding:6px 12px; cursor:pointer; }
button[aria-pressed="true"] { background:var(--play); color:#11120C; border-color:var(--play); }
.legend { display:flex; flex-wrap:wrap; gap:10px 16px; margin:0 0 20px; color:var(--muted); }
.swatch { display:inline-block; width:10px; height:10px; border-radius:2px; margin-right:6px; vertical-align:middle; }
.row { margin:0 0 18px; }
.head { display:flex; justify-content:space-between; gap:12px; margin:0 0 6px; }
.meta { color:var(--muted); font-variant-numeric:tabular-nums; }
.track { position:relative; height:36px; background:#1A1B14; border:1px solid var(--line); border-radius:6px; overflow:hidden; }
.bar { position:absolute; top:6px; height:24px; border-radius:3px; min-width:2px; }
.bar.inference { top:10px; height:16px; opacity:0.95; box-shadow:inset 0 0 0 1px #11120C; }
.play { position:absolute; top:0; bottom:0; width:1px; background:var(--play); }
.axis { position:relative; height:18px; color:var(--muted); font-size:11px; margin-top:4px; }
.tick { position:absolute; transform:translateX(-50%); }
table { width:100%; border-collapse:collapse; margin-top:28px; font-variant-numeric:tabular-nums; }
th,td { text-align:left; padding:8px 10px; border-bottom:1px solid var(--line); }
th { color:var(--muted); font-weight:550; }
.note { color:var(--muted); margin-top:16px; font-size:12px; }
#waterfall-tools { display:flex; flex-wrap:wrap; gap:8px; margin:0 0 12px; }
#flame-tools { display:none; flex-wrap:wrap; gap:8px; margin:0 0 12px; }
.flame-wrap { margin:0 0 28px; }
.flame-wrap svg { width:100%; height:auto; display:block; background:#1A1B14; border:1px solid var(--line); border-radius:6px; }
.frame { cursor:pointer; }
.frame:hover rect { stroke:#F4F1E6; stroke-width:1; }
.frame text { font:11px/1 ui-sans-serif,system-ui,sans-serif; fill:#11120C; pointer-events:none; }
.tip { position:fixed; display:none; background:#1C1D16; color:var(--ink); border:1px solid var(--line); padding:6px 8px; font-size:12px; pointer-events:none; z-index:9; }
</style>
</head>
<body>
<main>
  <h1>__TITLE__</h1>
  <p class="sub">Wall bars are measured locally. The lemon frame is fal <code>timings.inference</code> — GPU denoise only. The rust frame under IN_PROGRESS is everything after denoise (encode / publish / unknown).</p>
  <div class="toolbar">
    <button id="btn-waterfall" aria-pressed="true">Waterfall</button>
    <button id="btn-flame" aria-pressed="false">Flame graph</button>
  </div>
  <div id="waterfall-tools">
    <button id="btn-compare" aria-pressed="true">Compare takes</button>
    <button id="btn-session" aria-pressed="false">Session</button>
  </div>
  <div id="flame-tools">
    <button id="btn-flame-orient" aria-pressed="true">Flame (root at bottom)</button>
    <button id="btn-icicle" aria-pressed="false">Icicle (root at top)</button>
    <button id="btn-reset">Reset zoom</button>
  </div>
  <div class="legend" id="legend"></div>
  <div id="chart"></div>
  <table id="table"></table>
  <p class="note">Click a flame frame to zoom. Width is inclusive seconds. Inference is nested under IN_PROGRESS and does not add extra width. Frame upload is the last-frame PNG that gates the next same-speaker take.</p>
</main>
<div class="tip" id="tip"></div>
<script>
const DATA = __PAYLOAD__;
const LABELS = {
  hero_upload:"hero upload", submit:"queue POST", in_queue:"IN_QUEUE",
  in_progress:"IN_PROGRESS", poll:"poll to COMPLETED", fal_wait:"fal wait",
  inference:"fal inference", after_denoise:"after denoise",
  result:"result GET", download:"download", validate:"validate",
  extract:"last-frame extract", upload_frame:"frame upload", copy:"copy to ready",
  post:"post", "all cooks":"all cooks"
};
const COLORS = {};
DATA.takes.forEach(t => t.spans.forEach(s => { COLORS[s.name] = s.color; }));
function legend() {
  const names = new Set();
  DATA.takes.forEach(t => t.spans.forEach(s => names.add(s.name)));
  names.add("after_denoise");
  names.add("fal_wait");
  document.getElementById("legend").innerHTML = [...names].map(name => {
    const color = COLORS[name] || (name === "after_denoise" ? "#9A3412" : name === "fal_wait" ? "#D97706" : "#64748B");
    return `<span><i class="swatch" style="background:${color}"></i>${LABELS[name] || name}</span>`;
  }).join("");
}
function maxEnd(session) {
  let max = DATA.play_s || 5;
  DATA.takes.forEach(t => {
    t.spans.forEach(s => {
      const end = (session ? t.offset_s : 0) + s.end_s;
      if (end > max) max = end;
    });
    const cook = (session ? t.offset_s : 0) + (t.t_cook_s || 0);
    if (cook > max) max = cook;
  });
  return Math.max(max, DATA.play_s || 5) * 1.05;
}
function renderWaterfall(session) {
  const widthFor = maxEnd(session);
  const chart = document.getElementById("chart");
  chart.innerHTML = DATA.takes.map(t => {
    const bars = t.spans.map(s => {
      const start = (session ? t.offset_s : 0) + s.start_s;
      const left = (start / widthFor) * 100;
      const width = Math.max(((s.end_s - s.start_s) / widthFor) * 100, 0.2);
      const cls = s.name === "inference" ? "bar inference" : "bar";
      const title = `${s.label}: ${s.dur_s.toFixed(3)}s${s.detail ? " · " + s.detail : ""}`;
      return `<div class="${cls}" style="left:${left}%;width:${width}%;background:${s.color}" title="${title}"></div>`;
    }).join("");
    const playLeft = ((session ? t.offset_s : 0) + DATA.play_s) / widthFor * 100;
    const ticks = [];
    for (let s = 0; s <= widthFor; s += (widthFor > 20 ? 5 : 1)) {
      ticks.push(`<span class="tick" style="left:${(s/widthFor)*100}%">${s.toFixed(0)}s</span>`);
    }
    const infer = t.t_inference_s == null ? "—" : t.t_inference_s.toFixed(3) + "s infer";
    const cook = t.t_cook_s == null ? "—" : t.t_cook_s.toFixed(3) + "s cook";
    return `<section class="row">
      <div class="head"><strong>take ${t.take}</strong><span class="meta">${infer} · ${cook} · ${t.status || ""}</span></div>
      <div class="track">${bars}<div class="play" style="left:${playLeft}%" title="play length ${DATA.play_s}s"></div></div>
      <div class="axis">${ticks.join("")}</div>
    </section>`;
  }).join("");
  renderTable();
}
function renderTable() {
  const cols = ["take","infer","COMPLETED","cook","surplus","hero","POST","queue/progress","download","validate","extract","upload","copy"];
  const body = DATA.takes.map(t => {
    const by = Object.fromEntries(t.spans.map(s => [s.name, s.dur_s]));
    const queue = (by.in_queue || 0) + (by.in_progress || by.poll || 0);
    const surplus = t.t_cook_s == null ? "" : (DATA.play_s - t.t_cook_s).toFixed(3);
    const cell = (v) => v == null || v === 0 ? "—" : Number(v).toFixed(3);
    return `<tr>
      <td>${t.take}</td><td>${cell(t.t_inference_s)}</td><td>${cell(t.t_completed_s)}</td>
      <td>${cell(t.t_cook_s)}</td><td>${surplus}</td><td>${cell(by.hero_upload)}</td>
      <td>${cell(by.submit)}</td><td>${cell(queue)}</td><td>${cell(by.download)}</td>
      <td>${cell(by.validate)}</td><td>${cell(by.extract)}</td>
      <td>${cell(by.upload_frame)}</td><td>${cell(by.copy)}</td>
    </tr>`;
  }).join("");
  document.getElementById("table").innerHTML =
    `<thead><tr>${cols.map(c => `<th>${c}</th>`).join("")}</tr></thead><tbody>${body}</tbody>`;
}
function depthOf(node) {
  if (!node.children || !node.children.length) return 1;
  return 1 + Math.max(...node.children.map(depthOf));
}
function layoutFlame(node, x0, x1, depth, rows) {
  rows.push({node, x0, x1, depth});
  const kids = node.children || [];
  let cursor = x0;
  const span = x1 - x0;
  kids.forEach(child => {
    const w = node.value ? span * (child.value / node.value) : 0;
    layoutFlame(child, cursor, cursor + w, depth + 1, rows);
    cursor += w;
  });
}
let flameRoot = DATA.merged_flame;
let icicle = false;
function renderFlame() {
  const chart = document.getElementById("chart");
  const trees = [DATA.merged_flame].concat(DATA.takes.map(t => t.flame));
  chart.innerHTML = trees.map((tree, index) => {
    const title = index === 0 ? "all cooks (merged)" : `take ${DATA.takes[index-1].take}`;
    return `<section class="flame-wrap" data-tree="${index}">
      <div class="head"><strong>${title}</strong><span class="meta">${tree.value.toFixed(3)}s inclusive · click a frame to zoom</span></div>
      <svg viewBox="0 0 1000 20" preserveAspectRatio="none"></svg>
    </section>`;
  }).join("");
  chart.querySelectorAll(".flame-wrap").forEach((wrap, index) => {
    const tree = index === 0 ? flameRoot : DATA.takes[index-1].flame;
    drawFlame(wrap.querySelector("svg"), tree);
  });
  renderTable();
}
function drawFlame(svg, root) {
  const rows = [];
  layoutFlame(root, 0, 1000, 0, rows);
  const maxD = Math.max(...rows.map(r => r.depth)) + 1;
  const rowH = 22;
  const height = maxD * rowH;
  svg.setAttribute("viewBox", `0 0 1000 ${height}`);
  svg.setAttribute("height", String(height));
  svg.innerHTML = rows.map(r => {
    const y = icicle ? r.depth * rowH : (maxD - r.depth - 1) * rowH;
    const w = Math.max(r.x1 - r.x0, 1);
    const label = (w > 80) ? `${r.node.label}  ${r.node.value.toFixed(2)}s` : "";
    const fill = r.node.color || "#334155";
    const ink = (r.node.name === "inference" || r.node.name === "extract") ? "#11120C" : "#F4F1E6";
    return `<g class="frame" data-name="${r.node.name}">
      <rect x="${r.x0.toFixed(2)}" y="${y}" width="${w.toFixed(2)}" height="${rowH-1}" fill="${fill}"></rect>
      <text x="${(r.x0+4).toFixed(2)}" y="${y+15}" fill="${ink}">${label}</text>
    </g>`;
  }).join("");
  svg.querySelectorAll(".frame").forEach((g, i) => {
    g.addEventListener("mousemove", ev => {
      const n = rows[i].node;
      const tip = document.getElementById("tip");
      tip.style.display = "block";
      tip.style.left = (ev.clientX + 12) + "px";
      tip.style.top = (ev.clientY + 12) + "px";
      const pct = root.value ? (100 * n.value / root.value).toFixed(1) : "0";
      tip.textContent = `${n.label}: ${n.value.toFixed(3)}s (${pct}% of this graph)`;
    });
    g.addEventListener("mouseleave", () => { document.getElementById("tip").style.display = "none"; });
    g.addEventListener("click", () => {
      if (svg.closest(".flame-wrap").dataset.tree === "0") {
        flameRoot = rows[i].node;
        renderFlame();
      }
    });
  });
}
let view = "waterfall";
let session = false;
function show(next) {
  view = next;
  document.getElementById("btn-waterfall").setAttribute("aria-pressed", String(view === "waterfall"));
  document.getElementById("btn-flame").setAttribute("aria-pressed", String(view === "flame"));
  document.getElementById("waterfall-tools").style.display = view === "waterfall" ? "flex" : "none";
  document.getElementById("flame-tools").style.display = view === "flame" ? "flex" : "none";
  if (view === "flame") renderFlame();
  else renderWaterfall(session);
}
function setSession(next) {
  session = next;
  document.getElementById("btn-compare").setAttribute("aria-pressed", String(!session));
  document.getElementById("btn-session").setAttribute("aria-pressed", String(session));
  if (view === "waterfall") renderWaterfall(session);
}
function setIcicle(next) {
  icicle = next;
  document.getElementById("btn-flame-orient").setAttribute("aria-pressed", String(!icicle));
  document.getElementById("btn-icicle").setAttribute("aria-pressed", String(icicle));
  if (view === "flame") renderFlame();
}
document.getElementById("btn-waterfall").onclick = () => show("waterfall");
document.getElementById("btn-flame").onclick = () => show("flame");
document.getElementById("btn-compare").onclick = () => setSession(false);
document.getElementById("btn-session").onclick = () => setSession(true);
document.getElementById("btn-flame-orient").onclick = () => setIcicle(false);
document.getElementById("btn-icicle").onclick = () => setIcicle(true);
document.getElementById("btn-reset").onclick = () => { flameRoot = DATA.merged_flame; renderFlame(); };
legend();
show("waterfall");
</script>
</body>
</html>
"""
