# Windows

Windows PowerShell용 설치·제거 진입점입니다. 코어 소스는 루트 `src/`를 공유하므로 Linux와 동일한 압축·복구 엔진을 사용합니다.

## 요구 사항

- Windows 10/11
- Python 3.10+ 및 `py` launcher
- PowerShell 5.1+
- Codex Skill 연동 시 Codex CLI

## 설치

```powershell
git clone https://github.com/hojunjeon/CodexLean.git
cd CodexLean
.\windows\install.ps1
```

기본 설치 위치는 `%LOCALAPPDATA%\CodexLean\venv`, 실행 진입점은 `%USERPROFILE%\.local\bin\codexlean.cmd`입니다. 시스템 Python 패키지를 변경하지 않습니다.

프로젝트 범위 설치:

```powershell
$env:CODEXLEAN_SCOPE = "project"
$env:CODEXLEAN_PROJECT = "C:\path\to\repo"
.\windows\install.ps1
```

## 확인

```powershell
& "$HOME\.local\bin\codexlean.cmd" --version
& "$HOME\.local\bin\codexlean.cmd" doctor --scope user
```

## 제거

```powershell
.\windows\uninstall.ps1
```

프로젝트 범위 연동을 제거하려면 설치 때와 같은 환경 변수를 지정합니다.
