/* Drive the grokbot from the streamer loop. Footage is the clock. Chat interrupts. */
(function () {
  const obj = StreamerLoop.gtaFixture();
  let state = StreamerLoop.openObject(obj, 0);
  const bus = GrokbotBus.createBus({
    emotion: "listening",
    energy: 0.25,
    thinking: false,
    squash: 0,
  });
  const voice = GrokbotVoice.createVoice(bus, { muted: false });

  const canvas = document.getElementById("stage");
  const logEl = document.getElementById("log");
  const hudEl = document.getElementById("hud");
  const spokenEl = document.getElementById("spoken");
  const faceEl = document.getElementById("face-state");
  const decisionEl = document.getElementById("decision");
  const loopStateEl = document.getElementById("loop-state");
  const loopMoveEl = document.getElementById("loop-move");
  const monCopy = document.getElementById("mon-copy");
  const monWhy = document.getElementById("mon-why");
  const playhead = document.getElementById("playhead");
  const tNow = document.getElementById("t-now");
  const tEnd = document.getElementById("t-end");
  const muteBtn = document.getElementById("mute");
  const form = document.getElementById("composer");
  const input = document.getElementById("comment");

  try {
    GrokbotFace.createGrokbot(canvas, bus);
  } catch (err) {
    spokenEl.textContent = "Face failed. The loop still runs.";
    console.error(err);
  }

  const lastT = obj.moments[obj.moments.length - 1].t;
  tEnd.textContent = lastT.toFixed(0) + "s";
  const speed = Math.max(0.5, Math.min(8, Number(new URLSearchParams(location.search).get("speed") || 1) || 1));

  let mediaT = 0;
  let lastStamp = performance.now();
  let emitted = {};
  let endedSent = false;
  let queue = [];
  let speaking = false;
  let closed = false;
  let lastMoment = obj.moments[0];

  function append(role, text) {
    const li = document.createElement("li");
    li.className = "msg msg-" + role;
    const who = document.createElement("span");
    who.className = "who";
    who.textContent = role === "chat" ? "CHAT" : "HOST";
    const body = document.createElement("p");
    body.textContent = text;
    li.append(who, body);
    logEl.appendChild(li);
    logEl.scrollTop = logEl.scrollHeight;
  }

  function momentAt(t) {
    let row = obj.moments[0];
    obj.moments.forEach((m) => {
      if (m.t <= t) row = m;
    });
    return row;
  }

  function lineFor(action, pending) {
    const moment = obj.moments.find((m) => m.id === action.momentId) || lastMoment;
    if (action.move === "glance") {
      return "Don't read the card. Weather is the sell. City as a toy before anyone talks.";
    }
    if (action.move === "point") {
      return "There. " + moment.what;
    }
    if (action.move === "react") {
      return "Hold that. " + moment.what + (moment.why ? " That's the " + moment.why + "." : "");
    }
    if (action.move === "chat" && pending) {
      const text = pending.text || "";
      if (/\b(lol|lucky|haha)\b/i.test(text)) {
        return "The landing is the tell. If the physics always forgive you, the chase is a demo.";
      }
      if (/\?/.test(text)) {
        return "Yes. The stars are doing work. Cops commit. That's a system, not a pose.";
      }
      return "Chat's in. I'm taking that as a poke at the clip, not a recap.";
    }
    if (action.move === "take") {
      return "I think the drop is density. The story can wait. The city has to feel expensive to move through.";
    }
    if (action.move === "land") {
      return "That's the clip. City as a toy, chase as the demo, sunset as the postcard. Next object.";
    }
    return "";
  }

  function emotionFor(move) {
    if (move === "chat") return "happy";
    if (move === "take") return "skeptical";
    if (move === "land") return "talking";
    if (move === "react") return "talking";
    return "talking";
  }

  function paintHud(action) {
    decisionEl.textContent = (action.decision || "stay") + " · " + (action.move || "wait");
    loopStateEl.textContent = action.decision || "stay";
    loopMoveEl.textContent = action.move || "wait";
    hudEl.textContent = JSON.stringify(
      {
        t: Number(mediaT.toFixed(1)),
        move: action.move,
        decision: action.decision,
        why: action.why,
        still_open: action.stillOpen || [],
        pointed: state.pointedIds,
        took: state.took,
        landed: state.landed,
      },
      null,
      0
    );
  }

  function paintMonitor() {
    lastMoment = momentAt(mediaT);
    monCopy.textContent = lastMoment.what;
    monWhy.textContent = lastMoment.why ? lastMoment.why : "";
    const span = Math.max(lastT + 1, 1);
    playhead.style.width = Math.min(100, (mediaT / span) * 100) + "%";
    tNow.textContent = mediaT.toFixed(1) + "s";
  }

  function speakAction(action) {
    const pending = action.pendingChat;
    const text = lineFor(action, pending);
    if (!text) {
      state = StreamerLoop.apply(state, action, mediaT);
      speaking = false;
      return;
    }
    speaking = true;
    if (action.move === "chat" && pending) append("chat", pending.text);
    append("host", text);
    spokenEl.textContent = text;
    faceEl.textContent = emotionFor(action.move);
    faceEl.dataset.emotion = emotionFor(action.move);
    bus.applyPerformance(
      { emotion: emotionFor(action.move), energy: 0.62, thinking: false },
      text
    );
    bus.set({ squash: 0.55 });
    voice.speak(text, () => {
      state = StreamerLoop.apply(state, action, mediaT);
      speaking = false;
      if (action.decision === "next" || state.landed && action.move === "land") {
        bus.set({ emotion: "listening", thinking: false, energy: 0.25, squash: 0 });
      } else {
        bus.set({ emotion: "listening", thinking: false, energy: 0.25, squash: 0 });
      }
    });
  }

  function drain() {
    if (speaking || closed) return;
    const action = StreamerLoop.nextAction(state, mediaT, queue);
    queue = [];
    paintHud(action);
    if (action.move === "wait") return;
    if (action.move === "next") {
      closed = true;
      paintHud(action);
      spokenEl.textContent = "Object closed. Next object when you reload.";
      return;
    }
    bus.set({ emotion: "thinking", thinking: true, energy: 0.35, squash: 0 });
    speakAction(action);
  }

  function collect() {
    obj.moments.forEach((m) => {
      if (mediaT >= m.t && !emitted[m.id]) {
        emitted[m.id] = true;
        queue.push({ type: "moment", momentId: m.id });
      }
    });
    if (!endedSent && mediaT >= lastT + 0.5) {
      endedSent = true;
      queue.push({ type: "ended" });
    }
  }

  function tick(stamp) {
    const dt = Math.min(0.2, (stamp - lastStamp) / 1000);
    lastStamp = stamp;
    if (!closed) mediaT += dt * speed;
    paintMonitor();
    collect();
    drain();
    requestAnimationFrame(tick);
  }

  function poke(text) {
    const comment = String(text || "").trim();
    if (!comment || closed) return;
    queue.push({
      type: "chat",
      commentId: "c" + Date.now(),
      text: comment,
      why: "typed poke",
    });
    drain();
  }

  form.addEventListener("submit", (event) => {
    event.preventDefault();
    const value = input.value;
    input.value = "";
    poke(value);
  });
  document.querySelectorAll("[data-sample]").forEach((button) => {
    button.addEventListener("click", () => poke(button.getAttribute("data-sample")));
  });
  muteBtn.addEventListener("click", () => {
    const next = !voice.muted;
    voice.setMuted(next);
    muteBtn.setAttribute("aria-pressed", String(next));
    muteBtn.textContent = next ? "Sound off" : "Sound on";
  });

  bus.subscribe((s) => {
    faceEl.textContent = s.emotion;
    faceEl.dataset.emotion = s.emotion;
  });

  requestAnimationFrame(tick);
})();
