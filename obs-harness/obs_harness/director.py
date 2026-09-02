"""Director: snapshot in, one beat out. No I/O. No OBS."""

HOST_LAYOUTS = {"wide", "split", "solo_l", "solo_r"}


def decide(snapshot: dict) -> dict:
    flags = snapshot.get("flags") or {}
    segment = snapshot.get("segment") or {}
    center = segment.get("center") or {"kind": "none"}
    chyron = segment.get("chyron") or ""
    t = snapshot.get("t", 0.0)

    def beat(**kwargs):
        out = {
            "at": t,
            "layout": "hold",
            "host_source": None,
            "speaking": None,
            "center": center,
            "chyron": chyron,
            "submit": None,
            "why": "",
        }
        out.update(kwargs)
        return out

    if flags.get("panic"):
        return beat(layout="hold", why="panic")

    if flags.get("hold"):
        return beat(layout="hold", why="hold flag")

    ready = list(snapshot.get("ready") or [])
    cooking = snapshot.get("cooking")
    next_line = snapshot.get("next_line")
    spend_policy = segment.get("spend_policy") or "normal"
    can_submit = (
        cooking is None
        and next_line is not None
        and spend_policy == "normal"
    )

    if ready:
        clip = ready[0]
        take = clip["take"]
        layout = _next_host_layout(segment, snapshot.get("layout_i", 0))
        submit = _submit_from_line(snapshot, next_line) if can_submit else None
        return beat(
            layout=layout,
            host_source=f"ready:{take}",
            speaking=clip.get("speaker"),
            submit=submit,
            why="ready clip exists; stub is free" if submit else "ready clip exists",
        )

    wait_layout = _wait_layout(snapshot)

    if cooking is not None:
        return beat(layout=wait_layout, why="waiting on cooking")

    if next_line is not None and spend_policy == "normal":
        return beat(
            layout=wait_layout,
            submit=_submit_from_line(snapshot, next_line),
            why="cold start or hole; submit next line",
        )

    return beat(layout="hold", why="script ended or stop")


def _wait_layout(snapshot: dict) -> str:
    """Keep the last two-box on screen while the next take cooks.

    card_full hides HOST_WIDE. Combined with OBS Fade, that is the
    cameras blinking out between clips. Cold start still uses the card.
    """
    current = snapshot.get("layout")
    if current not in HOST_LAYOUTS:
        on_air = snapshot.get("on_air") or {}
        current = on_air.get("layout")
    if current in HOST_LAYOUTS:
        return current
    center = (snapshot.get("segment") or {}).get("center") or {}
    return "card_full" if center.get("kind") not in (None, "none") else "hold"


def _next_host_layout(segment: dict, layout_i: int) -> str:
    plan = [name for name in (segment.get("layout_plan") or ["split"]) if name in HOST_LAYOUTS]
    if not plan:
        return "split"
    if layout_i >= len(plan):
        return plan[-1]
    return plan[layout_i]


def _submit_from_line(snapshot: dict, next_line: dict) -> dict:
    return {
        "take": snapshot.get("next_take", 1),
        "line": next_line["text"],
        "speaker": next_line.get("speaker"),
    }
