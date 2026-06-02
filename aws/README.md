# Odysseus on AWS — private, two-user, ~$20-25/mo

Same access pattern as `hermes-aws/`: EC2 + Tailscale + SSM. Adapted for the
heavier Odysseus stack (FastAPI + SQLite + fastembed + optional ChromaDB)
and shaped for shared use by you + your wife.

| | |
|---|---|
| Variant | on-demand single instance, ~$20-25/mo |
| Compute | t4g.medium (4 GB) |
| Public ingress | none |
| Access | Tailscale Serve (`https://odysseus.<tailnet>.ts.net`) for the web UI; Tailscale SSH for ops |
| Persistence | root EBS volume with `DeleteOnTermination=false` + daily DLM snapshots (14-day retention) |

## Files

- `odysseus-stack.yaml` — single-instance CloudFormation
- `deploy.sh` — deploy/update wrapper
- `tailscale-acl.example.json` — example tailnet ACL for a two-user family

## One-time prerequisites

You only do these once per account/tailnet.

### 1. GitHub PAT in SSM
Fine-grained PAT on `Grenguar/odysseus-fork` with `Contents: Read-only`
only. Park it as a SecureString:

```bash
aws ssm put-parameter \
  --name /odysseus/github/pat \
  --type SecureString \
  --value 'github_pat_...' \
  --region eu-west-1 --profile igor
```

Why fine-grained: classic PATs grant access to *every* repo on your account.
A fine-grained token caps the blast radius to one repo, read-only.

To rotate later: `--overwrite` the same parameter. No instance change
needed; next boot picks it up.

### 2. Tailscale ACL
Open <https://login.tailscale.com/admin/acls/file>, paste the contents of
`tailscale-acl.example.json`, edit the two email addresses to match your
Tailscale logins, save. Highlights:

- Declares `tag:odysseus` so the EC2 host can identify itself.
- Defines `group:family` containing both you and your wife.
- Allows the family group to reach the box on port 443.
- Allows only you (`group:admin`) Tailscale-SSH into the box.

### 3. Tailscale auth key (reusable, NOT ephemeral)
<https://login.tailscale.com/admin/settings/keys>:
- **Reusable: ON**
- **Ephemeral: OFF** — we want the node identity stable across reboots so
  MagicDNS keeps resolving `odysseus.<tailnet>.ts.net` after instance
  restarts.
- **Tag: tag:odysseus**

Copy the `tskey-auth-...` value.

### 4. Tailnet HTTPS + MagicDNS
DNS tab → enable **MagicDNS** (usually already on).  
DNS tab → enable **HTTPS Certificates**. Without this, Tailscale Serve
can't mint the Let's Encrypt cert and the browser will refuse the
connection.

## Deploy

```bash
export AWS_PROFILE=igor
export AWS_REGION=eu-west-1
export TS_AUTHKEY=tskey-auth-xxxxxxxxxxxxx

./deploy.sh
```

Bootstrap is ~5-8 minutes (the slow part is `pip install`-ing Odysseus's
dependency tree, especially the cryptography + fastembed wheels on the
small ARM box).

When the stack outputs print, also fetch the one-time setup token:

```bash
aws ssm get-parameter --region eu-west-1 \
  --name /odysseus/setup-token \
  --query Parameter.Value --output text
```

Then open `https://odysseus.<your-tailnet>.ts.net` in your browser and
follow the `/setup` flow. The token is consumed on first successful setup
and the SSM parameter can be deleted afterwards.

## Adding your wife as a second user (Tailscale + Odysseus)

This is two separate user systems and both need to be configured. They
don't talk to each other — Tailscale gets her *to* the box; Odysseus gets
her *into* the app.

### Step 1 — Add her to your tailnet
There are two ways. Pick one:

**Option A: Personal tailnet (free, up to 3 users).**  
Tailscale admin console → **Users** → **Invite users** → enter her email.
She'll receive an invite, sign up with Google/Microsoft/GitHub (or email),
join your tailnet. You'll see her under "Users". Her email must match the
one you'll put into the ACL.

**Option B: Shared device only (no full tailnet membership).**  
Admin → the `odysseus-agent` device → **Share…** → enter her email. She
gets access *only* to that one node and only to the ports you allow. This
is more locked-down but loses ergonomics (she won't see the host listed
in her Tailscale app, has to type the full hostname).

I'd start with A for simplicity. The ACL in `tailscale-acl.example.json`
assumes A — both users in `group:family`.

### Step 2 — Update the ACL with her email
Edit `tailscale-acl.example.json`, replace `wife@example.com` with her
actual Tailscale-login email, paste into
<https://login.tailscale.com/admin/acls/file>, **Save**.

ACL tip: Tailscale validates the file on save — if either email isn't on
your tailnet yet, it complains. Add her first (step 1), then update the
ACL.

### Step 3 — Install Tailscale on her devices
On each of her devices:
- macOS / Windows: install from <https://tailscale.com/download>, sign in
  with the same identity she accepted the invite on.
- iOS / Android: App Store / Play Store, sign in same way.
- Linux: `curl -fsSL https://tailscale.com/install.sh | sh` then
  `sudo tailscale up`.

Once signed in, each device shows up under "Machines" in your admin
console. She doesn't need to do anything else — the ACL already grants
her group access to the Odysseus box.

### Step 4 — Verify she can reach Odysseus
On any of her tailnet devices: open
`https://odysseus.<your-tailnet>.ts.net`. The login page should load with
a real TLS cert (no browser warning). If it doesn't:
- Did you enable **HTTPS Certificates** in the tailnet's DNS settings? (§4
  of prerequisites above.)
- Does her device show as **Connected** in the Tailscale app? Some VPNs
  conflict with Tailscale — turn the other VPN off first.
- Is the ACL saved with her actual email? `tailscale-acl.example.json` is
  a placeholder file.

### Step 5 — Create her Odysseus account
Tailscale only gets her *to* the page. Odysseus has its own user system
on top. From your admin session in Odysseus:

1. Settings → **Users** → **Add user**.
2. Pick her username (lowercase, no spaces), set a strong starter password.
3. Leave **is_admin: false**. Two admins is fine if you trust her with
   the shell tool / MCP / vault — those are admin-gated for safety.
4. Tell her the temp password. She logs in once, then changes it via her
   profile menu.

She can now log into Odysseus from any of her tailnet devices. Her chat
sessions, notes, calendar, email accounts, and uploads are scoped to her
own account; she can't see yours and vice versa (Odysseus has owner
scoping on every state-changing route).

### Step 6 (optional) — 2FA on each account
Both of you should enable TOTP from the Odysseus user menu. The backup
codes shown after setup are the only chance to capture them — store
somewhere safe (password manager). The codes are hashed at rest on the
box, so even if `data/auth.json` leaked, they'd still need the
plaintext copies you stashed at enrollment time.

## Day-2 operations

### Update to a new version of the fork

```bash
ssh odysseus@odysseus              # via Tailscale SSH
cd /opt/odysseus/app
git pull
./venv/bin/pip install -r requirements.txt
sudo systemctl restart odysseus
```

Or pin a tag via `GIT_REF=v0.2.0 ./deploy.sh` to redeploy via CFN.

### Watch logs

```bash
ssh odysseus@odysseus
sudo journalctl -u odysseus -f          # app logs
sudo tail -f /var/log/odysseus-bootstrap.log   # first-boot only
```

The H-LogPII filter in `src/log_scrub.py` masks Bearer tokens, `sk-...` /
`hf_...` / `ody_...` API keys, and `password=...` URI fragments before
they hit the log handler — so journalctl output is safe to copy/paste
into a bug report.

### Open a root shell without SSH (break-glass)
If Tailscale is broken, fall back to SSM:
```bash
aws ssm start-session --target $(aws cloudformation describe-stack-resources \
  --stack-name odysseus-agent \
  --logical-resource-id OdysseusInstance \
  --query 'StackResources[0].PhysicalResourceId' --output text)
```

### Backups & disaster recovery
Daily snapshots are kept for 14 days (DLM policy). To restore from a
snapshot:
1. `aws ec2 describe-snapshots --filters Name=tag:Snapshot,Values=odysseus-daily`
2. Create a new volume from the snapshot.
3. Stop the instance, detach the live root volume, attach the restored
   one as `/dev/xvda`, start.

For a *full* restore including the tailnet identity, the restored volume
preserves `/var/lib/tailscale` so the node rejoins the same tailnet
identity automatically.

### Cost knobs

| Item | $/mo (eu-west-1) |
|---|---|
| t4g.medium on-demand | ~$18 |
| 30 GB root gp3 | $2.40 |
| 14×1 GB daily snapshots | ~$0.50 |
| Outbound bandwidth (under free tier) | $0 |
| **Total** | **~$21** |

If you want to drop to ~$13: rebuild on the spot pattern from
`hermes-aws/hermes-stack-spot.yaml`. You'd need the persistent-EBS dance
because the data is much more valuable than Hermes's runtime cache.

### Tear down

```bash
aws cloudformation delete-stack --stack-name odysseus-agent
aws cloudformation wait stack-delete-complete --stack-name odysseus-agent
```

The root EBS volume is set to `DeleteOnTermination=false`, so your data
*survives* a stack delete. Take a final snapshot and then delete the
volume manually if you really want to wipe:

```bash
VOL_ID=$(aws ec2 describe-volumes \
  --filters Name=tag:Name,Values=odysseus-agent \
  --query 'Volumes[?Attachments==null]|[0].VolumeId' --output text)
aws ec2 create-snapshot --volume-id "$VOL_ID" --description "final odysseus backup"
aws ec2 delete-volume --volume-id "$VOL_ID"
```

Also clean up SSM:
```bash
aws ssm delete-parameter --name /odysseus/github/pat
aws ssm delete-parameter --name /odysseus/setup-token || true
```

The Tailscale node will auto-remove from the tailnet after ~28 days idle,
or remove it manually from the admin console.

## Security notes

Carried over from the `hermes-aws` posture, plus Odysseus-specific
extras from the recent security review:

- ✅ Zero inbound rules, no SSH key, IMDSv2 enforced, root volume encrypted
- ✅ Hop limit 1 on IMDS — a web-renderer / agent RCE can't pivot to
  steal instance role creds
- ✅ Bcrypt(rounds=12) password hashes, Fernet-encrypted secrets at rest
  (IMAP/SMTP creds, integration API keys, persisted session tokens)
- ✅ TOTP backup codes bcrypt-hashed (H1) — a stolen `auth.json` no longer
  contains permanent 2FA bypass codes
- ✅ `.key` file mode 0o600 (H2)
- ✅ Incoming email HTML allowlist-sanitized (H3)
- ✅ Origin/Referer CSRF middleware (H4)
- ✅ Agent loopback blocked from creating run_*/ssh_command tasks (H5)
- ✅ One-time setup token replaces "temp password printed to logs forever"
  (H8)
- ✅ Logging filter masks Bearer / sk-/ hf_/ ody_/ AWS / Slack tokens and
  password fields
- ✅ Tailscale Serve binds the app to loopback and terminates TLS — the
  web UI is reachable ONLY from your tailnet
- ⚠️ `SECURE_COOKIES=true` is set in `.env` because Tailscale Serve
  fronts HTTPS. If you ever bypass Tailscale Serve and hit `http://` on
  loopback for debugging, log-in cookies won't be set.

## What's intentionally NOT here

- **No Funnel.** Tailscale Funnel would expose Odysseus to the public
  internet. We never want that for this stack — the whole point is that
  only tailnet members can reach it.
- **No Bedrock IAM policy.** Hermes uses Bedrock natively; Odysseus does
  not. Configure your LLM provider (OpenRouter, OpenAI, Anthropic, or a
  local Ollama on another tailnet host) from Odysseus Settings → Models
  after first login.
- **No ChromaDB server.** Personal-docs and semantic-memory features
  expect a ChromaDB server at `localhost:8100`. If you want them, SSH in
  and:
  ```bash
  sudo -u odysseus -H bash -lc 'cd /opt/odysseus/app && ./venv/bin/pip install chromadb'
  # Then add a second systemd unit running `chroma run --host 127.0.0.1 --port 8100`
  ```
  Skipping it is a deliberate default — most chat / agent flows don't
  need it, and adding it doubles the memory footprint.

## Push before you deploy

The CFN user-data clones *this very repo* at the ref you pass as
`GIT_REF` (default `main`). Whatever you've pushed is what runs on the
box — including these templates in `aws/`. So the flow is always:

```bash
cd ..                # back to the fork root
git add -A
git commit -m "..."
git push
cd aws
./deploy.sh
```

To test an in-progress change without disturbing `main`, push a
branch and deploy it:

```bash
git push origin my-experiment
GIT_REF=my-experiment ./deploy.sh
```
