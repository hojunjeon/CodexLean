from codexlean.detector import detect_kind


def test_command_detection():
    assert detect_kind(("pytest", "-q"), "collected 1 item").kind == "test"
    assert detect_kind(("git", "status"), "On branch main").kind == "git_status"
    assert detect_kind(("git", "diff"), "diff --git a/a b/a").kind == "git_diff"
    assert detect_kind(("rg", "needle", "src"), "src/a.py:1:needle").kind == "search"
    assert detect_kind(("tail", "app.log"), "INFO start").kind == "log"
    assert detect_kind(("find", ".", "-type", "f"), "src/a.py").kind == "tree"


def test_json_detection():
    assert detect_kind((), '{"items": [1, 2]}').kind == "json"


def test_npm_run_build_is_not_misclassified_as_test():
    result = detect_kind(("npm", "run", "build"), "Build passed through test fixture data")
    assert result.kind != "test"
