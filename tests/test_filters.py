import json

from codexlean.filters.git_output import GitStatusFilter
from codexlean.filters.json_output import JsonFilter
from codexlean.models import CompressionRequest, Profile


def test_git_status_preserves_every_changed_path():
    paths = [f"\tmodified:   src/f{i}.py" for i in range(100)]
    text = "\n".join(
        [
            "On branch main",
            "Changes not staged for commit:",
            '  (use "git add <file>..." to update what will be committed)',
            *paths,
        ]
    )
    candidate = GitStatusFilter().compress(
        text,
        CompressionRequest(raw=text.encode(), profile=Profile.SAFE),
        1.0,
    )
    for i in range(100):
        assert f"src/f{i}.py" in candidate.text
    assert "[unstaged M] 100" in candidate.text
    assert "grouped canonical git status" in candidate.notes


def test_json_strict_is_data_model_lossless():
    value = {"a": [1, 2, 3], "nested": {"ok": True}}
    text = json.dumps(value, indent=2)
    candidate = JsonFilter().compress(
        text,
        CompressionRequest(raw=text.encode(), profile=Profile.STRICT),
        1.0,
    )
    assert json.loads(candidate.text) == value


def test_search_groups_repeated_paths_without_losing_locations():
    from codexlean.filters.search_output import SearchFilter

    text = "\n".join(f"src/a.py:{i}:match {i}" for i in range(1, 30))
    text += "\n" + "\n".join(f"src/b.py:{i}:match {i}" for i in range(1, 30))
    candidate = SearchFilter().compress(
        text,
        CompressionRequest(raw=text.encode(), command=("rg", "match"), profile=Profile.SAFE),
        1.0,
    )
    assert candidate.text.count("## src/a.py") == 1
    assert candidate.text.count("## src/b.py") == 1
    assert "1:match 1" in candidate.text
    assert "src/a.py" in candidate.protected_lines


def test_search_keeps_exact_path_line_for_errors_and_symbol_definitions():
    from codexlean.filters.search_output import SearchFilter

    text = "\n".join(
        [f"src/module_{i % 7}.py:{10 + i}:handler_{i}()" for i in range(80)]
        + [
            "src/auth.py:42:raise AuthError('expired token accepted')",
            "src/auth.py:77:def validate_expiry(token):",
        ]
    )
    candidate = SearchFilter().compress(
        text,
        CompressionRequest(raw=text.encode(), command=("rg", "handler", "src"), profile=Profile.SAFE),
        1.0,
    )
    assert "src/auth.py:42:raise AuthError('expired token accepted')" in candidate.text
    assert "src/auth.py:77:def validate_expiry(token):" in candidate.text


def test_tree_hierarchy_is_reconstructed_before_sampling():
    from codexlean.filters.tree_output import TreeFilter

    rows = ["project", "├── README.md", "├── src"]
    for i in range(100):
        connector = "└──" if i == 99 else "├──"
        rows.append(f"│   {connector} module_{i:03d}.py")
    rows.extend(["└── tests", "    └── test_main.py", "2 directories, 102 files"])
    text = "\n".join(rows)
    candidate = TreeFilter().compress(
        text,
        CompressionRequest(raw=text.encode(), command=("tree",), profile=Profile.SAFE),
        1.0,
    )
    assert "- src/" in candidate.text
    assert "module_000.py" in candidate.text
    assert "module_099.py" in candidate.text
    assert "- tests/" in candidate.text
    assert "test_main.py" in candidate.text
    assert "README.md" in candidate.protected_lines
    assert "tree hierarchy reconstructed" in candidate.notes


def test_long_ls_listing_is_not_reinterpreted_as_paths():
    from codexlean.filters.tree_output import TreeFilter

    text = "\n".join(
        f"-rw-r--r-- 1 user group {i + 1} Jul 10 12:00 file_{i:03d}.txt"
        for i in range(100)
    )
    candidate = TreeFilter().compress(
        text,
        CompressionRequest(raw=text.encode(), command=("ls", "-l"), profile=Profile.SAFE),
        1.0,
    )
    assert "long listing protected" in candidate.notes
    assert "Filesystem listing:" not in candidate.text


def test_search_repeated_bodies_use_lossless_template_aliases():
    from codexlean.filters.search_output import SearchFilter

    body = "register_handler(route, middleware=auth_guard)"
    text = "\n".join(
        f"src/f{file_index}.py:{line}:{body}"
        for file_index in range(5)
        for line in range(1, 9)
    )
    candidate = SearchFilter().compress(
        text,
        CompressionRequest(raw=text.encode(), command=("rg", "register_handler"), profile=Profile.SAFE),
        1.0,
    )
    assert "[match templates]" in candidate.text
    assert body in candidate.text
    assert "@1" in candidate.text
    for file_index in range(5):
        assert f"## src/f{file_index}.py" in candidate.text

