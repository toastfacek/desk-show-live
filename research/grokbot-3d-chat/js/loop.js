/* Streamer stay/leave loop. Port of streamer_loop.py. Renderer does not decide. */
(function (global) {
  function gtaFixture() {
    return {
      id: "footage-drop-1",
      kind: "footage",
      title: "New footage drop",
      question: "What in this clip is actually new, and do we care?",
      hardClock: 70,
      quietS: 6,
      minTurns: 3,
      moments: [
        { t: 0, id: "m0", what: "Night city card. Rain on the hood. The clip is selling weather.", why: "" },
        { t: 8, id: "m1", what: "A bike cuts six lanes. Traffic shears around it.", why: "motion, density" },
        { t: 18, id: "m2", what: "Wanted stars pop. Cops commit instead of posing.", why: "system, chase" },
        { t: 28, id: "m3", what: "Gap jump. The landing is a little too lucky.", why: "physics tell" },
        { t: 40, id: "m4", what: "Sunset skyline, people on the overpass watching.", why: "tone, crowd" },
      ],
    };
  }

  function openObject(obj, now) {
    return {
      obj: obj,
      glanced: false,
      pointedIds: [],
      took: false,
      landed: false,
      footageEnded: false,
      chatAnswered: 0,
      pendingChat: null,
      turns: 0,
      lastActivityT: now || 0,
      startedAt: now || 0,
    };
  }

  function establishId(obj) {
    return obj.moments.length ? obj.moments[0].id : "";
  }

  function interestingPointed(state) {
    const open = establishId(state.obj);
    return state.pointedIds.some((id) => id !== open);
  }

  function stillOpen(state, pending, ended) {
    if (state.landed) return [];
    const reasons = [];
    if (!state.glanced) reasons.push("have not opened the object");
    if (!interestingPointed(state)) reasons.push("have not pointed at an interesting moment");
    const leftover = state.obj.moments.filter((row) => state.pointedIds.indexOf(row.id) < 0);
    if (leftover.length) reasons.push("unseen interesting moments remain");
    if (!state.took) reasons.push("have not taken a side");
    if (pending) reasons.push("curated chat is waiting");
    if (!ended) reasons.push("footage is still playing");
    return reasons;
  }

  function incoming(state, events) {
    const newIds = [];
    let pending = state.pendingChat;
    let ended = state.footageEnded;
    (events || []).forEach((event) => {
      if (event.type === "moment" && event.momentId) {
        if (newIds.indexOf(event.momentId) < 0) newIds.push(event.momentId);
      } else if (event.type === "chat") {
        pending = event;
      } else if (event.type === "ended") {
        ended = true;
      }
    });
    return { newIds: newIds, pending: pending, ended: ended };
  }

  function nextAction(state, now, events) {
    const got = incoming(state, events);
    const open = stillOpen(state, got.pending, got.ended);
    const clockHit = now - state.startedAt >= state.obj.hardClock;
    const quietHit = now - state.lastActivityT >= state.obj.quietS;

    if (state.landed) {
      return { move: "next", decision: "next", why: "object closed", stillOpen: [], footageEnded: got.ended };
    }
    if (!state.glanced) {
      return {
        move: "glance",
        decision: "stay",
        why: "open the object",
        stillOpen: open,
        footageEnded: got.ended,
        pendingChat: got.pending,
      };
    }

    const fresh = got.newIds.filter((id) => state.pointedIds.indexOf(id) < 0);
    if (fresh.length) {
      return {
        move: interestingPointed(state) ? "react" : "point",
        decision: "stay",
        why: "new moment on the content view",
        stillOpen: open,
        momentId: fresh[0],
        footageEnded: got.ended,
        pendingChat: got.pending,
      };
    }

    if (got.pending && !(clockHit && state.took)) {
      return {
        move: "chat",
        decision: "stay",
        why: "curated chat interrupt",
        stillOpen: open,
        commentId: got.pending.commentId,
        footageEnded: got.ended,
        pendingChat: got.pending,
      };
    }

    if (clockHit && state.took) {
      return { move: "land", decision: "leave", why: "clock killed the topic", stillOpen: [], footageEnded: got.ended };
    }
    if (clockHit && !state.took) {
      return {
        move: "take",
        decision: "stay",
        why: "clock is up; take a side before the land",
        stillOpen: open,
        footageEnded: got.ended,
        pendingChat: got.pending,
      };
    }

    if (got.ended && !state.took) {
      return {
        move: "take",
        decision: "stay",
        why: "footage ended; take a side",
        stillOpen: open,
        footageEnded: true,
        pendingChat: got.pending,
      };
    }
    if (got.ended && got.pending) {
      return {
        move: "chat",
        decision: "stay",
        why: "curated chat before the land",
        stillOpen: open,
        commentId: got.pending.commentId,
        footageEnded: true,
        pendingChat: got.pending,
      };
    }
    if (got.ended && state.took) {
      return { move: "land", decision: "leave", why: "sum up the reaction", stillOpen: [], footageEnded: true };
    }

    if (quietHit && state.took && interestingPointed(state) && state.turns >= state.obj.minTurns) {
      return {
        move: "land",
        decision: "leave",
        why: "quiet; the topic has exhausted itself",
        stillOpen: [],
        footageEnded: got.ended,
      };
    }

    return {
      move: "wait",
      decision: "stay",
      why: "hold for the next moment or a chat poke",
      stillOpen: open,
      footageEnded: got.ended,
      pendingChat: got.pending,
    };
  }

  function apply(state, action, now) {
    const next = {
      obj: state.obj,
      glanced: state.glanced,
      pointedIds: state.pointedIds.slice(),
      took: state.took,
      landed: state.landed,
      footageEnded: state.footageEnded || Boolean(action.footageEnded),
      chatAnswered: state.chatAnswered,
      pendingChat: action.pendingChat || null,
      turns: state.turns,
      lastActivityT: state.lastActivityT,
      startedAt: state.startedAt,
    };
    if (action.move === "glance") {
      next.glanced = true;
      const establish = establishId(state.obj);
      if (establish && next.pointedIds.indexOf(establish) < 0) next.pointedIds.push(establish);
      next.turns += 1;
      next.lastActivityT = now;
    } else if (action.move === "point" || action.move === "react") {
      if (action.momentId && next.pointedIds.indexOf(action.momentId) < 0) {
        next.pointedIds.push(action.momentId);
      }
      next.turns += 1;
      next.lastActivityT = now;
    } else if (action.move === "chat") {
      next.chatAnswered += 1;
      next.pendingChat = null;
      next.turns += 1;
      next.lastActivityT = now;
    } else if (action.move === "take") {
      next.took = true;
      next.turns += 1;
      next.lastActivityT = now;
    } else if (action.move === "land") {
      next.landed = true;
      next.pendingChat = null;
      next.turns += 1;
      next.lastActivityT = now;
    } else if (action.move === "next") {
      next.lastActivityT = now;
    }
    return next;
  }

  global.StreamerLoop = {
    gtaFixture: gtaFixture,
    openObject: openObject,
    nextAction: nextAction,
    apply: apply,
    stillOpen: stillOpen,
  };
})(window);
