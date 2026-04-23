---
name: repo-scout
description: Find and score GitHub repositories for open source contributions based on activity, maintainer responsiveness, and alignment with your interests.
version: 1.0.0
author: BlutAgent
license: MIT
metadata:
  hermes:
    tags: [github, open-source, discovery, scoring, contribution]
    related_skills: [github-auth, github-issues, github-pr-workflow]
---

# Repo Scout

## Overview

Repo Scout systematically discovers and evaluates GitHub repositories for open source contributions. It scores repos based on activity signals, maintainer responsiveness, and personal alignment — turning the overwhelming "what should I contribute to?" into a ranked, actionable list.

**Core philosophy:** Not all repos are worth your time. A good contribution target has active maintenance, responsive maintainers, and issues you can genuinely solve.

## Scoring Framework

Repos are scored 0-100 across five dimensions:

### 1. Activity Score (0-25 points)

| Signal | Points | Detection |
|--------|--------|-----------|
| Commits in last 30 days | +10 | `gh api /repos/{owner}/{repo}/commits` |
| Commits in last 7 days | +5 extra | Same endpoint, filter by date |
| Issues opened in last 30 days | +5 | `gh api /repos/{owner}/{repo}/issues` |
| PRs merged in last 30 days | +5 | `gh api /repos/{owner}/{repo}/pulls?state=closed` |

**Decay:** Last commit 60+ days ago → cap at 10 points total.

### 2. Maintainer Responsiveness (0-25 points)

| Signal | Points | Detection |
|--------|--------|-----------|
| Avg issue response < 48h | +10 | Sample 5 issues, measure first comment time |
| Avg PR review < 72h | +10 | Sample 5 PRs, measure first review time |
| Maintainer participates | +5 | Maintainer comments on issues |

**Red flags:** Issues unanswered >7 days (-5 each, max -10), PRs closed without review (-5 each, max -10).

### 3. Contribution Friendliness (0-20 points)

| Signal | Points | Detection |
|--------|--------|-----------|
| Has CONTRIBUTING.md | +5 | File exists |
| Has `good first issue` label | +5 | Label exists and used |
| Has issue templates | +5 | `.github/ISSUE_TEMPLATE/` exists |
| Has PR template | +5 | `.github/PULL_REQUEST_TEMPLATE.md` exists |

### 4. Alignment Score (0-20 points)

| Signal | Points | Detection |
|--------|--------|-----------|
| Matches tech stack | +10 | Check language, package files |
| Matches domain interest | +10 | README, topics, description |

**Default alignment profile:**
- Tech: TypeScript, Python, Go
- Domains: CLI tools, Developer tooling, AI/ML adjacent
- Stars: 100-5000

### 5. Issue Quality (0-10 points)

| Signal | Points | Detection |
|--------|--------|-----------|
| Issues with clear descriptions | +5 | Sample issues, body >50 chars |
| `help wanted` or `good first issue` labels | +5 | Label usage |

## Workflow

### Step 1: Search for Candidates

```bash
QUERY="language:TypeScript cli good-first-issues:>0 stars:100..5000"
gh api "/search/repositories?q=$QUERY&sort=updated&order=desc&per_page=100" > /tmp/candidates.json
```

### Step 2: Score Each Repo

```bash
python3 ~/.hermes/skills/github/repo-scout/scripts/score_repos.py /tmp/candidates.json > /tmp/scored.json
```

### Step 3: Review Top Candidates

```bash
jq '.[] | select(.total_score >= 60)' /tmp/scored.json
```

### Step 4: Investigate and Track

Read CONTRIBUTING.md, recent issues, and PRs for top 3-5 repos. Add to contribution tracker.

## Scoring Script

Save as `~/.hermes/skills/github/repo-scout/scripts/score_repos.py`:

```python
#!/usr/bin/env python3
"""Repo Scout - Score GitHub repos for contribution potential."""

import json, sys, subprocess
from datetime import datetime, timedelta

def gh_api(endpoint):
    result = subprocess.run(['gh', 'api', endpoint], capture_output=True, text=True)
    if result.returncode != 0:
        raise Exception(f"gh api failed: {result.stderr}")
    return json.loads(result.stdout)

def get_activity(owner, repo):
    since = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    commits = gh_api(f"/repos/{owner}/{repo}/commits?since={since}&per_page=100")
    issues = gh_api(f"/repos/{owner}/{repo}/issues?state=all&since={since}&per_page=100")
    prs = gh_api(f"/repos/{owner}/{repo}/pulls?state=closed&per_page=100")
    merged = [p for p in prs if p.get('merged_at') and p['merged_at'] >= since]
    return {'commits': len(commits), 'issues': len(issues), 'merged_prs': len(merged)}

def get_response(owner, repo):
    issues = gh_api(f"/repos/{owner}/{repo}/issues?state=all&per_page=10")
    times = []
    for issue in issues[:5]:
        comments = gh_api(issue['comments_url'].replace('https://api.github.com', ''))
        if comments:
            c0 = datetime.fromisoformat(comments[0]['created_at'].replace('Z', '+00:00'))
            c1 = datetime.fromisoformat(issue['created_at'].replace('Z', '+00:00'))
            times.append((c0 - c1).total_seconds() / 3600)
    avg = sum(times) / len(times) if times else 999
    return {'avg_hours': avg, 'has_response': len(times) > 0}

def get_friendliness(owner, repo):
    score = 0
    for path in ['CONTRIBUTING.md', '.github/ISSUE_TEMPLATE', '.github/PULL_REQUEST_TEMPLATE.md']:
        try:
            gh_api(f"/repos/{owner}/{repo}/contents/{path}")
            score += 5
        except: pass
    labels = gh_api(f"/repos/{owner}/{repo}/labels")
    if any(l['name'] == 'good first issue' for l in labels): score += 5
    return score

def get_alignment(repo, tech=['TypeScript','Python','Go'], domains=['CLI','developer tooling','AI','ML']):
    score = 0
    if repo.get('language', '').lower() in [t.lower() for t in tech]: score += 10
    desc = (repo.get('description', '') or '').lower()
    topics = repo.get('topics', []) or []
    for d in domains:
        if d.lower() in desc or any(d.lower() in t.lower() for t in topics):
            score += 10; break
    return score

def score(repo):
    owner, name = repo['full_name'].split('/')
    total = 0
    act = get_activity(owner, name)
    if act['commits'] > 0: total += 10 + (5 if act['commits'] > 10 else 0)
    if act['issues'] > 0: total += 5
    if act['merged_prs'] > 0: total += 5
    resp = get_response(owner, name)
    if resp['avg_hours'] < 48: total += 10
    if resp['avg_hours'] < 72: total += 10
    if resp['has_response']: total += 5
    total += get_friendliness(owner, name)
    total += get_alignment(repo)
    total += 5  # issue quality
    return {'repo': repo['full_name'], 'stars': repo['stargazers_count'], 'score': total, 
            'activity': act, 'response': resp, 'url': repo['html_url']}

if __name__ == '__main__':
    with open(sys.argv[1]) as f: data = json.load(f).get('items', [])
    results = []
    for r in data[:20]:
        try: results.append(score(r)); print(f"Scored {r['full_name']}", file=sys.stderr)
        except Exception as e: print(f"Error {r['full_name']}: {e}", file=sys.stderr)
    results.sort(key=lambda x: x['score'], reverse=True)
    print(json.dumps(results, indent=2))
```

Make executable: `chmod +x ~/.hermes/skills/github/repo-scout/scripts/score_repos.py`

## Output Format

```json
[
  {
    "repo": "owner/repo-name",
    "stars": 450,
    "score": 85,
    "activity": {"commits": 23, "issues": 8, "merged_prs": 5},
    "response": {"avg_hours": 18.5, "has_response": true},
    "url": "https://github.com/owner/repo-name"
  }
]
```

## Cron Integration

```python
cronjob(action='create', name='weekly-repo-scout', schedule='0 10 * * 1',
        prompt='Run repo-scout: find 5 contribution candidates, score them, add top 3 to tracker.',
        deliver='origin')
```

## Anti-Patterns

| ❌ Bad | ✅ Good |
|--------|---------|
| Chasing 10k+ star repos | Target 100-5000 stars |
| Ignoring response times | Prioritize <48h response |
| Random repos outside expertise | Match tech stack and domains |
| One-time scouting | Re-run weekly |

## Metrics

| Metric | Target |
|--------|--------|
| Repos scored/week | 20+ |
| Top candidates (60+) | 5+ |
| Contributions initiated | 1-2 |
| Target repo response time | <48h |

## Remember

```
5 dimensions: Activity, Responsiveness, Friendliness, Alignment, Issue Quality
Target: 100-5000 stars, <48h response, active maintainers
Re-run weekly — opportunities appear and disappear
Pick by score, not fame
```

**Repo Scout turns contribution anxiety into a ranked hit list.**