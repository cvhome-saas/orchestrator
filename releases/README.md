# Release manifests

One file per version, `vX.Y.Z.yaml`, written by the `Release` workflow (`scripts/release.py manifest`).
Every repo with `tag: true` in `repos.yaml` carries the same tag; the manifest records the commit each tag
points at and the commits of the validating repos. A release is a compatibility record: version X of every tagged repo
works with version X of the others. It does not deploy anything; what an environment runs is cvhome-platform's
concern. A manifest is never edited after the release; a correction is a new patch release.
