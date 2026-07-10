# 기여 방법

## 개발 환경

```bash
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -e '.[test,benchmark]'
pytest -q
```

## 변경 원칙

- 토큰 절감보다 정확성과 복원 가능성을 우선합니다.
- 출력 생략을 추가할 때는 원문 복구와 fail-open 경로를 함께 검증합니다.
- 오류, 예외, assertion, 파일 경로, 행 번호 및 종료 코드가 손실되지 않아야 합니다.
- 새로운 필터에는 성공·실패·민감정보·짧은 출력 테스트를 추가합니다.
- 벤치마크 수치는 사용한 토크나이저와 코퍼스를 명시합니다.

## 제출 전 확인

```bash
pytest -q
python benchmarks/cross_benchmark.py
```

버그 보고에는 재현 가능한 최소 출력과 명령을 포함하되, 토큰·비밀번호·개인정보는 제거하십시오.
