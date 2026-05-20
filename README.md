# atlantis-teams-relay

A small Flask service that bridges [Atlantis](https://www.runatlantis.io/) to
Microsoft Teams.

Atlantis's `kind: http` webhook posts a JSON payload (with PascalCase fields
like `Repo`, `Pull`, `Project`, `Success`) to any URL you choose, but Microsoft
Teams (via its Workflows / Power Automate "Post to a channel when a webhook
request is received" trigger) expects an **Adaptive Card**. This relay takes
the Atlantis payload, renders an Adaptive Card from it, and forwards it to
your Teams webhook.

```
                Atlantis kind:http JSON              Adaptive Card JSON
   Atlantis  ────────────────────────────►  Relay  ────────────────────────►  Teams
                POST /relay                          POST $TEAMS_WEBHOOK_URL
```

## Supported payload shapes

The relay auto-detects which shape it was sent and dispatches accordingly.

**1. Atlantis native (recommended; what `kind: http` actually sends)**

Top-level PascalCase fields. Rendered as a coloured title (`Apply succeeded` /
`Apply failed`) plus a FactSet of `Repo`, `Pull request`, `Project`,
`Workspace`, `Directory`, `Triggered by`.

**2. Slack incoming-webhook shape (useful for `curl` testing)**

`{text, attachments: [{title, color, pretext, text, fields}]}`. Mapped to:

- Top-level `text` → bold heading
- `attachments[].title` / `fallback` → coloured heading (`good` / `warning` /
  `danger` → `Good` / `Warning` / `Attention`)
- `attachments[].pretext` → subtle text
- `attachments[].text` → monospace block
- `attachments[].fields` → `FactSet`
- Anything unrecognised falls back to raw JSON so nothing is silently lost

## Endpoints

| Method | Path     | Purpose                                  |
| ------ | -------- | ---------------------------------------- |
| POST   | /relay   | Receives the Atlantis webhook payload    |
| GET    | /health  | Liveness probe (returns `{"status":"ok"}`) |

## Configuration

| Variable            | Required | Default | Description                                    |
| ------------------- | -------- | ------- | ---------------------------------------------- |
| `TEAMS_WEBHOOK_URL` | yes      | —       | The Microsoft Teams Workflows webhook URL      |
| `PORT`              | no       | `5025`  | Port the relay listens on                      |

## Running locally

```bash
make install
TEAMS_WEBHOOK_URL=https://prod-XX.westeurope.logic.azure.com:443/workflows/... make run
```

## Running with Docker

Pull from Docker Hub:

```bash
docker run --rm -p 5025:5025 \
  -e TEAMS_WEBHOOK_URL="https://prod-XX.westeurope.logic.azure.com:443/workflows/..." \
  operry/atlantis-teams-relay:latest
```

Or build locally:

```bash
make build
make docker-run
```

## Pointing Atlantis at the relay

Use Atlantis's generic HTTP webhook (`kind: http`), **not** `kind: slack` —
`kind: slack` calls the Slack Web API and ignores your URL.

In your Atlantis server-side config (`repos.yaml` / server config file or the
equivalent env vars):

```yaml
webhooks:
  - event: apply
    kind: http
    url: http://<host-running-the-relay>:5025/relay
    workspace-regex: .*
    branch-regex: .*
```

When the relay runs as an ECS sidecar in the same task as Atlantis, the URL
becomes `http://localhost:5025/relay`.

### Test it without Atlantis

```bash
curl -X POST http://localhost:5025/relay \
  -H 'Content-Type: application/json' \
  -d '{
    "Repo": {"FullName": "acme/infra"},
    "Pull": {"Num": 42, "URL": "https://github.com/acme/infra/pull/42", "Author": "alice"},
    "User": {"Username": "alice"},
    "Project": "vpc",
    "Workspace": "prod",
    "Directory": "terraform/vpc",
    "Success": true
  }'
```

## Releasing

Every push to `main` triggers the GitHub Actions workflow in
`.github/workflows/docker-publish.yml`, which:

1. Bumps the patch version and creates a new `vX.Y.Z` git tag
   (Conventional Commit prefixes `feat:` / `fix:` / `BREAKING CHANGE:` control
   the bump level)
2. Builds a multi-arch image (`linux/amd64`, `linux/arm64`)
3. Pushes it to Docker Hub as `operry/atlantis-teams-relay` with tags
   `:X.Y.Z`, `:vX.Y.Z`, and `:latest`

Required repo secrets: `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN`.

## License

MIT — see [LICENSE](./LICENSE).

Originally developed at **Quantifi Solutions Inc** and released as open source.
