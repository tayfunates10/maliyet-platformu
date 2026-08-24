"""Fail fast when the production release provenance contract becomes unsafe."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WORKFLOW = ROOT / ".github" / "workflows" / "release.yml"


def require(text: str, fragment: str) -> None:
    if fragment not in text:
        raise SystemExit(f"Production release contract is missing: {fragment}")


def forbid(text: str, fragment: str) -> None:
    if fragment in text:
        raise SystemExit(f"Production release contract contains forbidden text: {fragment}")


def main() -> None:
    text = WORKFLOW.read_text(encoding="utf-8")

    for fragment in (
        "workflow_dispatch:",
        'test "${GITHUB_REF}" = "refs/heads/main"',
        "packages: write",
        "id-token: write",
        "attestations: write",
        "docker/build-push-action@v6",
        "push: true",
        "provenance: mode=max",
        "sbom: true",
        "actions/attest-build-provenance@v2",
        "subject-digest: ${{ steps.api.outputs.digest }}",
        "subject-digest: ${{ steps.web.outputs.digest }}",
        "push-to-registry: true",
        '"git_sha": os.environ["GITHUB_SHA"]',
        '"digest": os.environ["API_DIGEST"]',
        '"digest": os.environ["WEB_DIGEST"]',
        "actions/upload-artifact@v4",
        "release-manifest.json",
    ):
        require(text, fragment)

    if text.count("docker/build-push-action@v6") != 2:
        raise SystemExit("Production release must build exactly API and web images")
    if text.count("actions/attest-build-provenance@v2") != 2:
        raise SystemExit("Production release must attest exactly API and web images")

    for forbidden in (
        "pull_request:",
        "branches: [main]",
        ":latest",
        "provenance: false",
        "sbom: false",
        "continue-on-error: true",
    ):
        forbid(text, forbidden)

    print("Production release contract: PASS")


if __name__ == "__main__":
    main()
