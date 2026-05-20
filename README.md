# atlantis-teams-relay

A small Flask service that bridges [Atlantis](https://www.runatlantis.io/) to
Microsoft Teams.

Atlantis can post notifications in Slack's webhook format, but Microsoft Teams
(via its Workflows / Power Automate "Post to a channel when a webhook request
is received" trigger) expects an **Adaptive Card** payload. This relay accepts
the Slack-format payload from Atlantis, converts it into an Adaptive Card, and
forwards it to a Teams webhook URL.

```
                  Slack-format JSON                 Adaptive Card JSON
   Atlantis  ────────────────────────►  Relay  ────────────────────────►  Teams
                  POST /relay                      POST $TEAMS_WEBHOOK_URL
```

## What it converts

- Top-level `text` → bold heading
- `attachments[].title` / `fallback` → coloured heading (`good` / `warning` /
  `danger` map to Adaptive Card `Good` / `Warning` / `Attention`)
- `attachments[].pretext` → subtle text
- `attachments[].text` → monospace block (so `terraform plan` output is
  readable)
- `attachments[].fields` → `FactSet`
- Anything unrecognised falls back to the raw JSON so nothing is silently lost

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

In your Atlantis server config:

```yaml
webhooks:
  - event: apply
    kind: slack
    channel: "#ignored"
    workspace-regex: .*
    branch-regex: .*
```

…and set the Slack webhook URL Atlantis posts to as
`http://<host-running-the-relay>:5025/relay`.

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
