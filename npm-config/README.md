# Nginx Proxy Manager config as code (`*.heb.bet`)

This folder is the **source of truth** for Nginx Proxy Manager (NPM). From these files,
`npm_config.py` can rebuild an empty NPM: certificates, then access lists, then hosts.

NPM runs in Docker at `10.0.20.200` (admin UI and API on port 81). Its live data stays in
`../nginx-proxy-manager/`, which is gitignored. Only reviewed, secret-free config lives here.

```
npm-config/
├── npm_config.py                  # export / apply (Python 3 standard library only)
├── certificates.json              # certs by domain: provider, DNS challenge settings, expiry
├── access-lists.json              # access lists: name, IP allow/deny rules, usernames
├── bootstrap-secrets.example.json # shape of the secrets file (placeholders only)
└── hosts/
    ├── proxy/<domain>.json        # proxy hosts
    ├── redirection/<domain>.json  # redirection hosts
    ├── dead/<domain>.json         # 404 hosts
    └── stream/<port>.json         # TCP/UDP streams
```

## Rebuild from scratch (bootstrap order)

1. **Docker host and network.** Follow the main [README](../README.md): `.env` and the
   macvlan network, so NPM can get `10.0.20.200`.
2. **DNS.** Start AdGuard (`10.0.20.30`) and add the rewrite `*.heb.bet` → `10.0.20.200`.
   This rewrite is not yet stored as code (see open questions).
3. **NPM container.**
   ```bash
   docker compose up -d nginx-proxy-manager
   ```
4. **NPM admin.** Open http://10.0.20.200:81 and create the admin account. Older images
   start with `admin@example.com` / `changeme`; change it immediately.
5. **Secrets file.** Create the bootstrap secrets file **outside the repo** from
   `bootstrap-secrets.example.json`, `chmod 600` it, and point `NPM_BOOTSTRAP_SECRETS` at it.
   The tool refuses to read a secrets file located inside the repo.
6. **Plan.** This needs no secrets file; it lists what a real run will need:
   ```bash
   cd npm-config && python3 npm_config.py apply --dry-run
   ```
7. **Apply.** It runs in dependency order: certificates (Let's Encrypt via the recorded DNS
   challenge; each request can take minutes), then access lists, then proxy, redirection,
   404 hosts and streams.
   ```bash
   NPM_BOOTSTRAP_SECRETS=~/path/outside/repo/npm-secrets.json \
     python3 npm_config.py apply --agree-letsencrypt-tos
   ```
   Hosts whose certificate or access list failed are skipped with an error, and everything
   else is still applied. Fix the cause and run it again; it's idempotent.
8. **Backends.** The k3s services the hosts forward to come from their own folders (for
   example [`../streaming-setup`](../streaming-setup) provides Redpanda Console on NodePort 30081).
9. **Verify.** `python3 npm_config.py export` should produce no `git diff`, apart from
   `expires_on` for the newly issued certificates.

## Secrets policy

The repo never holds secrets. Real values are supplied by the user at rebuild time.
- **Location:** the secrets file lives **outside the repo** (recommended; the tool refuses to
  read one inside it). A local copy inside the repo must at least be gitignored; the
  `*secrets*.json` rule covers it.
- **Templates:** only `*.example` templates are committed, and their values must be
  placeholders (`REPLACE_ME`).
- **Commit-time check:** `scripts/check-secrets.py`, run by `.githooks/pre-commit`, blocks
  commits that add:
  - **Forbidden files:** `.env`, `*secrets*.json`, kubeconfig or `k3s.yaml`, or private keys
    and certs.
  - **Non-placeholder templates:** a template with a real-looking value.
  - **Secret values:** in any file, for example a private key, a DNS API token, a GitHub,
    AWS or Slack token, a JWT, a k3s token, a password hash or a Discord webhook.

  It prints `file:line` and the rule, never the value. Enable it once per clone:
  ```bash
  git config core.hooksPath .githooks
  ```
  To check the whole repo, run `python3 scripts/check-secrets.py --all`.

## Secrets the bootstrap needs (never stored here)

| Secret | Used for | Where it goes |
|---|---|---|
| NPM admin email and password | logging in to the API (`NPM_TOKEN` or prompt) | typed at the prompt |
| Let's Encrypt account email | requesting certificates | secrets file: `letsencrypt_email` |
| DNS provider API token (Cloudflare for `heb.bet`) | the DNS-01 challenge for `*.heb.bet` | secrets file: `dns_credentials.<provider>`, in certbot's credentials format |
| Access-list user passwords | creating access lists, or adding users to them | secrets file: `access_list_passwords.<list>.<user>` |

- **Read only when needed:** the secrets file is read only when something has to be created.
  An NPM that already matches the files needs only the admin login.
- **Never printed:** values are never printed, and export never writes them. NPM's stored DNS
  credentials, Let's Encrypt email and password hashes are stripped. A fail-closed scan then
  refuses to write anything that still looks secret.
- **Cloudflare token:** a token with only `Zone:DNS:Edit` on `heb.bet` is enough.

**Open question: where should the secrets live?** Options:
- **1Password item:** the user already has 1Password; use `op inject` or `op read` to render
  the file at bootstrap time.
- **SOPS + age:** encrypted in this repo; it needs an age key backed up elsewhere.
- **A file on the NAS:** outside the repo.

Not decided, and nothing is implemented yet.

## Export (NPM → files)

```bash
cd npm-config && python3 npm_config.py export
```

- **Scope:** every proxy, redirection and 404 host with at least one `*.heb.bet` (or
  `heb.bet`) domain, plus the certificates and access lists they use. Streams have no domain
  names, so **all** streams are exported.
- **Stable output:** one JSON file per host, with sorted keys and sorted domain names. Volatile
  or noisy fields are dropped: ids, timestamps, owner, `meta`.
- **References by name:** certificates are referenced by their domain list
  (`"certificate": ["*.heb.bet"]`), access lists by name, never by id.
- **No secret material:** no cert or key contents. Access lists include usernames and IP
  rules, but no passwords or hashes.
- **Fails closed:** before writing, the output is scanned for secret-looking content: PEM
  blocks, password/token keys or assignments, `Authorization`/`Basic`/`Bearer` values,
  password hashes, JWTs, email addresses and long random strings.
  - **On a match:** nothing is written. It prints `file:line` and the pattern name, never the
    value. Fix the host in NPM (usually by moving a credential out of *Advanced* config) and
    export again.
- **Mirrors NPM:** files for hosts that no longer exist in NPM are removed, so `git diff`
  shows exactly what changed. `expires_on` changes whenever NPM renews a certificate.

## Apply (files → NPM)

```bash
python3 npm_config.py apply --dry-run   # plan plus a unified diff per item; changes nothing
python3 npm_config.py apply             # create/update to match the files
python3 npm_config.py apply --prune     # also delete in-scope hosts that have no file
```

- **Idempotent:** hosts are matched by their exact set of domain names (streams by incoming
  port), certificates by domain set, access lists by name. Unchanged items are left alone.
- **Certificates:** missing ones are requested from Let's Encrypt with the recorded challenge
  settings, and only with `--agree-letsencrypt-tos`. Existing certificates are never modified
  (NPM renews them); differences are reported. Custom (uploaded) certificates can't be
  recreated from metadata; upload them in the UI.
- **Access lists:** rules and flags are updated. Users are created with passwords from the
  secrets file. When the user list hasn't changed, users aren't touched, so their existing
  passwords are kept.
- **Never deletes by default:** deleting needs `--prune`. It only deletes hosts (never
  certificates or access lists), only in scope, and refuses to run with no host files. Run
  `--prune --dry-run` first.
- **Enabled state:** `"enabled": false` disables a host through NPM's enable/disable endpoints.
- **Validation:** files with unknown keys, invalid JSON, duplicates, no `*.heb.bet` domain, or
  references to a certificate or access list missing from the JSON files are rejected before
  anything is sent.
- **Exit codes:** 0 on success, 1 on any error or failed item, 3 when export found
  secret-looking content.

## Login

- **Token:** if `NPM_TOKEN` is set, it's used as the bearer token.
- **Prompt:** otherwise you're asked for the NPM admin email and password. The password is
  read without echo, exchanged for a short-lived token and discarded.
- **Overrides:** use `--api URL` or `NPM_API` for the endpoint (default
  `http://10.0.20.200:81/api`), and `NPM_ZONE` for the zone (default `heb.bet`).

## Changing config

1. Edit or copy a JSON file and run `apply --dry-run`, then `apply`. Or change it in the NPM
   UI and run `export`.
2. Review `git diff`, then commit. New `*.heb.bet` names resolve through the AdGuard wildcard
   and are covered by the `*.heb.bet` certificate.

## Open questions and gaps

- **Secrets storage:** see above.
- **AdGuard:** the `*.heb.bet` rewrite (and the rest of AdGuard's config) isn't stored as code yet.
- **NPM admin account:** still created by hand on a fresh install.
- **Not tested against real NPM yet:** the tool was tested against a local mock of the NPM
  API, which included a full rebuild of an empty instance. The first real export and apply
  (`--dry-run` first) should be watched.
  - **Unconfirmed behaviour:** two NPM behaviours the tool relies on are unconfirmed. On
    update, NPM should keep an existing access-list user's password when it's sent empty. On
    create, a certificate request should return the new certificate's id.
