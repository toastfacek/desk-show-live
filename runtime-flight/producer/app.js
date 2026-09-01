const POLL_MS = 200;

function formatClock(seconds) {
  const total = Math.max(0, Math.floor(Number(seconds) || 0));
  const mm = String(Math.floor(total / 60)).padStart(2, "0");
  const ss = String(total % 60).padStart(2, "0");
  return `${mm}:${ss}`;
}

function percent(progress) {
  const value = Math.max(0, Math.min(1, Number(progress) || 0));
  return `${Math.round(value * 100)}%`;
}

function applyLane(root, lane) {
  if (!root || !lane) {
    return;
  }
  const name = root.querySelector("[data-name]");
  const pct = root.querySelector("[data-pct]");
  const bar = root.querySelector("[data-bar]");
  const line = root.querySelector("[data-line]");
  const label = lane.status && lane.status !== "EMPTY" ? `${lane.label} · ${lane.status}` : lane.label;
  const topLabel = root.querySelector(".lane-label");
  if (topLabel) {
    topLabel.textContent = label;
  }
  if (name) {
    name.textContent = lane.name || "—";
  }
  if (pct) {
    pct.textContent = lane.status === "EMPTY" ? "—" : percent(lane.progress);
  }
  if (bar) {
    bar.style.width = percent(lane.progress);
  }
  if (line) {
    line.textContent = lane.line || "";
  }
}

function applyPipeline(root, pipeline) {
  if (!root) {
    return;
  }
  const items = Array.isArray(pipeline) ? pipeline : [];
  while (root.childNodes.length > items.length) {
    root.removeChild(root.lastChild);
  }
  items.forEach((step, index) => {
    let node = root.children[index];
    if (!node) {
      node = document.createElement("div");
      node.className = "pipe-step";
      const label = document.createElement("b");
      const detail = document.createElement("span");
      node.appendChild(label);
      node.appendChild(detail);
      root.appendChild(node);
    }
    const classes = ["pipe-step"];
    if (step.state === "active") {
      classes.push("is-active");
    }
    if (step.state === "done") {
      classes.push("is-done");
    }
    node.className = classes.join(" ");
    node.children[0].textContent = step.label || "";
    node.children[1].textContent = step.detail || step.state || "";
  });
}

function applyList(root, items, write) {
  if (!root) {
    return;
  }
  const rows = Array.isArray(items) ? items : [];
  while (root.childNodes.length > rows.length) {
    root.removeChild(root.lastChild);
  }
  rows.forEach((item, index) => {
    let node = root.children[index];
    if (!node) {
      node = document.createElement("article");
      node.className = "item";
      const who = document.createElement("p");
      who.className = "who";
      const body = document.createElement("p");
      body.className = "body";
      node.appendChild(who);
      node.appendChild(body);
      root.appendChild(node);
    }
    write(node, item);
  });
}

function setEnabled(button, on) {
  if (!button) {
    return;
  }
  button.disabled = !on;
}

function applyState(state, nodes) {
  const program = state.program || {};
  const stats = state.stats || {};
  const flags = state.flags || {};
  const controls = state.controls || {};
  const writer = state.writer || {};
  const story = state.story || {};
  const queue = state.queue || {};

  nodes.eyebrow.textContent = `${state.show || "RUNTIME"} · ${state.system || "LIVE SYSTEM"}`;
  nodes.modePill.textContent = `${String(state.mode || "idle").toUpperCase()} CONTROL`;
  nodes.liveState.textContent = state.live_state || "";
  nodes.meta.textContent = state.meta || "";
  nodes.note.textContent = state.note || "";
  nodes.statLayout.textContent = stats.layout || "—";
  nodes.statSpeaker.textContent = stats.speaker_name || stats.speaker || "—";
  nodes.statSpend.textContent = `$${stats.spend_usd || "0.00"} / ${stats.spend_cap || "0.00"}`;
  nodes.statSeconds.textContent = state.clock || formatClock(state.elapsed_s);
  nodes.rehearsalCopy.textContent =
    state.phase === "PLAY"
      ? "Generating the next take while this one airs."
      : state.phase === "GENERATE"
        ? "Two futures would be a second performer. We keep one clip in the oven."
        : state.phase === "HOLD" || state.phase === "PANIC"
          ? "Hold is a planned beat. Furniture stays up. Faces do not freeze."
          : "Writer fills the slot. The harness will not wait on taste.";

  nodes.program.classList.toggle("is-hold", Boolean(program.hold));
  nodes.program.classList.toggle("is-live", Boolean(program.live));
  nodes.pgClock.textContent = program.clock || state.clock || "00:00";
  nodes.pgLive.style.opacity = program.live ? "1" : "0.4";
  nodes.cardAuthor.textContent = program.card && program.card.author ? program.card.author : "";
  nodes.cardBody.textContent = program.card && program.card.body ? program.card.body : "";
  nodes.pgLine.textContent = program.preview
    ? `PREVIEW · ${program.line || ""}`
    : program.line || "";
  nodes.chyronKicker.textContent = (program.chyron && program.chyron.kicker) || "DESK";
  nodes.chyronHead.textContent = (program.chyron && program.chyron.headline) || "";
  nodes.hostLName.textContent = program.hosts && program.hosts.BOT1 ? program.hosts.BOT1.name : "PHASEONE[lol]";
  nodes.hostRName.textContent = program.hosts && program.hosts.BOT2 ? program.hosts.BOT2.name : "deb";
  nodes.wellL.classList.toggle("is-on", Boolean(program.hosts && program.hosts.BOT1 && program.hosts.BOT1.on_air));
  nodes.wellR.classList.toggle("is-on", Boolean(program.hosts && program.hosts.BOT2 && program.hosts.BOT2.on_air));
  nodes.pgHoldLabel.textContent = state.phase === "PANIC" ? "PANIC" : "STAND BY";

  nodes.dotClock.classList.toggle("is-on", true);
  nodes.dotVideo.classList.toggle("is-on", Boolean(program.live));
  nodes.dotSpend.classList.toggle("is-on", Number(stats.spend_usd || 0) > 0);

  applyLane(nodes.laneOnAir, state.lanes && state.lanes.on_air);
  applyLane(nodes.laneNext, state.lanes && state.lanes.next);
  applyPipeline(nodes.pipe, state.pipeline);

  setEnabled(nodes.btnPreview, Boolean(controls.preview_next));
  setEnabled(nodes.btnHold, Boolean(controls.hold));
  setEnabled(nodes.btnResume, Boolean(controls.resume));
  setEnabled(nodes.btnKill, Boolean(controls.kill_take));
  setEnabled(nodes.btnNext, Boolean(controls.next_segment));
  setEnabled(nodes.btnPanic, Boolean(controls.panic));
  nodes.btnHold.classList.toggle("is-armed", Boolean(flags.hold) === false && Boolean(controls.hold));
  nodes.btnResume.classList.toggle("is-armed", Boolean(flags.hold) || Boolean(flags.panic));

  nodes.writerPhase.textContent = writer.phase || "—";
  const coverage = writer.coverage || {};
  nodes.writerBeat.textContent = coverage.question || story.question || "";
  nodes.writerMeta.textContent = coverage.beat_id
    ? `beat ${coverage.beat_id} · exchanges ${coverage.exchanges} · map ${coverage.map_complete ? "complete" : "open"}`
    : "no coverage yet";
  applyList(nodes.writerReady, writer.ready || [], (node, item) => {
    node.children[0].textContent = item.speaker || "WRITER";
    node.children[1].textContent = item.text || item.line || "";
  });

  nodes.storyId.textContent = story.item_id || "";
  nodes.storyQuestion.textContent = story.question || "";
  nodes.storyFraming.textContent = story.framing || "";
  nodes.storyFight.textContent = story.fight
    ? `${story.throughline} · ${story.fight}`
    : story.throughline || "";
  applyList(nodes.storyBeats, story.beats || [], (node, beat) => {
    node.children[0].textContent = beat.id ? `${beat.id} · ${beat.question}` : beat.question || "";
    node.children[1].textContent = beat.tension || beat.bot1_job || "";
  });

  const nowRows = [];
  if (queue.cooking) {
    nowRows.push({
      speaker: `COOKING · take ${queue.cooking.take}`,
      text: queue.cooking.line || "",
    });
  }
  (queue.ready || []).forEach((item) => {
    nowRows.push({
      speaker: `READY · take ${item.take} · ${item.speaker || ""}`,
      text: item.line || "",
    });
  });
  if (!nowRows.length) {
    nowRows.push({ speaker: "QUEUE", text: "Nothing in the oven. Writer may still be ahead." });
  }
  applyList(nodes.queueNow, nowRows, (node, item) => {
    node.children[0].textContent = item.speaker;
    node.children[1].textContent = item.text;
  });
  applyList(nodes.queueLog, queue.log || [], (node, item) => {
    node.children[0].textContent = `TAKE ${item.take} · ${item.speaker || ""} · ${item.status || ""}`;
    node.children[1].textContent = item.line || "";
  });
}

function collectNodes() {
  return {
    eyebrow: document.getElementById("eyebrow"),
    modePill: document.getElementById("mode-pill"),
    liveState: document.getElementById("live-state"),
    meta: document.getElementById("meta"),
    note: document.getElementById("note"),
    statLayout: document.getElementById("stat-layout"),
    statSpeaker: document.getElementById("stat-speaker"),
    statSpend: document.getElementById("stat-spend"),
    statSeconds: document.getElementById("stat-seconds"),
    rehearsalCopy: document.getElementById("rehearsal-copy"),
    program: document.getElementById("program"),
    pgClock: document.getElementById("pg-clock"),
    pgLive: document.getElementById("pg-live"),
    cardAuthor: document.getElementById("card-author"),
    cardBody: document.getElementById("card-body"),
    pgLine: document.getElementById("pg-line"),
    chyronKicker: document.getElementById("chyron-kicker"),
    chyronHead: document.getElementById("chyron-head"),
    hostLName: document.getElementById("host-l-name"),
    hostRName: document.getElementById("host-r-name"),
    wellL: document.getElementById("well-l"),
    wellR: document.getElementById("well-r"),
    pgHoldLabel: document.querySelector(".hold-label"),
    dotClock: document.getElementById("dot-clock"),
    dotVideo: document.getElementById("dot-video"),
    dotSpend: document.getElementById("dot-spend"),
    laneOnAir: document.getElementById("lane-on-air"),
    laneNext: document.getElementById("lane-next"),
    pipe: document.getElementById("pipe"),
    btnPreview: document.getElementById("btn-preview"),
    btnHold: document.getElementById("btn-hold"),
    btnResume: document.getElementById("btn-resume"),
    btnKill: document.getElementById("btn-kill"),
    btnNext: document.getElementById("btn-next"),
    btnPanic: document.getElementById("btn-panic"),
    writerPhase: document.getElementById("writer-phase"),
    writerBeat: document.getElementById("writer-beat"),
    writerMeta: document.getElementById("writer-meta"),
    writerReady: document.getElementById("writer-ready"),
    storyId: document.getElementById("story-id"),
    storyQuestion: document.getElementById("story-question"),
    storyFraming: document.getElementById("story-framing"),
    storyFight: document.getElementById("story-fight"),
    storyBeats: document.getElementById("story-beats"),
    queueNow: document.getElementById("queue-now"),
    queueLog: document.getElementById("queue-log"),
  };
}

function bootProducer() {
  const nodes = collectNodes();
  const tabs = Array.from(document.querySelectorAll(".tab"));
  const panels = Array.from(document.querySelectorAll(".panel"));

  function showTab(name) {
    tabs.forEach((tab) => {
      tab.classList.toggle("is-on", tab.getAttribute("data-tab") === name);
    });
    panels.forEach((panel) => {
      panel.classList.toggle("is-on", panel.getAttribute("data-panel") === name);
    });
  }

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      showTab(tab.getAttribute("data-tab"));
    });
  });

  async function sendAction(action) {
    try {
      await fetch("/control", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ action }),
      });
    } catch (_error) {
      return;
    }
    await poll();
  }

  document.querySelectorAll("[data-action]").forEach((button) => {
    button.addEventListener("click", () => {
      sendAction(button.getAttribute("data-action"));
    });
  });

  const pause = document.getElementById("btn-pause-run");
  if (pause) {
    pause.addEventListener("click", () => {
      const resume = nodes.btnResume && !nodes.btnResume.disabled;
      sendAction(resume ? "resume" : "hold");
    });
  }

  const full = document.getElementById("btn-fullsize");
  if (full) {
    full.addEventListener("click", () => {
      const monitor = document.getElementById("monitor");
      if (monitor && monitor.requestFullscreen) {
        monitor.requestFullscreen();
      }
    });
  }

  async function poll() {
    try {
      const response = await fetch("/state.json", { cache: "no-store" });
      if (!response.ok) {
        throw new Error("state");
      }
      applyState(await response.json(), nodes);
    } catch (_error) {
      return;
    }
  }

  poll();
  setInterval(poll, POLL_MS);
}

if (typeof module !== "undefined" && module.exports) {
  module.exports = {
    POLL_MS,
    formatClock,
    percent,
    applyLane,
    applyPipeline,
    applyState,
    applyList,
  };
}

if (typeof document !== "undefined") {
  bootProducer();
}
