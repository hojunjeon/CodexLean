import os
from pathlib import Path

import codexlean


ROOT = Path(__file__).resolve().parents[1]


def test_platform_directories_have_documented_install_and_uninstall_entrypoints():
    expected = {
        "linux": ("install.sh", "uninstall.sh"),
        "windows": ("install.ps1", "uninstall.ps1"),
    }
    for platform, scripts in expected.items():
        directory = ROOT / platform
        assert (directory / "README.md").is_file()
        for script in scripts:
            assert (directory / script).is_file()
    if os.name != "nt":
        assert os.access(ROOT / "linux" / "install.sh", os.X_OK)
        assert os.access(ROOT / "linux" / "uninstall.sh", os.X_OK)


def test_platform_directories_share_one_core_instead_of_copying_it():
    assert (ROOT / "src" / "codexlean").is_dir()
    assert not (ROOT / "linux" / "src").exists()
    assert not (ROOT / "windows" / "src").exists()
    assert not (ROOT / "scripts").exists()


def test_package_and_runtime_versions_match():
    project = (ROOT / "pyproject.toml").read_text("utf-8")
    assert f'version = "{codexlean.__version__}"' in project


def test_packaged_skill_matches_repository_source():
    source = ROOT / "skills" / "codexlean"
    packaged = ROOT / "src" / "codexlean" / "resources" / "skill" / "codexlean"
    source_files = {path.relative_to(source) for path in source.rglob("*") if path.is_file()}
    packaged_files = {path.relative_to(packaged) for path in packaged.rglob("*") if path.is_file()}
    assert source_files == packaged_files
    for relative in source_files:
        assert (source / relative).read_bytes() == (packaged / relative).read_bytes()


def test_root_readme_routes_users_to_both_platforms():
    readme = (ROOT / "README.md").read_text("utf-8")
    for path in ("./linux/install.sh", ".\\windows\\install.ps1"):
        assert path in readme
