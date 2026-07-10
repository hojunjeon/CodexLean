from __future__ import annotations

import os
import shutil
import sys
from importlib import resources
from pathlib import Path

BEGIN = "<!-- codexlean:begin -->"
END = "<!-- codexlean:end -->"
AGENTS_BLOCK = f"""{BEGIN}
## CodexLean
For commands likely to emit more than 40 lines (tests, builds, searches, logs, listings), use `codexlean run -- <command>`. When output is compressed and omitted detail could affect a decision, inspect the exact original with `codexlean show <id>` or `codexlean show <id> --grep <pattern>`. Use direct commands for interactive, binary, or already short output. Keep final responses compact: result first; no greetings, tool narration, or repeated recap; preserve code, identifiers, commands, paths, and exact error strings.
{END}
"""


def _skill_source() -> Path:
    root = resources.files("codexlean").joinpath("resources/skill/codexlean")
    # as_file supports zipped distributions as well as editable installs.
    context = resources.as_file(root)
    path = context.__enter__()
    # Keep context alive for process lifetime; installer is short-lived.
    _RESOURCE_CONTEXTS.append(context)
    return path


_RESOURCE_CONTEXTS: list[object] = []


def _update_agents(path: Path) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    existing = path.read_text("utf-8") if path.exists() else ""
    if BEGIN in existing and END in existing:
        before, remainder = existing.split(BEGIN, 1)
        _, after = remainder.split(END, 1)
        updated = before.rstrip() + "\n\n" + AGENTS_BLOCK + after.lstrip("\n")
    else:
        separator = "\n\n" if existing.strip() else ""
        updated = existing.rstrip() + separator + AGENTS_BLOCK
    if updated == existing:
        return False
    if path.exists():
        backup = path.with_suffix(path.suffix + ".codexlean.bak")
        shutil.copy2(path, backup)
    path.write_text(updated, "utf-8")
    return True


def _remove_agents_block(path: Path) -> bool:
    if not path.exists():
        return False
    existing = path.read_text("utf-8")
    if BEGIN not in existing or END not in existing:
        return False
    before, remainder = existing.split(BEGIN, 1)
    _, after = remainder.split(END, 1)
    updated = (before.rstrip() + "\n\n" + after.lstrip()).strip()
    if updated:
        path.write_text(updated + "\n", "utf-8")
    else:
        path.unlink()
    return True


def target_paths(scope: str, project: Path | None = None) -> tuple[Path, Path]:
    if scope == "user":
        skill = Path.home() / ".agents" / "skills" / "codexlean"
        agents = Path(os.getenv("CODEX_HOME", Path.home() / ".codex")) / "AGENTS.md"
        return skill, agents
    root = (project or Path.cwd()).resolve()
    return root / ".agents" / "skills" / "codexlean", root / "AGENTS.md"


def install(scope: str, project: Path | None = None, add_agents: bool = True) -> dict[str, object]:
    skill_target, agents_target = target_paths(scope, project)
    skill_target.parent.mkdir(parents=True, exist_ok=True)
    if skill_target.exists():
        shutil.rmtree(skill_target)
    shutil.copytree(_skill_source(), skill_target)
    agents_changed = _update_agents(agents_target) if add_agents else False
    return {
        "scope": scope,
        "skill": str(skill_target),
        "agents": str(agents_target) if add_agents else None,
        "agents_changed": agents_changed,
    }


def uninstall(scope: str, project: Path | None = None) -> dict[str, object]:
    skill_target, agents_target = target_paths(scope, project)
    removed_skill = False
    if skill_target.exists():
        shutil.rmtree(skill_target)
        removed_skill = True
    removed_agents = _remove_agents_block(agents_target)
    return {
        "scope": scope,
        "skill": str(skill_target),
        "removed_skill": removed_skill,
        "agents": str(agents_target),
        "removed_agents_block": removed_agents,
    }


def doctor(scope: str = "user", project: Path | None = None) -> list[tuple[str, bool, str]]:
    skill_target, agents_target = target_paths(scope, project)
    executable = shutil.which("codexlean")
    if executable is None:
        adjacent = Path(sys.executable).with_name("codexlean" + (".exe" if os.name == "nt" else ""))
        if adjacent.exists():
            executable = str(adjacent)
    checks = [
        ("Python", sys.version_info >= (3, 10), sys.version.split()[0]),
        ("codexlean on PATH", executable is not None, executable or "not found"),
        ("Codex skill", (skill_target / "SKILL.md").exists(), str(skill_target)),
        (
            "AGENTS guidance",
            agents_target.exists() and BEGIN in agents_target.read_text("utf-8"),
            str(agents_target),
        ),
    ]
    return checks
