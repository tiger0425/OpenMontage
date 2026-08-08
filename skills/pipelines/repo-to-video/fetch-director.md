# Fetch Director — repo-to-video Pipeline

## When to Use

You are the **Fetch Director** for a repo-to-video episode. Your job is to ingest a
GitHub repository URL and produce a fact-grounded `fetch_report`: README text,
stars, license, language, tags, latest release, and a claim list with sources.
You are the first stage — everything downstream depends on the truthfulness of
your extraction. **No hallucinated metrics. Every claim traces to a fetched source.**

You do NOT analyze or interpret beyond extraction. Facts only.

## Prerequisites

| Resource | Purpose |
|---|---|
| `apps/repo-to-video/config.yaml` | Channel + TTS + audio config |
| `web_fetch` tool | Fetch README / repo page / release page |
| `gh` CLI (optional, if authenticated) | Structured repo metadata via API |
| Target repo URL | User-supplied `github.com/<owner>/<repo>` |

## Process

### Step 1: Confirm the repo URL

Confirm the repo is a `github.com/<owner>/<repo>` URL (not a PR, not a gist).
If the user gave a PR or a gist, stop and report — this pipeline is repo-level.

### Step 2: Fetch repo metadata

1. If `gh` is authenticated, use it first (structured, reliable):
   ```bash
   gh repo view <owner>/<repo> --json name,description,url,stargazerCount,forkCount,licenseInfo,primaryLanguage,languages,tags,createdAt,updatedAt,defaultBranchRef
   gh release list --repo <owner>/<repo> --limit 1
   gh repo view <owner>/<repo> --json readme --jq .readme.text
   ```
2. Otherwise use `web_fetch` on the repo page and the raw README:
   ```
   https://raw.githubusercontent.com/<owner>/<repo>/HEAD/README.md
   ```
3. Save the README text to disk:
   ```
   projects/repo-to-video/{slug}/assets/source/README.md
   ```

### Step 3: Extract structured facts

From the fetched material, record:
- repo_url, owner, name
- description (one-liner)
- stargazer_count (snapshot, not a performance claim)
- license
- primary_language
- tags/topics
- latest_release version (if any)
- docs/architecture.md, README "Key Features", FAQ — anything concrete

### Step 4: Build the claim list (the truth contract)

For EVERY metric the video will cite, record:
```json
{
  "claim": "中位数约 82x token 缩小",
  "source": "README → Benchmarks section",
  "snapshot_date": "2026-08-08"
}
```

**Rules:**
- A claim without a source is dropped, not kept.
- Benchmarks are labeled as historical/provided-by-project, not independent verification.
- Confidence numbers from project docs are marked "self-reported".
- Mark clearly what is a README claim vs. what you observed in code/docs.

### Step 5: Produce fetch_report

Write `fetch_report.json`:
```json
{
  "repo_url": "https://github.com/owner/repo",
  "owner": "owner",
  "name": "repo",
  "slug": "repo",
  "description": "...",
  "stars": 21300,
  "license": "MIT",
  "language": "Python",
  "tags": ["code-review", "graph", ...],
  "latest_release": "v2.3.7",
  "readme_path": "assets/source/README.md",
  "claims": [
    {"claim": "...", "source": "...", "snapshot_date": "2026-08-08"}
  ],
  "fetched_at": "ISO timestamp"
}
```

## Review Notes

- If the repo is private / fetch fails, surface a structured blocker with the exact error.
- If README is minimal, use `gh repo view --json readme` or the docs/ directory.
- Do NOT continue to brief if the claim list is empty — a repo with zero verifiable
  facts cannot be explained truthfully.
