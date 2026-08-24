# Production release provenance

Production rollout accepts only digest-pinned API and web images. A release is therefore incomplete until both container digests are produced from canonical `main`, accompanied by provenance/SBOM attestations and an immutable manifest that records the exact Git commit and image digests.

## Release authority

Production images are published only by `.github/workflows/release.yml` through an explicit `workflow_dispatch` run on `refs/heads/main`. Pull requests, feature branches and arbitrary tags are not production release authorities.

The workflow publishes two GHCR images:

- `ghcr.io/<owner>/maliyet-platformu-api:sha-<git-sha>`
- `ghcr.io/<owner>/maliyet-platformu-web:sha-<git-sha>`

The tag is only a human-readable locator. Production rollout must consume the registry digest returned by the build, never the mutable tag.

## Supply-chain evidence

Each image build requires BuildKit provenance in `mode=max` and an SBOM. GitHub artifact attestation is also generated against the exact registry digest and pushed to the registry. The workflow needs only repository read, package write, OIDC and attestation write permissions.

The workflow writes `release-manifest.json` containing:

- schema version;
- exact Git SHA;
- API image name and `sha256:` digest;
- web image name and `sha256:` digest.

The manifest is uploaded as a GitHub Actions artifact. Operators copy only the repository names and 64-character digest values into the rollout environment after verifying the release run and attestations.

## Release-to-rollout handoff

1. Run the production release workflow on `main`.
2. Confirm both builds, SBOM/provenance generation, attestations and manifest upload succeed.
3. Read the API/web digests from the successful release output/manifest.
4. Supply `API_IMAGE_REPOSITORY`, `API_IMAGE_DIGEST`, `WEB_IMAGE_REPOSITORY` and `WEB_IMAGE_DIGEST` to the production host.
5. Run `python scripts/check_production_rollout_contract.py` in that exact runtime environment.
6. Follow `docs/operations/production-rollout.md` for the separate migration ceremony and fail-closed readiness/startup sequence.

Never substitute `latest`, a branch tag, a local rebuild or an unattested digest for the release outputs. A failed provenance/SBOM/attestation step means the release is not production-authorized.
