# Release manifests

One file per version, `vX.Y.Z.yaml`, written by the `Release` workflow (`scripts/release.py manifest`).
Every repo with `tag: true` in `repos.yaml` carries the same tag; the manifest records the commit each tag
points at and the commits of the validating repos. `envs/<env>.tfvars` `image_tag` in cvhome-platform must
name a version that has a manifest here (`scripts/contract-check.py --only release`). A manifest is never
edited after the release; a correction is a new patch release.
