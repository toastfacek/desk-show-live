(function exposeSelection(root) {
  const CHARACTER_V2_TEMPLATE = {
    schema_version: 2,
    visual_invariants: {
      locked_traits: ["silhouette", "eye_design", "proportions"],
      silhouette: "Broad rounded orange software sprite.",
      eye_design: "Two solid cream ovals, no pupils or inner marks.",
      proportions: "Low and wide; width is about 1.35 times height.",
    },
    persona: "Calm, dry, optimistic technical anchor.",
    writer_rules: ["Make one clear claim per thought."],
    voice_direction: "Low, measured, dry, warm, with restrained energy.",
    tts: {
      enabled: false,
      provider: null,
      voice_id: null,
      speed: null,
      pitch: null,
      pronunciations: [],
      max_duration_s: null,
      license: {
        broadcast_rights_confirmed: false,
        soundalike_or_cloned_person: false,
        notes: "",
      },
    },
    asset_ids: [],
  };

  const SCENE_V2_TEMPLATE = {
    schema_version: 2,
    set: "Warm studio",
    palette: ["orange", "cream"],
    lighting: "Soft key light",
    frame: { w: 1920, h: 1080, fps: 30 },
    reanchor_every: 60,
    asset_ids: [],
  };

  function manifestTemplateForKind(kind) {
    if (kind === "scene") {
      return structuredClone(SCENE_V2_TEMPLATE);
    }
    return structuredClone(CHARACTER_V2_TEMPLATE);
  }

  function manifestTemplateJsonForSelectedPack(packs, selectedPackId) {
    const selectedPack = packs.find((pack) => pack.id === selectedPackId);
    if (!selectedPack) return null;
    return JSON.stringify(manifestTemplateForKind(selectedPack.kind), null, 2);
  }

  function requestedCandidatesForCanonical(candidates, castKey) {
    const canonical = candidates.find(
      (item) => item.cast_key === castKey && item.is_current_canonical,
    );
    if (!canonical) return [];
    return [
      canonical,
      ...candidates.filter(
        (item) => item.canonical_candidate_id === canonical.id,
      ),
    ];
  }

  function requestedCandidateLabel(candidate) {
    const name = candidate.canonical_candidate_id
      ? candidate.theme || "Daily variant"
      : "Canonical";
    return `${name} · ${candidate.status}`;
  }

  const api = {
    CHARACTER_V2_TEMPLATE,
    SCENE_V2_TEMPLATE,
    manifestTemplateForKind,
    manifestTemplateJsonForSelectedPack,
    requestedCandidateLabel,
    requestedCandidatesForCanonical,
  };
  root.PackManagerSelection = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
}(typeof globalThis === "undefined" ? window : globalThis));
