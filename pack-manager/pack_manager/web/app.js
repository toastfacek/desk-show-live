const state = { packs: [], assets: [], candidates: [], baselines: [] };
const notice = document.querySelector("#notice");

async function api(path, options = {}) {
  const response = await fetch(path, options);
  const contentType = response.headers.get("content-type") || "";
  const body = contentType.includes("json") ? await response.json() : await response.text();
  if (!response.ok) {
    const message = body?.error?.message || body?.detail?.[0]?.msg || `HTTP ${response.status}`;
    throw new Error(message);
  }
  return body;
}

function jsonRequest(method, body) {
  return {
    method,
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  };
}

function show(message, error = false) {
  notice.textContent = message;
  notice.classList.toggle("error", error);
}

function parseJson(form, name) {
  return JSON.parse(new FormData(form).get(name));
}

function option(value, label) {
  const item = document.createElement("option");
  item.value = value;
  item.textContent = label;
  return item;
}

function refill(selector, records, label, includeBlank = false) {
  document.querySelectorAll(selector).forEach((select) => {
    const current = select.value;
    select.replaceChildren();
    if (includeBlank) select.append(option("", "Canonical"));
    records.forEach((record) => select.append(option(record.id, label(record))));
    if ([...select.options].some((item) => item.value === current)) select.value = current;
  });
}

async function refresh() {
  [state.packs, state.assets, state.candidates, state.baselines] = await Promise.all([
    api("/api/packs"),
    api("/api/assets"),
    api("/api/candidates"),
    api("/api/baselines"),
  ]);
  render();
}

function render() {
  refill(".pack-options", state.packs, (item) => `${item.name} · ${item.kind}`);
  refill(".asset-options", state.assets, (item) => `${item.id} · ${item.mime_type}`);
  refill(
    ".canonical-options",
    state.candidates.filter((item) => item.status === "approved" && !item.canonical_candidate_id),
    (item) => `${item.id} · ${item.cast_key.slice(0, 10)}`,
  );
  refill(".candidate-options", state.candidates, (item) => `${item.id} · ${item.status}`, true);

  const packs = document.querySelector("#packs");
  packs.replaceChildren(...state.packs.map((pack) => {
    const card = document.createElement("article");
    card.innerHTML = `<h3>${escapeHtml(pack.name)}</h3><p><code>${escapeHtml(pack.id)}</code></p><p>${pack.kind}</p>`;
    const button = document.createElement("button");
    button.textContent = "View versions";
    button.type = "button";
    button.onclick = async () => {
      try {
        const versions = await api(`/api/packs/${encodeURIComponent(pack.id)}/versions`);
        const pre = document.createElement("pre");
        pre.textContent = JSON.stringify(versions, null, 2);
        card.querySelector("pre")?.remove();
        card.append(pre);
      } catch (error) { show(error.message, true); }
    };
    card.append(button);
    return card;
  }));

  const candidates = document.querySelector("#candidates");
  candidates.replaceChildren(...state.candidates.map(candidateCard));

  const baselines = document.querySelector("#baselines");
  baselines.replaceChildren(...state.baselines.map((baseline) => {
    const card = document.createElement("article");
    card.innerHTML = `
      <h3>${escapeHtml(baseline.id)}</h3>
      <p>Candidate: <code>${escapeHtml(baseline.candidate_id)}</code></p>
      <p>${escapeHtml(baseline.fallback_reason || "Requested candidate selected")}</p>`;
    const inspect = document.createElement("button");
    inspect.type = "button";
    inspect.textContent = "Inspect manifest";
    inspect.onclick = () => inspectManifest(baseline.id);
    const download = document.createElement("a");
    download.href = `/api/baselines/${encodeURIComponent(baseline.id)}/download/manifest`;
    download.textContent = "Download manifest";
    download.className = "button-link";
    card.append(inspect, download);
    return card;
  }));
}

function candidateCard(candidate) {
  const card = document.createElement("article");
  card.innerHTML = `
    <h3>${escapeHtml(candidate.theme || "Canonical candidate")}</h3>
    <p><code>${escapeHtml(candidate.id)}</code></p>
    <p><span class="status ${candidate.status}">${candidate.status}</span></p>
    <p>Hero: <code>${escapeHtml(candidate.hero_asset_id)}</code></p>
    <p>Cast: <code>${escapeHtml(candidate.cast_key)}</code></p>`;
  if (candidate.status === "draft") {
    const note = document.createElement("input");
    note.placeholder = "Review note";
    note.setAttribute("aria-label", `Review note for ${candidate.id}`);
    const approve = actionButton("Approve", () => reviewCandidate(candidate.id, "approve", note.value, false));
    const canonical = actionButton("Approve canonical", () => reviewCandidate(candidate.id, "approve", note.value, true));
    const reject = actionButton("Reject", () => reviewCandidate(candidate.id, "reject", note.value, false));
    card.append(note, approve, canonical, reject);
  }
  return card;
}

function actionButton(label, handler) {
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = label;
  button.onclick = handler;
  return button;
}

async function reviewCandidate(id, action, reviewNote, canonical) {
  try {
    await api(
      `/api/candidates/${encodeURIComponent(id)}/${action}`,
      jsonRequest("POST", action === "approve" ? { review_note: reviewNote, canonical } : { review_note: reviewNote }),
    );
    show(`Candidate ${action}d.`);
    await refresh();
  } catch (error) { show(error.message, true); }
}

async function inspectManifest(id) {
  try {
    const manifest = await api(`/api/baselines/${encodeURIComponent(id)}/manifest`);
    document.querySelector("#manifest").textContent = JSON.stringify(manifest, null, 2);
    show("Manifest verified and loaded.");
  } catch (error) { show(error.message, true); }
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function handle(formId, handler) {
  document.querySelector(formId).addEventListener("submit", async (event) => {
    event.preventDefault();
    try {
      await handler(event.currentTarget);
      show("Saved.");
      await refresh();
    } catch (error) {
      show(error.message, true);
    }
  });
}

handle("#pack-form", (form) => {
  const data = new FormData(form);
  return api("/api/packs", jsonRequest("POST", { kind: data.get("kind"), name: data.get("name") }));
});

handle("#asset-form", (form) => api("/api/assets", { method: "POST", body: new FormData(form) }));

handle("#version-form", (form) => {
  const data = new FormData(form);
  return api(
    `/api/packs/${encodeURIComponent(data.get("pack_id"))}/versions`,
    jsonRequest("POST", { manifest: parseJson(form, "manifest") }),
  );
});

function candidatePayload(form) {
  const data = new FormData(form);
  return {
    character_versions: parseJson(form, "character_versions"),
    scene_pack_id: data.get("scene_pack_id"),
    scene_version: Number(data.get("scene_version")),
  };
}

handle("#candidate-form", (form) => {
  const data = new FormData(form);
  return api("/api/candidates", jsonRequest("POST", {
    ...candidatePayload(form),
    hero_asset_id: data.get("hero_asset_id"),
  }));
});

handle("#generate-form", (form) => {
  const data = new FormData(form);
  const seed = data.get("seed");
  return api("/api/candidates/generate", jsonRequest("POST", {
    ...candidatePayload(form),
    hero_asset_id: data.get("reference_asset_id"),
    reference_asset_ids: [data.get("reference_asset_id")],
    prompt: data.get("prompt"),
    seed: seed === "" ? null : Number(seed),
  }));
});

handle("#variant-form", (form) => {
  const data = new FormData(form);
  return api("/api/candidates/variants", jsonRequest("POST", {
    canonical_candidate_id: data.get("canonical_candidate_id"),
    hero_asset_id: data.get("hero_asset_id"),
    theme: data.get("theme"),
    changes: parseJson(form, "changes"),
  }));
});

handle("#baseline-form", async (form) => {
  const data = new FormData(form);
  const baseline = await api("/api/baselines", jsonRequest("POST", {
    cast_key: data.get("cast_key"),
    requested_candidate_id: data.get("requested_candidate_id") || null,
  }));
  await inspectManifest(baseline.id);
});

refresh().catch((error) => show(error.message, true));
