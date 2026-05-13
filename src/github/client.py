import httpx

_BASE_URL = "https://api.github.com"


class GitHubClient:
    def __init__(self, token: str) -> None:
        self._client = httpx.AsyncClient(
            base_url=_BASE_URL,
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/vnd.github.v3+json",
                "X-GitHub-Api-Version": "2022-11-28",
            },
            timeout=30.0,
        )

    async def get_pr_info(self, repo: str, pr_number: int) -> dict:
        """Get PR metadata (title, body, head sha)."""
        resp = await self._client.get(f"/repos/{repo}/pulls/{pr_number}")
        resp.raise_for_status()
        data = resp.json()
        return {
            "title": data["title"],
            "body": data.get("body") or "",
            "head_sha": data["head"]["sha"],
        }

    async def get_pr_files(self, repo: str, pr_number: int) -> list[dict]:
        """Get list of changed files with patches.

        Returns list of {filename, status, patch} dicts.
        Handles pagination for PRs with many files.
        """
        files: list[dict] = []
        page = 1
        while True:
            resp = await self._client.get(
                f"/repos/{repo}/pulls/{pr_number}/files",
                params={"per_page": 100, "page": page},
            )
            resp.raise_for_status()
            page_data = resp.json()
            if not page_data:
                break
            files.extend(
                {
                    "filename": f["filename"],
                    "status": f["status"],
                    "patch": f.get("patch", ""),
                }
                for f in page_data
            )
            page += 1
        return files

    async def post_review(
        self, repo: str, pr_number: int, body: str, event: str = "COMMENT"
    ) -> None:
        """Post a review on a PR.

        event: "APPROVE" | "REQUEST_CHANGES" | "COMMENT"
        """
        resp = await self._client.post(
            f"/repos/{repo}/pulls/{pr_number}/reviews",
            json={"body": body, "event": event},
        )
        resp.raise_for_status()

    async def post_comment(self, repo: str, pr_number: int, body: str) -> None:
        """Post a regular comment on a PR (not a review)."""
        resp = await self._client.post(
            f"/repos/{repo}/issues/{pr_number}/comments",
            json={"body": body},
        )
        resp.raise_for_status()

    async def close(self) -> None:
        await self._client.aclose()
