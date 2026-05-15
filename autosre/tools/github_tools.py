"""
AutoSRE — GitHub Tools
Create issues, comment on PRs, and check deployments via GitHub API.
Gracefully falls back to console logging if no token is configured.
"""

import logging
from typing import Any, Dict, List, Optional

from config import settings

logger = logging.getLogger("autosre.tools.github")


def _get_github_client():
    """Get authenticated PyGithub client, or None if unavailable."""
    if not settings.has_github():
        return None
    try:
        from github import Github
        return Github(settings.GITHUB_TOKEN)
    except ImportError:
        logger.warning("PyGithub not installed")
        return None
    except Exception as e:
        logger.warning(f"GitHub client init failed: {e}")
        return None


def create_issue(
    title: str,
    body: str,
    labels: List[str] = None,
    assignees: List[str] = None,
    repo_owner: str = None,
    repo_name: str = None,
) -> Dict[str, Any]:
    """Create a GitHub issue with full incident context.
    
    Falls back to console logging if GitHub is not configured.
    """
    owner = repo_owner or settings.GITHUB_REPO_OWNER
    repo = repo_name or settings.GITHUB_REPO_NAME
    labels = labels or ["incident", "autosre"]

    logger.info(f"[github] Creating issue: {title}")

    gh = _get_github_client()
    if gh and owner and repo:
        try:
            repository = gh.get_repo(f"{owner}/{repo}")
            issue = repository.create_issue(
                title=title,
                body=body,
                labels=labels,
            )
            result = {
                "status": "created",
                "issue_number": issue.number,
                "html_url": issue.html_url,
                "title": title,
                "labels": labels,
            }
            logger.info(f"[github] Issue created: {issue.html_url}")
            return result
        except Exception as e:
            logger.error(f"[github] Failed to create issue: {e}")
            return {
                "status": "error",
                "error": str(e),
                "title": title,
                "fallback": "console",
            }
    else:
        # Simulated output
        result = {
            "status": "simulated",
            "issue_number": 9999,
            "html_url": f"https://github.com/{owner or 'org'}/{repo or 'repo'}/issues/9999",
            "title": title,
            "body_preview": body[:200],
            "labels": labels,
            "note": "GitHub integration simulated — no token or repo configured",
        }
        logger.info(f"[github] SIMULATED issue: {title}")
        return result


def comment_on_pr(
    pr_number: int,
    body: str,
    repo_owner: str = None,
    repo_name: str = None,
) -> Dict[str, Any]:
    """Post a comment on a GitHub PR."""
    owner = repo_owner or settings.GITHUB_REPO_OWNER
    repo = repo_name or settings.GITHUB_REPO_NAME

    logger.info(f"[github] Commenting on PR #{pr_number}")

    gh = _get_github_client()
    if gh and owner and repo:
        try:
            repository = gh.get_repo(f"{owner}/{repo}")
            pr = repository.get_pull(pr_number)
            comment = pr.create_issue_comment(body)
            return {
                "status": "posted",
                "comment_id": comment.id,
                "pr_number": pr_number,
            }
        except Exception as e:
            logger.error(f"[github] Failed to comment on PR: {e}")
            return {"status": "error", "error": str(e)}
    else:
        return {
            "status": "simulated",
            "pr_number": pr_number,
            "body_preview": body[:200],
            "note": "GitHub integration simulated",
        }


def list_recent_deploys(repo_owner: str = None, repo_name: str = None,
                        limit: int = 5) -> Dict[str, Any]:
    """List recent deployments for context."""
    owner = repo_owner or settings.GITHUB_REPO_OWNER
    repo = repo_name or settings.GITHUB_REPO_NAME

    gh = _get_github_client()
    if gh and owner and repo:
        try:
            repository = gh.get_repo(f"{owner}/{repo}")
            deployments = list(repository.get_deployments()[:limit])
            return {
                "status": "success",
                "deployments": [
                    {
                        "id": d.id,
                        "ref": d.ref,
                        "environment": d.environment,
                        "created_at": str(d.created_at),
                        "creator": d.creator.login if d.creator else "unknown",
                    }
                    for d in deployments
                ],
            }
        except Exception as e:
            logger.error(f"Failed to list deployments: {e}")

    # Simulated deployments for demo
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    return {
        "status": "simulated",
        "deployments": [
            {
                "id": 50001,
                "ref": "main",
                "sha": "a1b2c3d",
                "environment": "production",
                "created_at": (now - timedelta(minutes=47)).isoformat(),
                "creator": "dev-engineer",
                "description": "Deploy PR #4587 — Add order validation v2",
            },
            {
                "id": 50000,
                "ref": "main",
                "sha": "e4f5g6h",
                "environment": "production",
                "created_at": (now - timedelta(hours=6)).isoformat(),
                "creator": "ci-bot",
                "description": "Deploy PR #4582 — Update payment SDK",
            },
        ],
    }


def trigger_rollback(
    deployment_id: int = None,
    repo_owner: str = None,
    repo_name: str = None,
) -> Dict[str, Any]:
    """Trigger a deployment rollback (simulated for safety)."""
    logger.info(f"[github] Triggering rollback for deployment {deployment_id}")

    # Always simulated — real rollbacks are too dangerous for autonomous execution
    return {
        "status": "simulated",
        "action": "rollback",
        "deployment_id": deployment_id or 50001,
        "message": "Rollback triggered (simulated). In production, this would revert to the previous stable deployment.",
        "recommendation": "Manual confirmation recommended before executing real rollback.",
    }
