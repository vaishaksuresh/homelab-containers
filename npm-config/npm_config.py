#!/usr/bin/env python3
"""Nginx Proxy Manager config as code for *.heb.bet. The repo is the source of truth.

    npm_config.py export                          # NPM -> files (fails closed on secrets)
    npm_config.py apply --dry-run                 # show what would change
    npm_config.py apply                           # certs -> access lists -> hosts
    npm_config.py apply --agree-letsencrypt-tos   # needed when certs must be requested
    npm_config.py apply --prune                   # ...and delete in-scope hosts with no file

Auth: set NPM_TOKEN to a bearer token, or run interactively and you'll be prompted
for the NPM admin email and password (read with getpass, never stored or printed).

Bootstrap secrets (only needed to create certs or access-list users): set
NPM_BOOTSTRAP_SECRETS to a JSON file outside the repo (see bootstrap-secrets.example.json).
Only the Python standard library is used.
"""
from __future__ import annotations

import argparse
import difflib
import getpass
import json
import os
import re
import stat
import sys
import urllib.error
import urllib.request
from pathlib import Path

API = os.environ.get("NPM_API", "http://10.0.20.200:81/api").rstrip("/")
ZONE = os.environ.get("NPM_ZONE", "heb.bet").lower()
ROOT = Path(__file__).resolve().parent
HOSTS = ROOT / "hosts"
CERTS_FILE = ROOT / "certificates.json"
ACLS_FILE = ROOT / "access-lists.json"

# Host types, in dependency-safe apply order. Kept fields per type; everything else
# (id, created_on, modified_on, owner, meta, expanded objects, ...) is dropped.
KINDS = {
    "proxy": {
        "path": "nginx/proxy-hosts",
        "expand": "certificate,access_list",
        "fields": ["domain_names", "forward_scheme", "forward_host", "forward_port",
                   "caching_enabled", "block_exploits", "allow_websocket_upgrade",
                   "http2_support", "hsts_enabled", "hsts_subdomains", "ssl_forced",
                   "advanced_config", "locations"],
    },
    "redirection": {
        "path": "nginx/redirection-hosts",
        "expand": "certificate",
        "fields": ["domain_names", "forward_scheme", "forward_domain_name",
                   "forward_http_code", "preserve_path", "block_exploits", "http2_support",
                   "hsts_enabled", "hsts_subdomains", "ssl_forced", "advanced_config"],
    },
    "dead": {  # "404 hosts" in the UI
        "path": "nginx/dead-hosts",
        "expand": "certificate",
        "fields": ["domain_names", "http2_support", "hsts_enabled", "hsts_subdomains",
                   "ssl_forced", "advanced_config"],
    },
    "stream": {
        "path": "nginx/streams",
        "expand": "certificate",
        "fields": ["incoming_port", "forwarding_host", "forwarding_port",
                   "tcp_forwarding", "udp_forwarding"],
    },
}
LOCATION_FIELDS = ["path", "forward_scheme", "forward_host", "forward_port", "advanced_config"]
BOOL_FIELDS = {"caching_enabled", "block_exploits", "allow_websocket_upgrade", "http2_support",
               "hsts_enabled", "hsts_subdomains", "ssl_forced", "preserve_path",
               "tcp_forwarding", "udp_forwarding"}
META_KEYS = {"certificate", "access_list", "enabled"}  # our own keys in host files
CERT_KEYS = {"domain_names", "provider", "nice_name", "expires_on", "dns_challenge",
             "dns_provider", "propagation_seconds"}
ACL_KEYS = {"name", "satisfy_any", "pass_auth", "clients", "users"}

# Fail-closed secret patterns. Values are never printed, only file:line and pattern name.
SECRET_PATTERNS = [
    ("pem-block", re.compile(r"-----BEGIN [A-Z0-9 ]*(PRIVATE KEY|CERTIFICATE)")),
    ("secret-like-key", re.compile(
        r'"[a-z0-9_]*(password|passwd|secret|token|api_?key|credential|private)[a-z0-9_]*"\s*:', re.I)),
    ("secret-assignment", re.compile(
        r"(password|passwd|secret|token|api[_-]?key)\s*[=:]\s*\S{6,}", re.I)),
    ("auth-header", re.compile(r"\b(authorization|bearer|basic)\b[\s:\"']+[A-Za-z0-9+/=._-]{8,}", re.I)),
    ("password-hash", re.compile(r"\$(2[aby]|1|5|6|apr1)\$[./A-Za-z0-9]{4,}")),
    ("jwt", re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}")),
    ("email", re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(\.[A-Za-z0-9-]+)+")),
    ("long-random-string", re.compile(r"(?<![A-Za-z0-9+/_-])[A-Za-z0-9+/_-]{40,}={0,2}")),
]


def die(msg: str, code: int = 1):
    print(f"error: {msg}", file=sys.stderr)
    sys.exit(code)


# ---------------------------------------------------------------- API client
class NPM:
    def __init__(self, api: str, token: str):
        self.api, self.token = api, token

    def req(self, method: str, path: str, body=None, auth: bool = True, timeout: int = 30):
        data = json.dumps(body).encode() if body is not None else None
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        if auth:
            headers["Authorization"] = f"Bearer {self.token}"
        r = urllib.request.Request(f"{self.api}/{path}", data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(r, timeout=timeout) as resp:
                raw = resp.read()
                return json.loads(raw) if raw.strip() else None
        except urllib.error.HTTPError as e:
            detail = e.read().decode(errors="replace")[:300]
            raise RuntimeError(f"{method} /{path.split('?')[0]}: HTTP {e.code}: {detail}") from None
        except urllib.error.URLError as e:
            die(f"cannot reach NPM at {self.api}: {e.reason}")

    def list(self, path: str, expand: str = ""):
        if expand:
            try:
                return self.req("GET", f"{path}?expand={expand}") or []
            except RuntimeError:
                pass  # older NPM versions reject some expands
        return self.req("GET", path) or []


def login(api: str) -> NPM:
    token = os.environ.get("NPM_TOKEN", "").strip()
    client = NPM(api, token)
    if token:
        return client
    if not sys.stdin.isatty():
        die("set NPM_TOKEN or run in an interactive terminal to log in")
    ident = input("NPM admin email: ").strip()
    secret = getpass.getpass("NPM admin password: ")
    try:
        resp = client.req("POST", "tokens", {"identity": ident, "secret": secret}, auth=False)
    except RuntimeError:
        die("NPM login failed")
    finally:
        del secret
    client.token = (resp or {}).get("token") or die("NPM login returned no token")
    return client


class Secrets:
    """Bootstrap secrets, loaded lazily from $NPM_BOOTSTRAP_SECRETS. Never printed."""

    def __init__(self):
        self._data = None

    def _load(self):
        if self._data is None:
            p = os.environ.get("NPM_BOOTSTRAP_SECRETS")
            if not p:
                raise RuntimeError("needs bootstrap secrets: set NPM_BOOTSTRAP_SECRETS to a JSON "
                                   "file outside the repo (see bootstrap-secrets.example.json)")
            path = Path(p).expanduser().resolve()
            if ROOT.parent in path.parents:
                raise RuntimeError("refusing to read bootstrap secrets from inside the repo")
            if path.stat().st_mode & (stat.S_IRWXG | stat.S_IRWXO):
                print(f"warning: {path} is readable by others; chmod 600 it", file=sys.stderr)
            self._data = json.loads(path.read_text())
        return self._data

    def letsencrypt_email(self) -> str:
        v = self._load().get("letsencrypt_email")
        if not v:
            raise RuntimeError("bootstrap secrets file has no letsencrypt_email")
        return v

    def dns_credentials(self, provider: str) -> str:
        v = (self._load().get("dns_credentials") or {}).get(provider)
        if not v:
            raise RuntimeError(f"bootstrap secrets file has no dns_credentials.{provider}")
        return v

    def acl_password(self, acl: str, user: str) -> str:
        v = ((self._load().get("access_list_passwords") or {}).get(acl) or {}).get(user)
        if not v:
            raise RuntimeError(f"bootstrap secrets file has no access_list_passwords.{acl}.{user}")
        return v


# ---------------------------------------------------------------- normalisation
def in_zone(domain: str) -> bool:
    d = domain.lower()
    return d == ZONE or d.endswith("." + ZONE)


def in_scope(kind: str, h: dict) -> bool:
    # Streams have no domain names, so all streams are in scope.
    return kind == "stream" or any(in_zone(d) for d in h.get("domain_names") or [])


def domains(obj: dict) -> list[str]:
    return sorted(d.lower() for d in obj.get("domain_names") or [])


def normalize_cert(c: dict) -> dict:
    meta = c.get("meta") or {}
    out = {"domain_names": domains(c), "provider": c.get("provider") or "letsencrypt",
           "nice_name": c.get("nice_name") or "", "expires_on": c.get("expires_on")}
    if out["provider"] == "letsencrypt":
        out["dns_challenge"] = bool(meta.get("dns_challenge"))
        if out["dns_challenge"]:
            out["dns_provider"] = meta.get("dns_provider") or ""
            if meta.get("propagation_seconds") not in (None, ""):
                out["propagation_seconds"] = int(meta["propagation_seconds"])
    return out


def normalize_acl(a: dict) -> dict:
    return {
        "name": a["name"],
        "satisfy_any": bool(a.get("satisfy_any")),
        "pass_auth": bool(a.get("pass_auth")),
        "clients": sorted(({"address": c["address"], "directive": c["directive"]}
                           for c in a.get("clients") or []),
                          key=lambda c: (c["directive"], c["address"])),
        "users": sorted({i["username"] for i in a.get("items") or [] if i.get("username")}),
    }


def normalize(kind: str, h: dict, certs_by_id: dict, acls_by_id: dict) -> dict:
    out = {}
    for f in KINDS[kind]["fields"]:
        if f not in h:
            continue
        v = h[f]
        if f in BOOL_FIELDS:
            v = bool(v)
        elif f == "domain_names":
            v = sorted(d.lower() for d in v or [])
        elif f == "advanced_config":
            v = v or ""
        elif f == "locations":
            v = [{lf: (loc.get(lf) or "") if lf == "advanced_config" else loc.get(lf)
                  for lf in LOCATION_FIELDS if lf in loc} for loc in v or []]
        out[f] = v
    if kind != "stream" or "certificate_id" in h:
        cid = h.get("certificate_id") or 0
        if cid and cid not in certs_by_id:
            raise RuntimeError(f"{kind} host references unknown certificate id {cid}")
        out["certificate"] = domains(certs_by_id[cid]) if cid else None
    if kind == "proxy":
        aid = h.get("access_list_id") or 0
        if aid and aid not in acls_by_id:
            raise RuntimeError(f"proxy host references unknown access list id {aid}")
        out["access_list"] = acls_by_id[aid]["name"] if aid else None
    out["enabled"] = bool(h.get("enabled", True))
    return out


def identity(kind: str, d: dict):
    if kind == "stream":
        return ("port", int(d["incoming_port"]))
    return tuple(sorted(x.lower() for x in d["domain_names"]))


def filename(kind: str, d: dict) -> str:
    if kind == "stream":
        return f"{int(d['incoming_port'])}.json"
    first = sorted(d["domain_names"])[0].replace("*", "_wildcard")
    return re.sub(r"[^a-z0-9._-]", "_", first) + ".json"


def dump(obj) -> str:
    return json.dumps(obj, indent=2, sort_keys=True, ensure_ascii=False) + "\n"


def fetch_state(npm: NPM):
    certs = npm.list("nginx/certificates")
    acls = npm.list("nginx/access-lists", "items,clients")
    certs_by_id = {c["id"]: c for c in certs}
    acls_by_id = {a["id"]: a for a in acls}
    hosts = {}
    for kind, k in KINDS.items():
        rows = {}
        for h in npm.list(k["path"], k["expand"]):
            if in_scope(kind, h):
                n = normalize(kind, h, certs_by_id, acls_by_id)
                rows[identity(kind, n)] = (h["id"], n)
        hosts[kind] = rows
    cert_state = {tuple(domains(c)): (c["id"], normalize_cert(c)) for c in certs}
    acl_state = {a["name"]: (a["id"], normalize_acl(a)) for a in acls}
    return hosts, cert_state, acl_state


# ---------------------------------------------------------------- secret scan
def _looks_random(s: str) -> bool:
    # Keys/tokens mix upper, lower and digits; plain paths and hostnames usually don't.
    return bool(re.search(r"[A-Z]", s) and re.search(r"[a-z]", s) and re.search(r"[0-9]", s))


def scan(files: dict[str, str]) -> list[str]:
    hits = []
    for rel, text in sorted(files.items()):
        for lineno, line in enumerate(text.splitlines(), 1):
            for name, pat in SECRET_PATTERNS:
                for m in pat.finditer(line):
                    if name == "long-random-string" and not _looks_random(m.group(0)):
                        continue
                    hits.append(f"{rel}:{lineno}: matches '{name}'")
                    break
    return hits


# ---------------------------------------------------------------- export
def cmd_export(args) -> int:
    npm = login(args.api)
    hosts, cert_state, acl_state = fetch_state(npm)
    files: dict[str, str] = {}
    used_certs, used_acls = set(), set()
    for kind, rows in hosts.items():
        for _, (_, n) in rows.items():
            rel = f"hosts/{kind}/{filename(kind, n)}"
            if rel in files:
                raise RuntimeError(f"two {kind} hosts map to the same file {rel}")
            files[rel] = dump(n)
            if n.get("certificate"):
                used_certs.add(tuple(n["certificate"]))
            if n.get("access_list"):
                used_acls.add(n["access_list"])
        if kind == "stream" and rows:
            print(f"note: exported all {len(rows)} stream(s); streams have no domain to filter on")
    certs = [n for key, (_, n) in cert_state.items() if key in used_certs or any(in_zone(d) for d in key)]
    files["certificates.json"] = dump(sorted(certs, key=lambda c: c["domain_names"]))
    files["access-lists.json"] = dump(sorted((acl_state[a][1] for a in used_acls), key=lambda a: a["name"]))

    hits = scan(files)
    if hits:
        print("Refusing to write: output contains secret-looking content.", file=sys.stderr)
        print("Nothing was written. Fix these in NPM (e.g. move credentials out of", file=sys.stderr)
        print("advanced config) and export again:", file=sys.stderr)
        for h in hits:
            print("  " + h, file=sys.stderr)
        return 3

    for kind in KINDS:  # write, and remove files for hosts that no longer exist in NPM
        d = HOSTS / kind
        d.mkdir(parents=True, exist_ok=True)
        keep = {Path(r).name for r in files if r.startswith(f"hosts/{kind}/")}
        for old in d.glob("*.json"):
            if old.name not in keep:
                old.unlink()
                print(f"removed  {old.relative_to(ROOT)}")
        (d / ".gitkeep").touch()
    for rel, text in sorted(files.items()):
        p = ROOT / rel
        before = p.read_text() if p.exists() else None
        if before != text:
            tmp = p.with_suffix(p.suffix + ".tmp")
            tmp.write_text(text)
            tmp.replace(p)
            print(f"{'updated' if before is not None else 'wrote  '}  {rel}")
    counts = ", ".join(f"{k}={len(v)}" for k, v in hosts.items())
    print(f"export done (certificates={len(certs)}, access_lists={len(used_acls)}, {counts}); "
          "secret scan clean")
    return 0


# ---------------------------------------------------------------- apply
def load_json_list(path: Path, allowed: set, keyname: str, errors: list) -> dict:
    out = {}
    if not path.exists():
        return out
    try:
        items = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        errors.append(f"{path.name}: invalid JSON: {e}")
        return out
    for i, obj in enumerate(items):
        unknown = set(obj) - allowed
        if unknown:
            errors.append(f"{path.name}[{i}]: unknown keys {sorted(unknown)}")
            continue
        key = tuple(sorted(obj["domain_names"])) if keyname == "domain_names" else obj[keyname]
        if key in out:
            errors.append(f"{path.name}[{i}]: duplicate {key}")
        out[key] = obj
    return out


def load_desired():
    errors: list[str] = []
    certs = load_json_list(CERTS_FILE, CERT_KEYS, "domain_names", errors)
    acls = load_json_list(ACLS_FILE, ACL_KEYS, "name", errors)
    hosts = {k: {} for k in KINDS}
    allowed = {k: set(v["fields"]) | META_KEYS for k, v in KINDS.items()}
    for kind in KINDS:
        d = HOSTS / kind
        if not d.is_dir():
            continue
        for f in sorted(d.glob("*.json")):
            rel = str(f.relative_to(ROOT))
            try:
                obj = json.loads(f.read_text())
            except json.JSONDecodeError as e:
                errors.append(f"{rel}: invalid JSON: {e}")
                continue
            unknown = set(obj) - allowed[kind]
            if unknown:
                errors.append(f"{rel}: unknown keys {sorted(unknown)}")
                continue
            if kind != "stream" and not any(in_zone(x) for x in obj.get("domain_names", [])):
                errors.append(f"{rel}: no *.{ZONE} domain; out of scope")
                continue
            key = identity(kind, obj)
            if key in hosts[kind]:
                errors.append(f"{rel}: duplicate of {hosts[kind][key][0]}")
                continue
            if obj.get("certificate") and tuple(sorted(obj["certificate"])) not in certs:
                errors.append(f"{rel}: certificate {obj['certificate']} is not in certificates.json")
            if obj.get("access_list") and obj["access_list"] not in acls:
                errors.append(f"{rel}: access list '{obj['access_list']}' is not in access-lists.json")
            hosts[kind][key] = (rel, obj)
    return certs, acls, hosts, errors


def show_diff(label, old, new):
    a = dump(old).splitlines(keepends=True) if old is not None else []
    b = dump(new).splitlines(keepends=True)
    sys.stdout.writelines(difflib.unified_diff(a, b, f"npm:{label}", f"file:{label}"))


def host_payload(kind, d, cert_ids, acl_ids, creating):
    p = {f: d[f] for f in KINDS[kind]["fields"] if f in d}
    if "certificate" in d:
        p["certificate_id"] = cert_ids[tuple(sorted(d["certificate"]))] if d["certificate"] else 0
    if kind == "proxy":
        p["access_list_id"] = acl_ids[d["access_list"]] if d.get("access_list") else 0
    if creating and kind != "stream":
        p["meta"] = {}
    return p


class Applier:
    def __init__(self, npm, args):
        self.npm, self.args, self.secrets = npm, args, Secrets()
        self.mode = "DRY RUN: " if args.dry_run else ""
        self.stats = {k: 0 for k in ("create", "update", "unchanged", "delete", "failed")}
        self.needs: list[str] = []

    def secret(self, what: str, fn, *a):
        """Fetch a bootstrap secret. In a dry run without a secrets file, just record the need."""
        if self.args.dry_run and not os.environ.get("NPM_BOOTSTRAP_SECRETS"):
            self.needs.append(what)
            return "<from secrets file>"
        return fn(*a)

    def fail(self, label, err):
        self.stats["failed"] += 1
        print(f"  failed {label}: {err}", file=sys.stderr)

    # 1. certificates: create missing ones (never updated or deleted; NPM renews them)
    def certs(self, desired, state, cert_ids):
        for key, want in desired.items():
            label = f"certificate {list(key)}"
            if key in state:
                have = state[key][1]
                drift = {k for k in ("provider", "dns_challenge", "dns_provider")
                         if want.get(k) != have.get(k)}
                if drift:
                    print(f"note: {label} exists but differs in {sorted(drift)}; not changed")
                self.stats["unchanged"] += 1
                continue
            how = (f"dns:{want.get('dns_provider')}" if want.get("dns_challenge") else "http-01")
            print(f"{self.mode}create {label} via {want.get('provider')} ({how})")
            try:
                if want.get("provider") != "letsencrypt":
                    raise RuntimeError("custom certificates can't be recreated from metadata; "
                                       "upload the cert and key in the NPM UI")
                meta = {"letsencrypt_email": self.secret("letsencrypt_email", self.secrets.letsencrypt_email),
                        "dns_challenge": bool(want.get("dns_challenge"))}
                if meta["dns_challenge"]:
                    meta["dns_provider"] = want["dns_provider"]
                    meta["dns_provider_credentials"] = self.secret(
                        f"dns_credentials.{want['dns_provider']}", self.secrets.dns_credentials, want["dns_provider"])
                    if want.get("propagation_seconds"):
                        meta["propagation_seconds"] = want["propagation_seconds"]
                if not self.args.agree_letsencrypt_tos and self.args.dry_run:
                    self.needs.append("--agree-letsencrypt-tos")
                elif not self.args.agree_letsencrypt_tos:
                    raise RuntimeError("requesting a Let's Encrypt cert requires --agree-letsencrypt-tos")
                meta["letsencrypt_agree"] = True
                if self.args.dry_run:
                    cert_ids[key] = -1
                else:
                    body = {"provider": "letsencrypt", "nice_name": want.get("nice_name") or "",
                            "domain_names": list(key), "meta": meta}
                    created = self.npm.req("POST", "nginx/certificates", body, timeout=600)
                    cert_ids[key] = created["id"]
                self.stats["create"] += 1
            except RuntimeError as e:
                self.fail(label, e)

    # 2. access lists: create missing, update rules; existing users' passwords are left alone
    def acls(self, desired, state, acl_ids):
        for name, want in desired.items():
            label = f"access-list {name}"
            have = state.get(name, (None, None))[1]
            if have == want:
                self.stats["unchanged"] += 1
                continue
            action = "update" if have else "create"
            print(f"{self.mode}{action} {label}")
            show_diff(label, have, want)
            try:
                body = {"name": name, "satisfy_any": want["satisfy_any"],
                        "pass_auth": want["pass_auth"], "clients": want["clients"]}
                new_users = set(want["users"]) - set(have["users"] if have else [])
                removed = set(have["users"] if have else []) - set(want["users"])
                if new_users or removed or not have:
                    # NPM replaces the whole user list when items are sent; existing users keep
                    # their stored password when sent with an empty one.
                    body["items"] = [{"username": u,
                                      "password": self.secret(f"access_list_passwords.{name}.{u}",
                                                              self.secrets.acl_password, name, u)
                                      if u in new_users else ""}
                                     for u in want["users"]]
                if self.args.dry_run:
                    acl_ids.setdefault(name, -1)
                elif have:
                    self.npm.req("PUT", f"nginx/access-lists/{state[name][0]}", body)
                else:
                    acl_ids[name] = self.npm.req("POST", "nginx/access-lists", body)["id"]
                self.stats[action] += 1
            except RuntimeError as e:
                self.fail(label, e)

    # 3. hosts, in KINDS order
    def hosts(self, desired, state, cert_ids, acl_ids):
        for kind, wanted in desired.items():
            path = KINDS[kind]["path"]
            for key, (rel, d) in wanted.items():
                current = state[kind].get(key)
                label = f"{kind}/{Path(rel).name}"
                if current and current[1] == d:
                    self.stats["unchanged"] += 1
                    continue
                action = "update" if current else "create"
                print(f"{self.mode}{action} {label}")
                show_diff(label, current[1] if current else None, d)
                try:
                    if d.get("certificate") and tuple(sorted(d["certificate"])) not in cert_ids:
                        raise RuntimeError(f"certificate {d['certificate']} is not available")
                    if d.get("access_list") and d["access_list"] not in acl_ids:
                        raise RuntimeError(f"access list '{d['access_list']}' is not available")
                    payload = host_payload(kind, d, cert_ids, acl_ids, creating=not current)
                    if not self.args.dry_run:
                        if current:
                            hid = current[0]
                            self.npm.req("PUT", f"{path}/{hid}", payload)
                        else:
                            hid = self.npm.req("POST", path, payload)["id"]
                        now_enabled = current[1]["enabled"] if current else True
                        if d.get("enabled", True) != now_enabled:
                            self.npm.req("POST", f"{path}/{hid}/{'enable' if d.get('enabled', True) else 'disable'}")
                    self.stats[action] += 1
                except RuntimeError as e:
                    self.fail(label, e)

    # 4. prune hosts only (certs and access lists are never deleted by this tool)
    def prune(self, desired, state):
        for kind in reversed(list(KINDS)):
            path = KINDS[kind]["path"]
            for key, (hid, n) in state[kind].items():
                if key in desired[kind]:
                    continue
                label = f"{kind}/{filename(kind, n)}"
                if not self.args.prune:
                    print(f"note: {label} exists in NPM but has no file (use --prune to delete)")
                    continue
                if not (HOSTS / kind).is_dir():
                    print(f"skip prune of {label}: hosts/{kind}/ does not exist")
                    continue
                print(f"{self.mode}delete {label}")
                try:
                    if not self.args.dry_run:
                        self.npm.req("DELETE", f"{path}/{hid}")
                    self.stats["delete"] += 1
                except RuntimeError as e:
                    self.fail(label, e)


def cmd_apply(args) -> int:
    certs, acls, hosts, errors = load_desired()
    for e in errors:
        print(f"error: {e}", file=sys.stderr)
    if errors:
        return 1
    if args.prune and not any(hosts.values()):
        die("refusing to --prune with no host files (would delete everything in scope)")
    npm = login(args.api)
    host_state, cert_state, acl_state = fetch_state(npm)
    cert_ids = {k: v[0] for k, v in cert_state.items()}
    acl_ids = {k: v[0] for k, v in acl_state.items()}
    ap = Applier(npm, args)
    ap.certs(certs, cert_state, cert_ids)
    ap.acls(acls, acl_state, acl_ids)
    ap.hosts(hosts, host_state, cert_ids, acl_ids)
    ap.prune(hosts, host_state)
    if ap.needs:
        print("a real run will also need: " + ", ".join(dict.fromkeys(ap.needs)))
    print(ap.mode + ", ".join(f"{k}={v}" for k, v in ap.stats.items()))
    return 1 if ap.stats["failed"] else 0


def main() -> int:
    sys.stdout.reconfigure(line_buffering=True)  # keep stdout/stderr messages in order
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--api", default=API, help=f"NPM API base URL (default {API})")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("export", help="write NPM's *.heb.bet config to files")
    a = sub.add_parser("apply", help="create/update NPM from the files (certs, access lists, hosts)")
    a.add_argument("--dry-run", action="store_true", help="show the plan and diffs, change nothing")
    a.add_argument("--prune", action="store_true", help="also delete in-scope hosts with no file")
    a.add_argument("--agree-letsencrypt-tos", action="store_true",
                   help="agree to the Let's Encrypt subscriber agreement when requesting certs")
    args = ap.parse_args()
    try:
        return cmd_export(args) if args.cmd == "export" else cmd_apply(args)
    except RuntimeError as e:
        die(str(e))
    return 1


if __name__ == "__main__":
    sys.exit(main())
