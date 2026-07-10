# Security

## Local data

CodexLean stores exact command output locally only when a compact view omits information or a reversible presentation change is accepted. The default path is user-owned cache storage. No network telemetry is implemented.

Raw artifacts may contain source code, logs, personal data, or credentials. Controls:

- probable credential-bearing output is passed through and not stored by default
- common secret-bearing command arguments are redacted in metadata
- Unix directory/file permissions are restricted when supported
- artifacts are zlib-compressed and SHA-256 verified, but **not encrypted**
- default retention is seven days

For sensitive repositories, point `CODEXLEAN_STORE` to an encrypted volume or disable original storage. Selective omission then safely falls back to raw output.

```bash
export CODEXLEAN_STORE=/encrypted/path/codexlean.sqlite3
export CODEXLEAN_RETENTION_DAYS=1
```

Do not enable `CODEXLEAN_STORE_SECRETS=1` unless persistent local secret storage is acceptable.

## Command execution

`codexlean run -- ...` invokes the argument vector directly without a shell. Shell syntax, pipes, glob expansion, and redirection require an explicit trusted shell command, for example:

```bash
codexlean run -- sh -lc 'pytest -q 2>&1 | tee test.log'
```

Treat untrusted strings embedded in such shell commands as command-injection risks. CodexLean does not sanitize commands.

## Reporting

보안 문제는 GitHub 저장소의 Issue로 보고하되 실제 자격 증명이나 민감한 원문은 첨부하지 마십시오. 공개하기 어려운 취약점은 재현용 비밀정보를 제거한 최소 사례만 먼저 공유하십시오.
