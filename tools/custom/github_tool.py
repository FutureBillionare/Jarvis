"""
Tool: github_tool
Description: Interact with GitHub — repos, issues, PRs, commits, and more.
Requires: GITHUB_TOKEN environment variable.
"""
import os, subprocess


def _gh():
    from github import Github
    token = os.environ.get("GITHUB_TOKEN", "")
    if not token:
        raise RuntimeError("Set the GITHUB_TOKEN environment variable.")
    return Github(token)


def run_list_repos(params):
    g     = _gh()
    user  = g.get_user()
    repos = list(user.get_repos(sort="updated", direction="desc"))[:20]
    lines = [f"{'REPO':<40} {'LANG':<15} {'STARS':<8} {'UPDATED'}"]
    lines.append("─" * 80)
    for r in repos:
        lang    = r.language or "—"
        updated = str(r.updated_at)[:10]
        lines.append(f"{r.full_name:<40} {lang:<15} {r.stargazers_count:<8} {updated}")
    return "\n".join(lines)


def run_get_repo(params):
    g    = _gh()
    repo = g.get_repo(params["repo"])
    return (
        f"Repo:        {repo.full_name}\n"
        f"Description: {repo.description or '—'}\n"
        f"Language:    {repo.language or '—'}\n"
        f"Stars:       {repo.stargazers_count}\n"
        f"Forks:       {repo.forks_count}\n"
        f"Open issues: {repo.open_issues_count}\n"
        f"Default branch: {repo.default_branch}\n"
        f"URL:         {repo.html_url}"
    )


def run_list_issues(params):
    g     = _gh()
    repo  = g.get_repo(params["repo"])
    state = params.get("state", "open")
    limit = params.get("limit", 15)
    issues = list(repo.get_issues(state=state))[:limit]
    if not issues:
        return f"No {state} issues in {params['repo']}."
    lines = [f"{'#':<6} {'TITLE':<50} {'LABELS'}"]
    lines.append("─" * 75)
    for i in issues:
        labels = ", ".join(l.name for l in i.labels)
        lines.append(f"#{i.number:<5} {i.title[:48]:<50} {labels}")
    return "\n".join(lines)


def run_create_issue(params):
    g     = _gh()
    repo  = g.get_repo(params["repo"])
    issue = repo.create_issue(
        title  = params["title"],
        body   = params.get("body", ""),
        labels = params.get("labels", []),
    )
    return f"Issue created: #{issue.number}  {issue.html_url}"


def run_list_prs(params):
    g     = _gh()
    repo  = g.get_repo(params["repo"])
    state = params.get("state", "open")
    prs   = list(repo.get_pulls(state=state))[:15]
    if not prs:
        return f"No {state} PRs in {params['repo']}."
    lines = [f"{'#':<6} {'TITLE':<50} {'BRANCH'}"]
    lines.append("─" * 75)
    for pr in prs:
        lines.append(f"#{pr.number:<5} {pr.title[:48]:<50} {pr.head.ref}")
    return "\n".join(lines)


def run_create_pr(params):
    g    = _gh()
    repo = g.get_repo(params["repo"])
    pr   = repo.create_pull(
        title = params["title"],
        body  = params.get("body", ""),
        head  = params["head_branch"],
        base  = params.get("base_branch", repo.default_branch),
    )
    return f"PR created: #{pr.number}  {pr.html_url}"


def run_git_status(params):
    path   = params.get("path", ".")
    result = subprocess.run("git status", cwd=path, shell=True,
                            capture_output=True, text=True)
    return result.stdout or result.stderr


def run_git_commit_push(params):
    message = params["message"]
    path    = params.get("path", ".")
    branch  = params.get("branch", "")
    cmds    = [
        f'git -C "{path}" add -A',
        f'git -C "{path}" commit -m "{message}"',
        f'git -C "{path}" push' + (f" origin {branch}" if branch else ""),
    ]
    output = []
    for cmd in cmds:
        r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
        output.append((cmd.split()[2], r.stdout or r.stderr))
    return "\n".join(f"{c}: {o.strip()}" for c, o in output)


TOOLS = [
    ({"name": "github_list_repos",
      "description": "List your GitHub repositories sorted by most recently updated.",
      "input_schema": {"type": "object", "properties": {}}}, run_list_repos),

    ({"name": "github_get_repo",
      "description": "Get details about a GitHub repository.",
      "input_schema": {"type": "object", "properties": {
          "repo": {"type": "string", "description": "owner/repo format"}
      }, "required": ["repo"]}}, run_get_repo),

    ({"name": "github_list_issues",
      "description": "List issues in a GitHub repository.",
      "input_schema": {"type": "object", "properties": {
          "repo":  {"type": "string", "description": "owner/repo"},
          "state": {"type": "string", "enum": ["open", "closed", "all"], "description": "Default: open"},
          "limit": {"type": "integer"},
      }, "required": ["repo"]}}, run_list_issues),

    ({"name": "github_create_issue",
      "description": "Create a new issue in a GitHub repository.",
      "input_schema": {"type": "object", "properties": {
          "repo":   {"type": "string"},
          "title":  {"type": "string"},
          "body":   {"type": "string"},
          "labels": {"type": "array", "items": {"type": "string"}},
      }, "required": ["repo", "title"]}}, run_create_issue),

    ({"name": "github_list_prs",
      "description": "List pull requests in a GitHub repository.",
      "input_schema": {"type": "object", "properties": {
          "repo":  {"type": "string"},
          "state": {"type": "string", "enum": ["open", "closed", "all"]},
      }, "required": ["repo"]}}, run_list_prs),

    ({"name": "github_create_pr",
      "description": "Create a pull request in a GitHub repository.",
      "input_schema": {"type": "object", "properties": {
          "repo":        {"type": "string"},
          "title":       {"type": "string"},
          "head_branch": {"type": "string", "description": "Source branch"},
          "base_branch": {"type": "string", "description": "Target branch (default: main)"},
          "body":        {"type": "string"},
      }, "required": ["repo", "title", "head_branch"]}}, run_create_pr),

    ({"name": "github_git_status",
      "description": "Run git status in a local repository directory.",
      "input_schema": {"type": "object", "properties": {
          "path": {"type": "string", "description": "Local repo path (default: current directory)"}
      }}}, run_git_status),

    ({"name": "github_commit_push",
      "description": "Stage all changes, commit with a message, and push to remote.",
      "input_schema": {"type": "object", "properties": {
          "message": {"type": "string", "description": "Commit message"},
          "path":    {"type": "string", "description": "Local repo path"},
          "branch":  {"type": "string", "description": "Branch to push to (optional)"},
      }, "required": ["message"]}}, run_git_commit_push),
]
