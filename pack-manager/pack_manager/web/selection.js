(function exposeSelection(root) {
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
    requestedCandidateLabel,
    requestedCandidatesForCanonical,
  };
  root.PackManagerSelection = api;
  if (typeof module !== "undefined" && module.exports) module.exports = api;
}(typeof globalThis === "undefined" ? window : globalThis));
