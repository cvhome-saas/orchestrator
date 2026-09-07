# Release manifests

One file per product version, `vX.Y.Z.yaml`, written by the `Release product` workflow
(`scripts/release.py manifest`). A manifest is the answer to "what does version X.Y.Z consist of":

- `cvhome` / `cvhome-platform`: the lockstep tag and the commit it points at
- `images`: every image cvhome's `release-images.yml` pushed for the tag, with digests
- `components`: the versions of saas-gateway, caddy-domainlookup, certmagic-s3, aws-otel-collector and lcl the
  product was validated with (latest tag at release time, or `--pin` overrides)
- `validated_by`: the load-testing / e2e-testing commits and results
- `contract_check`: result of `scripts/contract-check.py` at the tag pair

`envs/<env>.tfvars` `image_tag` in cvhome-platform must name a version that has a manifest here;
`scripts/contract-check.py --only release` enforces it. Manifests are never edited by hand after the
release; a correction is a new patch release.
