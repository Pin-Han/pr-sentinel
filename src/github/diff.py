from dataclasses import dataclass, field
from fnmatch import fnmatch

SKIP_PATTERNS = [
    "*.lock",
    "*.min.js",
    "*.min.css",
    "*.map",
    "*.svg",
    "*.png",
    "*.jpg",
    "*.jpeg",
    "*.gif",
    "*.ico",
    "*.woff",
    "*.woff2",
    "*.ttf",
    "*.eot",
    "package-lock.json",
    "yarn.lock",
    "pnpm-lock.yaml",
    "poetry.lock",
    "Pipfile.lock",
    "*.pb.go",
    "*.generated.*",
]

# ~50K tokens, rough estimate 1 token ≈ 4 chars
MAX_DIFF_CHARS = 200_000


@dataclass
class ProcessedDiff:
    combined_diff: str
    included_files: list[str] = field(default_factory=list)
    skipped_files: list[str] = field(default_factory=list)
    truncated: bool = False


def _should_skip(filename: str) -> bool:
    return any(fnmatch(filename, pattern) for pattern in SKIP_PATTERNS)


def process_diff(files: list[dict]) -> ProcessedDiff:
    """Process PR files into a token-budget-aware combined diff.

    Files are included whole (never cut mid-hunk). When the budget is exhausted,
    remaining files are listed as skipped.
    """
    budget = MAX_DIFF_CHARS
    included: list[str] = []
    included_names: list[str] = []
    skipped_names: list[str] = []

    # Sort by patch size ascending so we can fit more small files
    sortable = sorted(files, key=lambda f: len(f.get("patch") or ""))

    for f in sortable:
        filename = f["filename"]
        patch = f.get("patch") or ""

        if not patch:
            skipped_names.append(filename)
            continue

        if _should_skip(filename):
            skipped_names.append(filename)
            continue

        file_diff = f"--- a/{filename}\n+++ b/{filename}\n{patch}\n"

        if len(file_diff) <= budget:
            included.append(file_diff)
            included_names.append(filename)
            budget -= len(file_diff)
        else:
            skipped_names.append(filename)

    combined = "\n".join(included)
    truncated = len(skipped_names) > 0 and budget <= 0

    return ProcessedDiff(
        combined_diff=combined,
        included_files=included_names,
        skipped_files=skipped_names,
        truncated=truncated,
    )
