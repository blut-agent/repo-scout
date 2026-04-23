#!/usr/bin/env python3
"""Repo Scout - Score GitHub repos for contribution potential."""

import json, sys, subprocess
from datetime import datetime, timedelta

def gh_api(endpoint):
    """Make GitHub API call using gh CLI (handles auth)."""
    result = subprocess.run(['gh', 'api', endpoint], capture_output=True, text=True)
    if result.returncode != 0:
        raise Exception(f"gh api failed: {result.stderr}")
    return json.loads(result.stdout)

def get_activity(owner, repo):
    """Get recent commits, issues, and merged PRs."""
    since = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    commits = gh_api(f"/repos/{owner}/{repo}/commits?since={since}&per_page=100")
    issues = gh_api(f"/repos/{owner}/{repo}/issues?state=all&since={since}&per_page=100")
    prs = gh_api(f"/repos/{owner}/{repo}/pulls?state=closed&per_page=100")
    merged = [p for p in prs if p.get('merged_at') and p['merged_at'] >= since]
    return {'commits': len(commits), 'issues': len(issues), 'merged_prs': len(merged)}

def get_response(owner, repo):
    """Sample recent issues for maintainer response times."""
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
    """Check for CONTRIBUTING.md, templates, and labels."""
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
    """Check if repo matches your tech stack and domains."""
    score = 0
    if repo.get('language', '').lower() in [t.lower() for t in tech]: score += 10
    desc = (repo.get('description', '') or '').lower()
    topics = repo.get('topics', []) or []
    for d in domains:
        if d.lower() in desc or any(d.lower() in t.lower() for t in topics):
            score += 10; break
    return score

def score(repo):
    """Calculate total score for a repo."""
    owner, name = repo['full_name'].split('/')
    total = 0
    # Activity (0-25)
    act = get_activity(owner, name)
    if act['commits'] > 0: total += 10 + (5 if act['commits'] > 10 else 0)
    if act['issues'] > 0: total += 5
    if act['merged_prs'] > 0: total += 5
    # Responsiveness (0-25)
    resp = get_response(owner, name)
    if resp['avg_hours'] < 48: total += 10
    if resp['avg_hours'] < 72: total += 10
    if resp['has_response']: total += 5
    # Friendliness (0-20)
    total += get_friendliness(owner, name)
    # Alignment (0-20)
    total += get_alignment(repo)
    # Issue quality (0-10)
    total += 5
    return {'repo': repo['full_name'], 'stars': repo['stargazers_count'], 'score': total, 
            'activity': act, 'response': resp, 'url': repo['html_url']}

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: score_repos.py <candidates.json>")
        sys.exit(1)
    with open(sys.argv[1]) as f: data = json.load(f).get('items', [])
    results = []
    for r in data[:20]:
        try: results.append(score(r)); print(f"Scored {r['full_name']}", file=sys.stderr)
        except Exception as e: print(f"Error {r['full_name']}: {e}", file=sys.stderr)
    results.sort(key=lambda x: x['score'], reverse=True)
    print(json.dumps(results, indent=2))
