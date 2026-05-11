from src.github.diff import MAX_DIFF_CHARS, ProcessedDiff, process_diff


def _make_file(name: str, patch_size: int = 100) -> dict:
    return {"filename": name, "status": "modified", "patch": "x" * patch_size}


class TestProcessDiff:
    def test_basic_files_included(self):
        files = [
            {"filename": "src/main.py", "status": "modified", "patch": "+print('hello')"},
            {"filename": "src/utils.py", "status": "modified", "patch": "+def foo(): pass"},
        ]
        result = process_diff(files)
        assert len(result.included_files) == 2
        assert "src/main.py" in result.included_files
        assert "src/utils.py" in result.included_files
        assert len(result.skipped_files) == 0

    def test_lockfiles_skipped(self):
        files = [
            {"filename": "src/main.py", "status": "modified", "patch": "+code"},
            {"filename": "package-lock.json", "status": "modified", "patch": "+lots of json"},
            {"filename": "yarn.lock", "status": "modified", "patch": "+lock content"},
            {"filename": "poetry.lock", "status": "modified", "patch": "+lock content"},
        ]
        result = process_diff(files)
        assert result.included_files == ["src/main.py"]
        assert "package-lock.json" in result.skipped_files
        assert "yarn.lock" in result.skipped_files
        assert "poetry.lock" in result.skipped_files

    def test_generated_files_skipped(self):
        files = [
            {"filename": "api.pb.go", "status": "modified", "patch": "+generated"},
            {"filename": "schema.generated.ts", "status": "modified", "patch": "+generated"},
            {"filename": "icon.svg", "status": "added", "patch": "+<svg>"},
        ]
        result = process_diff(files)
        assert len(result.included_files) == 0
        assert len(result.skipped_files) == 3

    def test_empty_patch_skipped(self):
        files = [
            {"filename": "binary.png", "status": "added", "patch": ""},
            {"filename": "src/main.py", "status": "modified", "patch": "+code"},
        ]
        result = process_diff(files)
        assert result.included_files == ["src/main.py"]
        assert "binary.png" in result.skipped_files

    def test_token_budget_respected(self):
        # Create files that exceed the budget
        big_patch = "x" * (MAX_DIFF_CHARS + 1)
        files = [
            {"filename": "small.py", "status": "modified", "patch": "+small change"},
            {"filename": "huge.py", "status": "modified", "patch": big_patch},
        ]
        result = process_diff(files)
        assert "small.py" in result.included_files
        assert "huge.py" in result.skipped_files

    def test_empty_file_list(self):
        result = process_diff([])
        assert result.combined_diff == ""
        assert result.included_files == []
        assert result.skipped_files == []

    def test_diff_format_contains_file_headers(self):
        files = [
            {"filename": "src/app.py", "status": "modified", "patch": "+new code"},
        ]
        result = process_diff(files)
        assert "--- a/src/app.py" in result.combined_diff
        assert "+++ b/src/app.py" in result.combined_diff
