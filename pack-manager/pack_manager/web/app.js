const state = { packs: [], versions: [], assets: [], candidates: [], baselines: [] };
const notice = document.querySelector("#notice");

async function api(path, options = {}) {
  const method = (options.method || "GET").toUpperCase();
  if (["POST", "PUT", "PATCH", "DELETE"].includes(method)) {
    options.headers = { ...(options.headers || {}), "X-Runtime-Manager": "1" };
  }
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
  state.packs = await api("/api/packs");
  [state.assets, state.candidates, state.baselines, state.versions] = await Promise.all([
    api("/api/assets"),
    api("/api/candidates"),
    api("/api/baselines"),
    Promise.all(state.packs.map(async (pack) => {
      const versions = await api(`/api/packs/${encodeURIComponent(pack.id)}/versions`);
      return versions.map((version) => ({
        ...version,
        id: `${pack.id}@${version.version}`,
        kind: pack.kind,
        name: pack.name,
      }));
    })).then((groups) => groups.flat()),
  ]);
  render();
}

function render() {
  refill(".pack-options", state.packs, (item) => `${item.name} · ${item.kind}`);
  refill(".asset-options", state.assets, (item) => `${item.id} · ${item.mime_type}`);
  refill(
    ".character-version-options",
    state.versions.filter((item) => item.kind === "character"),
    (item) => `${item.name} · v${item.version}`,
    true,
  );
  refill(
    ".scene-version-options",
    state.versions.filter((item) => item.kind === "scene"),
    (item) => `${item.name} · v${item.version}`,
    true,
  );
  refill(
    ".canonical-options",
    state.candidates.filter((item) => item.is_current_canonical),
    (item) => `${item.id} · ${item.cast_key.slice(0, 10)}`,
  );
  refill(".candidate-options", state.candidates, (item) => `${item.id} · ${item.status}`, true);
  refill(
    ".cast-options",
    state.candidates
      .filter((item) => item.is_current_canonical)
      .map((item) => ({ ...item, id: item.cast_key })),
    (item) => `${candidateLabel(item)} · ${item.cast_key.slice(0, 10)}`,
  );

  const assets = document.querySelector("#assets");
  assets.replaceChildren(...state.assets.map(assetCard));

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

function assetCard(asset) {
  const card = document.createElement("article");
  const image = document.createElement("img");
  image.src = `/api/assets/${encodeURIComponent(asset.id)}/content`;
  image.alt = `Preview of ${asset.id}`;
  image.loading = "lazy";
  card.append(image);
  const id = document.createElement("code");
  id.textContent = asset.id;
  card.append(id);
  const detail = document.createElement("p");
  detail.textContent = `${asset.mime_type} · ${asset.size} bytes`;
  card.append(detail);
  card.append(
    actionButton("Copy ID", async () => {
      try {
        await navigator.clipboard.writeText(asset.id);
        show("Asset ID copied.");
      } catch (error) {
        show(`Copy failed: ${error.message}`, true);
      }
    }),
    actionButton("Use in version manifest", () => useAssetInManifest(asset.id)),
    actionButton("Select as candidate hero", () => selectAsset("#candidate-form [name=hero_asset_id]", asset.id)),
    actionButton("Select as generation reference", () => selectAsset("#generate-form [name=reference_asset_id]", asset.id)),
    actionButton("Select as variant hero", () => selectAsset("#variant-form [name=hero_asset_id]", asset.id)),
  );
  return card;
}

function useAssetInManifest(assetId) {
  const textarea = document.querySelector("#version-form [name=manifest]");
  try {
    const manifest = JSON.parse(textarea.value);
    if (!Array.isArray(manifest.asset_ids)) manifest.asset_ids = [];
    if (!manifest.asset_ids.includes(assetId)) manifest.asset_ids.push(assetId);
    textarea.value = JSON.stringify(manifest, null, 2);
    textarea.focus();
    show("Asset added to the version manifest.");
  } catch (error) {
    show(`Manifest JSON must be valid first: ${error.message}`, true);
  }
}

function selectAsset(selector, assetId) {
  const select = document.querySelector(selector);
  select.value = assetId;
  select.focus();
  show("Asset selected.");
}

function candidateCard(candidate) {
  const card = document.createElement("article");
  const image = document.createElement("img");
  image.src = `/api/assets/${encodeURIComponent(candidate.hero_asset_id)}/content`;
  image.alt = `Hero preview for ${candidate.id}`;
  image.className = "candidate-preview";
  card.append(image);
  card.innerHTML = `
    <h3>${escapeHtml(candidateLabel(candidate))}</h3>
    <p><code>${escapeHtml(candidate.id)}</code></p>
    <p><span class="status ${candidate.status}">${candidate.status}</span></p>
    <p>Hero: <code>${escapeHtml(candidate.hero_asset_id)}</code></p>
    <p>Cast: <code>${escapeHtml(candidate.cast_key)}</code></p>`;
  card.prepend(image);
  if (candidate.status === "draft") {
    const note = document.createElement("input");
    note.placeholder = "Review note";
    note.setAttribute("aria-label", `Review note for ${candidate.id}`);
    const verified = document.createElement("label");
    verified.innerHTML = '<input type="checkbox" name="invariants_verified"> Invariants verified';
    const approve = actionButton("Approve", () => reviewCandidate(
      candidate.id,
      "approve",
      note.value,
      false,
      verified.querySelector("input").checked,
    ));
    const canonical = actionButton("Approve canonical", () => reviewCandidate(candidate.id, "approve", note.value, true));
    const reject = actionButton("Reject", () => reviewCandidate(candidate.id, "reject", note.value, false));
    if (candidate.canonical_candidate_id) card.append(verified);
    card.append(note, approve);
    if (!candidate.canonical_candidate_id) card.append(canonical);
    card.append(reject);
  } else if (
    candidate.status === "approved"
    && !candidate.canonical_candidate_id
    && !candidate.is_current_canonical
  ) {
    card.append(actionButton("Make canonical", () => makeCanonical(candidate.id)));
  }
  return card;
}

function candidateLabel(candidate) {
  if (candidate.canonical_candidate_id) return candidate.theme || "Daily variant";
  if (candidate.is_current_canonical) return "Current canonical";
  if (candidate.status === "approved") return "Approved root";
  if (candidate.status === "rejected") return "Rejected root candidate";
  return "Draft root candidate";
}

function actionButton(label, handler) {
  const button = document.createElement("button");
  button.type = "button";
  button.textContent = label;
  button.onclick = handler;
  return button;
}

async function reviewCandidate(id, action, reviewNote, canonical, invariantsVerified = false) {
  try {
    await api(
      `/api/candidates/${encodeURIComponent(id)}/${action}`,
      jsonRequest("POST", action === "approve"
        ? { review_note: reviewNote, canonical, invariants_verified: invariantsVerified }
        : { review_note: reviewNote }),
    );
    show(`Candidate ${action}d.`);
    await refresh();
  } catch (error) { show(error.message, true); }
}

async function makeCanonical(id) {
  try {
    await api(`/api/candidates/${encodeURIComponent(id)}/canonical`, { method: "POST" });
    show("Canonical candidate selected.");
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
  const characterVersions = {};
  for (const slot of ["BOT1", "BOT2"]) {
    const selected = data.get(slot);
    if (!selected) continue;
    const record = state.versions.find((item) => item.id === selected);
    characterVersions[slot] = [record.pack_id, record.version];
  }
  const scene = state.versions.find((item) => item.id === data.get("scene"));
  return {
    character_versions: characterVersions,
    scene_pack_id: scene.pack_id,
    scene_version: scene.version,
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
  const scene = state.versions.find((item) => item.id === data.get("scene"));
  return api("/api/candidates/variants", jsonRequest("POST", {
    canonical_candidate_id: data.get("canonical_candidate_id"),
    hero_asset_id: data.get("hero_asset_id"),
    theme: data.get("theme"),
    changes: parseJson(form, "changes"),
    scene_pack_id: scene?.pack_id || null,
    scene_version: scene?.version || null,
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
