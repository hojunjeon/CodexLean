from pathlib import Path

from codexlean.installer import BEGIN, install, uninstall


def test_project_install_is_idempotent_and_reversible(tmp_path: Path):
    agents = tmp_path / "AGENTS.md"
    agents.write_text("# Existing\n\nKeep this.\n", "utf-8")

    first = install("project", tmp_path)
    second = install("project", tmp_path)
    assert (tmp_path / ".agents" / "skills" / "codexlean" / "SKILL.md").exists()
    text = agents.read_text("utf-8")
    assert text.count(BEGIN) == 1
    assert "Keep this." in text
    assert first["scope"] == second["scope"] == "project"

    result = uninstall("project", tmp_path)
    assert result["removed_skill"]
    assert BEGIN not in agents.read_text("utf-8")
    assert "Keep this." in agents.read_text("utf-8")
