#!/usr/bin/env python3
"""Block commits that contain secrets.

    scripts/check-secrets.py            # check staged files (used by .githooks/pre-commit)
    scripts/check-secrets.py --all      # check every tracked file

Rules:
  1. Secret-bearing files may not be committed at all: .env, *secrets*.json, kubeconfigs,
     k3s.yaml, private keys and certs (*.pem, *.key, id_rsa*, id_ed25519*, *.p12, *.pfx).
  2. Templates (.env.example, *.example.json) may only hold placeholder values.
  3. No file may contain high-confidence secret values (private keys, tokens, hashes, ...).
Findings show file:line and the rule name, never the value. Exit 1 blocks the commit.
Bypass for a reviewed false positive: add the path to .secrets-allowlist (one per line).
"""
import fnmatch
import json
import re
import subprocess
import sys

FORBIDDEN_FILES = [".env", "*/.env", "*secrets*.json", "*kubeconfig*", "k3s.yaml", "*/k3s.yaml",
                   "*.pem", "*.key", "*.p12", "*.pfx", "id_rsa*", "*/id_rsa*", "id_ed25519*",
                   "*/id_ed25519*", "*.token"]
TEMPLATES = ["*.example.json", "*secrets.example.json"]
PLACEHOLDER = re.compile(r"REPLACE_ME|your[_-]|change[_-]?me|example|<[^>]+>|^$", re.I)

VALUE_PATTERNS = [
    ("private-key", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("certificate", re.compile(r"-{5}BEGIN CERTIFICATE-{5}")),
    ("kubeconfig-credential", re.compile(r"(client-key-data|client-certificate-data|token):\s+[A-Za-z0-9+/=._-]{20,}")),
    ("certbot-dns-credential", re.compile(r"dns_[a-z0-9]+_(api_token|api_key|token|secret)\s*=\s*(?!REPLACE_ME)[A-Za-z0-9_-]{8,}", re.I)),
    ("github-token", re.compile(r"\b(ghp|gho|ghu|ghs|ghr|github_pat)_[A-Za-z0-9_]{20,}")),
    ("aws-access-key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("slack-token", re.compile(r"\bxox[abposr]-[A-Za-z0-9-]{10,}")),
    ("jwt", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    ("k3s-token", re.compile(r"\bK10[0-9a-f]{40,}")),
    ("password-hash", re.compile(r"\$\$?(2[aby]|apr1|6|5)\$\$?[./A-Za-z0-9]{8,}\$\$?[./A-Za-z0-9]{8,}")),
    ("discord-webhook", re.compile(r"discord(app)?\.com/api/webhooks/\d{10,}/[A-Za-z0-9_-]{30,}")),
    ("bearer-token", re.compile(r"\bBearer\s+[A-Za-z0-9._~+/-]{30,}")),
]


def git(*args) -> str:
    return subprocess.run(["git", *args], check=True, capture_output=True, text=True).stdout


def match_any(path, globs):
    name = path.rsplit("/", 1)[-1]
    return any(fnmatch.fnmatch(path, g) or fnmatch.fnmatch(name, g) for g in globs)


def is_template(path):
    return path.endswith(".env.example") or match_any(path, TEMPLATES)


def template_findings(path, text):
    out = []
    if path.endswith(".json"):
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return [f"{path}: template is not valid JSON"]

        def leaves(o, trail):
            if isinstance(o, dict):
                for k, v in o.items():
                    yield from leaves(v, trail + [k])
            elif isinstance(o, list):
                for i, v in enumerate(o):
                    yield from leaves(v, trail + [str(i)])
            else:
                yield ".".join(trail), o

        for key, v in leaves(data, []):
            if isinstance(v, str) and not PLACEHOLDER.search(v):
                out.append(f"{path}: '{key}' is not a placeholder (use REPLACE_ME)")
    else:  # KEY=value files
        for n, line in enumerate(text.splitlines(), 1):
            s = line.strip()
            if not s or s.startswith("#") or "=" not in s:
                continue
            key, v = s.split("=", 1)
            if re.search(r"(?i)pass|secret|token|key|hash|webhook", key) and not PLACEHOLDER.search(v):
                out.append(f"{path}:{n}: '{key}' is not a placeholder")
    return out


def main() -> int:
    all_files = "--all" in sys.argv
    if all_files:
        paths = [p for p in git("ls-files", "-z").split("\0") if p]
        read = lambda p: open(p, encoding="utf-8", errors="replace").read()
    else:
        paths = [p for p in git("diff", "--cached", "--name-only", "--diff-filter=ACMR", "-z").split("\0") if p]
        read = lambda p: git("show", f":{p}")
    try:
        allow = {l.strip() for l in open(".secrets-allowlist") if l.strip() and not l.startswith("#")}
    except FileNotFoundError:
        allow = set()

    findings = []
    for path in paths:
        if path in allow:
            continue
        if not is_template(path) and match_any(path, FORBIDDEN_FILES):
            findings.append(f"{path}: secret-bearing file type must not be committed")
            continue
        try:
            text = read(path)
        except (subprocess.CalledProcessError, OSError, UnicodeDecodeError):
            continue
        if "\0" in text[:8000]:
            continue  # binary
        if is_template(path):
            findings += template_findings(path, text)
        for n, line in enumerate(text.splitlines(), 1):
            for name, pat in VALUE_PATTERNS:
                if pat.search(line):
                    findings.append(f"{path}:{n}: looks like a {name}")
                    break

    if findings:
        print("Secret check failed; nothing is committed. Values are not shown:", file=sys.stderr)
        for f in findings:
            print("  " + f, file=sys.stderr)
        print("Keep secrets outside the repo (see npm-config/README.md). For a reviewed false\n"
              "positive, add the path to .secrets-allowlist.", file=sys.stderr)
        return 1
    print(f"secret check passed ({len(paths)} file(s))")
    return 0


if __name__ == "__main__":
    sys.exit(main())
