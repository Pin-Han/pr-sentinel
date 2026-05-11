import hashlib
import hmac
from dataclasses import dataclass

from fastapi import HTTPException, Request


@dataclass
class PREvent:
    action: str  # "opened" | "synchronize" | "reopened"
    repo_full_name: str  # "owner/repo"
    pr_number: int
    pr_title: str
    pr_description: str
    head_sha: str


ALLOWED_ACTIONS = {"opened", "synchronize", "reopened"}


def verify_signature(payload_body: bytes, signature_header: str | None, secret: str) -> None:
    """Verify GitHub webhook X-Hub-Signature-256."""
    if not signature_header:
        raise HTTPException(status_code=401, detail="Missing X-Hub-Signature-256 header")

    expected = "sha256=" + hmac.new(
        secret.encode(), payload_body, hashlib.sha256
    ).hexdigest()

    if not hmac.compare_digest(expected, signature_header):
        raise HTTPException(status_code=401, detail="Invalid signature")


async def parse_webhook(request: Request, webhook_secret: str) -> PREvent | None:
    """Parse and validate a GitHub webhook request.

    Returns PREvent if this is a PR event we should process, None otherwise.
    """
    payload_body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")
    verify_signature(payload_body, signature, webhook_secret)

    event_type = request.headers.get("X-GitHub-Event")
    if event_type != "pull_request":
        return None

    payload = await request.json()
    action = payload.get("action")
    if action not in ALLOWED_ACTIONS:
        return None

    pr = payload["pull_request"]
    return PREvent(
        action=action,
        repo_full_name=payload["repository"]["full_name"],
        pr_number=pr["number"],
        pr_title=pr["title"],
        pr_description=pr.get("body") or "",
        head_sha=pr["head"]["sha"],
    )
