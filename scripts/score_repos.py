#!/usr/bin/env python3
"""Repo Scout - Score GitHub repos for contribution potential.

Security hardened v1.1.0:
- Input validation for file paths
- Endpoint validation for API calls
- Owner/repo format validation
"""

import json, sys, subprocess, re
from datetime import datetime, timedelta
from pathlib import Path

# Security: Validate inputs before use
ALLOWED_TMP_DIR = Path('/tmp').resolve()
GITHUB_API_BASE = 'https://api.github.com'

def validate_endpoint(endpoint):
    """Validate GitHub API endpoint format."""
    if not isinstance(endpoint, str):
        raise ValueError("Endpoint must be a string")
    if not endpoint.startswith('/repos/') and not endpoint.startswith('/search/'):
        raise ValueError(f"Invalid endpoint format: {endpoint[:50]}")
    return endpoint

def validate_owner_repo(owner, repo):
    """Validate owner/repo format to prevent injection."""
    pattern = r'^[a-zA-Z0-9][a-zA-Z0-9._-]{0,99}$'
    if not re.match(pattern, owner) or not re.match(pattern, repo):
        raise ValueError(f"Invalid owner/repo format: {owner}/{repo}")
    return True

def validate_file_path(filepath):
    """Validate file path is within allowed directory."""
    path = Path(filepath).resolve()
    if not str(path).startswith(str(ALLOWED_TMP_DIR)):
        raise ValueError(f"File must be in {ALLOWED_TMP_DIR}, got: {path}")
    if not path.suffix == '.json':
        raise ValueError(f"File must be .json, got: {path.suffix}")
    return path

def gh_api(endpoint):
    """Make GitHub API call with validated endpoint."""
    endpoint = validate_endpoint(endpoint)
    result = subprocess.run(['gh', 'api', endpoint], capture_output=True, text=True)
    if result.returncode != 0:
        raise Exception(f"gh api failed: {result.stderr}")
    return json.loads(result.stdout)

def get_activity(owner, repo):
    since = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
    validate_owner_repo(owner, repo)
    commits = gh_api(f"/repos/{owner}/{repo}/commits?since={since}&per_page=100")
    issues = gh_api(f"/repos/{owner}/{repo}/issues?state=all&since={since}&per_page=100")
    prs = gh_api(f"/repos/{owner}/{repo}/pulls?state=closed&per_page=100")
    merged = [p for p in prs if p.get('merged_at') and p['merged_at'] >= since]
    return {'commits': len(commits), 'issues': len(issues), 'merged_prs': len(merged)}

def get_response(owner, repo):
    validate_owner_repo(owner, repo)
    issues = gh_api(f"/repos/{owner}/{repo}/issues?state=all&per_page=10")
    times = []
    for issue in issues[:5]:
        # Security: Validate URL before using
        url = issue.get('comments_url', '')
        if not url.startswith(f'{GITHUB_API_BASE}/repos/'):
            continue
        endpoint = url.replace(GITHUB_API_BASE, '')
        if not endpoint.startswith('/repos/'):
            continue
        comments = gh_api(endpoint)
        if comments:
            c0 = datetime.fromisoformat(comments[0]['created_at'].replace('Z', '+00:00'))
            c1 = datetime.fromisoformat(issue['created_at'].replace('Z', '+00:00'))
            times.append((c0 - c1).total_seconds() / 3600)
    avg = sum(times) / len(times) if times else 999
    return {'avg_hours': avg, 'has_response': len(times) > 0}

def get_friendliness(owner, repo):
    validate_owner_repo(owner, repo)
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
    validate_owner_repo(owner, name)
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
    total += 5
    return {'repo': repo['full_name'], 'stars': repo['stargazers_count'], 'score': total, 
            'activity': act, 'response': resp, 'url': repo['html_url']}

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Usage: score_repos.py <candidates.json>", file=sys.stderr)
        sys.exit(1)
    
    try:
        input_path = validate_file_path(sys.argv[1])
    except ValueError as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)
    
    try:
        with open(input_path) as f: data = json.load(f).get('items', [])
    except json.JSONDecodeError as e:
        print(f"Error: Invalid JSON in {input_path}: {e}", file=sys.stderr)
        sys.exit(1)
    
    results = []
    for r in data[:20]:
        try: results.append(score(r)); print(f"Scored {r['full_name']}", file=sys.stderr)
        except Exception as e: print(f"Error {r['full_name']}: {e}", file=sys.stderr)
    results.sort(key=lambda x: x['score'], reverse=True)
    print(json.dumps(results, indent=2))
