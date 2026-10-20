// A single owner also covers detached Audio objects used for authenticated blobs.
let owner: { stop: () => void } | null = null;
export function claimAudioPreview(stop: () => void) {
  owner?.stop();
  const next = { stop };
  owner = next;
  return () => {
    if (owner === next) owner = null;
  };
}
