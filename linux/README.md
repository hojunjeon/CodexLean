# Linux

Linux용 설치·제거 진입점입니다. 코어 소스는 루트 `src/`를 공유하며 플랫폼별 사본을 만들지 않아 기능 차이와 드리프트를 방지합니다.

## 요구 사항

- Python 3.10+
- `venv` 모듈 (`python3-venv` 패키지가 필요할 수 있음)
- Codex Skill 연동 시 Codex CLI

## 설치

```bash
git clone https://github.com/hojunjeon/CodexLean.git
cd CodexLean
./linux/install.sh
```

기본 설치 위치는 `~/.local/share/codexlean/venv`, 실행 파일은 `~/.local/bin/codexlean`입니다. 시스템 Python 패키지를 변경하지 않습니다.

프로젝트 범위 설치:

```bash
CODEXLEAN_SCOPE=project CODEXLEAN_PROJECT=/path/to/repo ./linux/install.sh
```

설치 위치 변경:

```bash
CODEXLEAN_HOME=/opt/codexlean CODEXLEAN_BIN_DIR="$HOME/bin" ./linux/install.sh
```

## 확인

```bash
~/.local/bin/codexlean --version
~/.local/bin/codexlean doctor --scope user
~/.local/bin/codexlean run -- pytest -q
```

## 제거

```bash
./linux/uninstall.sh
```

프로젝트 범위 연동을 제거하려면 설치 때와 같은 `CODEXLEAN_SCOPE` 및 `CODEXLEAN_PROJECT`를 지정합니다.
