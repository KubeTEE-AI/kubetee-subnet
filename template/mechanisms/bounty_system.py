# The MIT License (MIT)
# Copyright © 2023 KubeTEE AI

"""
KubeTEE Bounty-Based Open Source Incentive System

GITHUB ISSUES AS BOUNTIES:
══════════════════════════
- Bounties ARE GitHub Issues in KubeTEE-AI organization repositories
- GitHub labels define difficulty: `bounty:easy`, `bounty:medium`, `bounty:hard`, `bounty:epic`
- Each bounty has an associated HOTKEY where emissions accumulate
- When bounty is won, accumulated emissions transfer to winner's hotkey

┌─────────────────────────────────────────────────────────────────────────────┐
│                    GITHUB ISSUES = BOUNTIES                                 │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                             │
│  Example GitHub Issue:                                                      │
│  ─────────────────────                                                      │
│  ┌─────────────────────────────────────────────────────────────────────┐    │
│  │  Issue #42: "Optimize batch inference pipeline"                     │    │
│  │                                                                     │    │
│  │  Labels: [bounty:hard] [category:optimization]                      │    │
│  │  Bounty Hotkey: 5FHneW46...abc123                                   │    │
│  │  Accumulated: 47.3 Alpha (receiving emissions each epoch)           │    │
│  │                                                                     │    │
│  │  Acceptance Criteria:                                               │    │
│  │  - [ ] Throughput improved by 2x                                    │    │
│  │  - [ ] All CI tests pass                                            │    │
│  │  - [ ] No memory regression                                         │    │
│  └─────────────────────────────────────────────────────────────────────┘    │
│                                                                             │
│  EMISSION FLOW:                                                             │
│  ─────────────                                                              │
│  Subnet → Open Source (40%) → Bounty Pool (60%) → Bounty Hotkeys            │
│                                                                             │
│  DIFFICULTY WEIGHTS (for emission distribution):                            │
│  ──────────────────────────────────────────────                             │
│  • bounty:easy   → 1x weight                                                │
│  • bounty:medium → 2x weight                                                │
│  • bounty:hard   → 4x weight                                                │
│  • bounty:epic   → 8x weight                                                │
│                                                                             │
│  CATEGORY LABELS:                                                           │
│  ────────────────                                                           │
│  • category:bug-fix       • category:feature                                │
│  • category:documentation • category:benchmark                              │
│  • category:security      • category:optimization                           │
│  • category:testing                                                         │
│                                                                             │
└─────────────────────────────────────────────────────────────────────────────┘

BOUNTY LIFECYCLE (FULLY AUTOMATED):
1. Subnet owner creates GitHub Issue with `bounty:*` label
2. System generates hotkey for the bounty (stored in issue body)
3. Emissions accumulate on bounty hotkey each epoch (weighted by difficulty)
4. Miner submits PR with "Fixes #42" in commit message
5. AUTOMATED VALIDATION: CI/CD + AI analysis
6. If approved → Accumulated emissions transfer to winner's hotkey
7. GitHub Issue closed, `bounty:completed` label added

KEY DESIGN PRINCIPLES:
- GitHub Issues = Single source of truth for bounties
- Emissions accumulate on bounty hotkeys until won (higher rewards over time!)
- NO HUMAN IN THE LOOP for validation
- Fully automated via CI/CD + AI analysis
- Subnet owner has final authority for edge cases
"""

import os
import time
import json
import hashlib
import httpx
import numpy as np
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional, Set, Tuple
from pathlib import Path
from enum import Enum
import bittensor as bt


# =============================================================================
# EMISSION ALLOCATION
# =============================================================================

# Distribution of Open Source mechanism emissions (40% of total subnet)
BOUNTY_POOL_SHARE = 0.60       # 60% goes to bounties
CONTINUOUS_SHARE = 0.30        # 30% goes to continuous contributions
BENCHMARK_BONUS_SHARE = 0.10   # 10% goes to benchmark improvements

# GitHub Organization
GITHUB_ORG = "KubeTEE-AI"


# =============================================================================
# GITHUB LABEL DEFINITIONS
# =============================================================================

# Difficulty labels (bounty:*)
GITHUB_LABEL_BOUNTY_EASY = "bounty:easy"
GITHUB_LABEL_BOUNTY_MEDIUM = "bounty:medium"
GITHUB_LABEL_BOUNTY_HARD = "bounty:hard"
GITHUB_LABEL_BOUNTY_EPIC = "bounty:epic"
GITHUB_LABEL_BOUNTY_COMPLETED = "bounty:completed"

# Category labels (category:*)
GITHUB_LABEL_CATEGORY_BUG = "category:bug-fix"
GITHUB_LABEL_CATEGORY_FEATURE = "category:feature"
GITHUB_LABEL_CATEGORY_DOCS = "category:documentation"
GITHUB_LABEL_CATEGORY_BENCHMARK = "category:benchmark"
GITHUB_LABEL_CATEGORY_SECURITY = "category:security"
GITHUB_LABEL_CATEGORY_OPTIMIZATION = "category:optimization"
GITHUB_LABEL_CATEGORY_TESTING = "category:testing"

# Map GitHub labels to enums
LABEL_TO_DIFFICULTY = {
    GITHUB_LABEL_BOUNTY_EASY: "easy",
    GITHUB_LABEL_BOUNTY_MEDIUM: "medium",
    GITHUB_LABEL_BOUNTY_HARD: "hard",
    GITHUB_LABEL_BOUNTY_EPIC: "epic",
}

LABEL_TO_CATEGORY = {
    GITHUB_LABEL_CATEGORY_BUG: "bug_fix",
    GITHUB_LABEL_CATEGORY_FEATURE: "feature",
    GITHUB_LABEL_CATEGORY_DOCS: "documentation",
    GITHUB_LABEL_CATEGORY_BENCHMARK: "benchmark",
    GITHUB_LABEL_CATEGORY_SECURITY: "security",
    GITHUB_LABEL_CATEGORY_OPTIMIZATION: "optimization",
    GITHUB_LABEL_CATEGORY_TESTING: "testing",
}


# =============================================================================
# BOUNTY DEFINITIONS
# =============================================================================

class BountyStatus(str, Enum):
    """Status of a bounty."""
    OPEN = "open"                # Available for claims
    CLAIMED = "claimed"          # Someone is working on it
    SUBMITTED = "submitted"      # Solution submitted, pending review
    COMPLETED = "completed"      # Successfully completed and paid
    EXPIRED = "expired"          # Time limit exceeded
    CANCELLED = "cancelled"      # Cancelled by creator


class BountyDifficulty(str, Enum):
    """Bounty difficulty levels (affects emission weight)."""
    EASY = "easy"           # 1x weight - Good for newcomers
    MEDIUM = "medium"       # 2x weight - Standard tasks
    HARD = "hard"           # 4x weight - Complex improvements
    EPIC = "epic"           # 8x multiplier - Major features


class BountyCategory(str, Enum):
    """Categories of bounties."""
    BUG_FIX = "bug_fix"
    FEATURE = "feature"
    DOCUMENTATION = "documentation"
    BENCHMARK = "benchmark"
    SECURITY = "security"
    OPTIMIZATION = "optimization"
    TESTING = "testing"


# Base payout per bounty (in Alpha tokens, adjusted by difficulty)
BASE_BOUNTY_PAYOUT = 10.0  # 10 Alpha base

DIFFICULTY_MULTIPLIERS = {
    BountyDifficulty.EASY: 1.0,
    BountyDifficulty.MEDIUM: 2.0,
    BountyDifficulty.HARD: 4.0,
    BountyDifficulty.EPIC: 8.0,
}


@dataclass
class Bounty:
    """
    A bounty for a specific open source contribution.
    
    Bounties ARE GitHub Issues in KubeTEE-AI organization repos.
    Each bounty has an associated hotkey where emissions accumulate
    until the bounty is won.
    
    GitHub Labels:
    - bounty:easy/medium/hard/epic → Difficulty (affects emission weight)
    - category:* → Category of work
    """
    
    # GitHub Issue Integration (Primary Source of Truth)
    github_repo: str                # e.g., "KubeTEE-AI/blueprints"
    github_issue_number: int        # Issue number in the repo
    github_issue_url: str           # Full URL to the issue
    
    # Bounty Hotkey (where emissions accumulate)
    bounty_hotkey: str              # SS58 address where emissions go
    bounty_coldkey: Optional[str] = None  # Associated coldkey (if generated)
    
    # Identification (derived from GitHub)
    bounty_id: str = ""             # Unique ID: "{repo}#{issue_number}"
    title: str = ""                 # Issue title
    description: str = ""           # Issue body
    
    # Classification (from GitHub labels)
    category: BountyCategory = BountyCategory.FEATURE
    difficulty: BountyDifficulty = BountyDifficulty.MEDIUM
    
    # Emission tracking
    accumulated_emissions: float = 0.0  # Alpha accumulated on bounty hotkey
    emission_weight: float = 1.0        # Weight for emission distribution
    
    # Acceptance criteria (parsed from issue body checkboxes)
    acceptance_criteria: List[str] = field(default_factory=list)
    automated_tests: List[str] = field(default_factory=list)
    
    # Target
    target_branch: str = "main"     # Branch to merge into
    
    # Status tracking
    status: BountyStatus = BountyStatus.OPEN
    created_at: float = field(default_factory=time.time)
    expires_at: Optional[float] = None  # None = no expiry
    
    # Claimant (who's working on it)
    claimed_by: Optional[str] = None  # Miner hotkey
    claimed_at: Optional[float] = None
    claim_expires_at: Optional[float] = None  # Must submit within this time
    
    # Submission
    submitted_by: Optional[str] = None
    submitted_at: Optional[float] = None
    pr_url: Optional[str] = None
    
    # Automated Validation Results (NO human in the loop)
    ci_tests_passed: bool = False
    ci_test_results: Optional[str] = None
    ai_code_quality_score: float = 0.0  # 0-100
    ai_security_score: float = 0.0      # 0-100
    ai_analysis_summary: Optional[str] = None
    benchmark_delta: float = 0.0        # % change in benchmark
    validation_timestamp: Optional[float] = None
    
    # Thresholds for auto-approval
    min_code_quality_score: float = 70.0  # Auto-approve if >= this
    min_security_score: float = 80.0      # Must pass security
    
    # Completion
    completed_at: Optional[float] = None
    paid_to: Optional[str] = None
    paid_amount: float = 0.0
    
    # Subnet owner decision (final authority)
    subnet_owner_approved: Optional[bool] = None
    subnet_owner_notes: Optional[str] = None
    
    @property
    def total_payout(self) -> float:
        """Calculate total payout including difficulty multiplier."""
        return self.base_payout * self.payout_multiplier
    
    def claim(self, miner_hotkey: str, claim_duration_hours: float = 72):
        """Claim this bounty for work."""
        if self.status != BountyStatus.OPEN:
            raise ValueError(f"Bounty {self.bounty_id} is not open for claims")
        
        self.claimed_by = miner_hotkey
        self.claimed_at = time.time()
        self.claim_expires_at = time.time() + (claim_duration_hours * 3600)
        self.status = BountyStatus.CLAIMED
    
    def submit(self, miner_hotkey: str, pr_url: str):
        """Submit a solution for this bounty."""
        if self.status not in [BountyStatus.OPEN, BountyStatus.CLAIMED]:
            raise ValueError(f"Bounty {self.bounty_id} cannot accept submissions")
        
        # If claimed by someone else, reject
        if self.claimed_by and self.claimed_by != miner_hotkey:
            # Check if claim expired
            if self.claim_expires_at and time.time() < self.claim_expires_at:
                raise ValueError(f"Bounty is claimed by another miner")
        
        self.submitted_by = miner_hotkey
        self.submitted_at = time.time()
        self.pr_url = pr_url
        self.status = BountyStatus.SUBMITTED
    
    def record_validation_results(
        self,
        ci_passed: bool,
        ci_results: str,
        code_quality_score: float,
        security_score: float,
        ai_summary: str,
        benchmark_delta: float = 0.0,
    ):
        """
        Record automated validation results.
        
        Called by the subnet owner's validator after running:
        - CI/CD tests (GitHub Actions)
        - AI code analysis
        - Benchmark tests
        """
        self.ci_tests_passed = ci_passed
        self.ci_test_results = ci_results
        self.ai_code_quality_score = min(100.0, max(0.0, code_quality_score))
        self.ai_security_score = min(100.0, max(0.0, security_score))
        self.ai_analysis_summary = ai_summary
        self.benchmark_delta = benchmark_delta
        self.validation_timestamp = time.time()
    
    def check_auto_approval(self) -> bool:
        """
        Check if bounty meets auto-approval criteria.
        
        Returns True if all automated checks pass thresholds.
        """
        if not self.ci_tests_passed:
            return False
        
        if self.ai_code_quality_score < self.min_code_quality_score:
            return False
        
        if self.ai_security_score < self.min_security_score:
            return False
        
        # For benchmark bounties, must show improvement
        if self.category == BountyCategory.BENCHMARK and self.benchmark_delta < 0:
            return False
        
        return True
    
    def auto_approve(self) -> bool:
        """
        Attempt auto-approval based on automated validation.
        
        Returns True if approved, False if manual review needed.
        """
        if self.status != BountyStatus.SUBMITTED:
            raise ValueError("No submission to approve")
        
        if self.check_auto_approval():
            self.subnet_owner_approved = True
            self.subnet_owner_notes = "Auto-approved: All automated checks passed"
            self.complete()
            return True
        
        return False  # Needs subnet owner manual review
    
    def subnet_owner_decision(self, approved: bool, notes: str = ""):
        """
        Subnet owner makes final decision (for edge cases).
        
        Used when auto-approval fails but owner wants to approve,
        or when owner wants to reject despite passing checks.
        """
        if self.status != BountyStatus.SUBMITTED:
            raise ValueError("No submission to review")
        
        self.subnet_owner_approved = approved
        self.subnet_owner_notes = notes
        
        if approved:
            self.complete()
        else:
            # Rejected - reopen bounty
            self.status = BountyStatus.OPEN
            self.submitted_by = None
            self.submitted_at = None
            self.pr_url = None
            self.ci_tests_passed = False
            self.ai_code_quality_score = 0.0
            self.ai_security_score = 0.0
    
    def complete(self):
        """Mark bounty as completed and calculate payout."""
        self.status = BountyStatus.COMPLETED
        self.completed_at = time.time()
        self.paid_to = self.submitted_by
        self.paid_amount = self.total_payout
    
    def to_dict(self) -> dict:
        data = asdict(self)
        data['category'] = self.category.value
        data['difficulty'] = self.difficulty.value
        data['status'] = self.status.value
        return data
    
    @classmethod
    def from_dict(cls, data: dict) -> "Bounty":
        data['category'] = BountyCategory(data['category'])
        data['difficulty'] = BountyDifficulty(data['difficulty'])
        data['status'] = BountyStatus(data['status'])
        return cls(**data)


# =============================================================================
# CONTINUOUS CONTRIBUTION TRACKING
# =============================================================================

class ContributionType(str, Enum):
    """Types of continuous contributions."""
    PR_MERGED = "pr_merged"           # Pull request merged
    BUG_FIX = "bug_fix"               # Bug fix merged
    DOCUMENTATION = "documentation"   # Docs improvement
    TEST_ADDED = "test_added"         # Test coverage increase
    CODE_REVIEW = "code_review"       # Helpful code review
    ISSUE_TRIAGED = "issue_triaged"   # Issue triaged/labeled


# Points per contribution type
CONTRIBUTION_POINTS = {
    ContributionType.PR_MERGED: 10,
    ContributionType.BUG_FIX: 15,
    ContributionType.DOCUMENTATION: 5,
    ContributionType.TEST_ADDED: 8,
    ContributionType.CODE_REVIEW: 3,
    ContributionType.ISSUE_TRIAGED: 2,
}


@dataclass
class Contribution:
    """A single contribution from a miner."""
    contribution_id: str
    miner_hotkey: str
    contribution_type: ContributionType
    points: int
    description: str
    pr_url: Optional[str] = None
    timestamp: float = field(default_factory=time.time)
    epoch: int = 0
    
    def to_dict(self) -> dict:
        data = asdict(self)
        data['contribution_type'] = self.contribution_type.value
        return data
    
    @classmethod
    def from_dict(cls, data: dict) -> "Contribution":
        data['contribution_type'] = ContributionType(data['contribution_type'])
        return cls(**data)


@dataclass
class MinerContributionProfile:
    """Tracks a miner's contribution history and accumulated points."""
    miner_hotkey: str
    total_points: int = 0
    epoch_points: int = 0  # Points this epoch
    
    # Contribution counts by type
    pr_count: int = 0
    bug_fixes: int = 0
    doc_contributions: int = 0
    tests_added: int = 0
    reviews_given: int = 0
    
    # Bounty stats
    bounties_completed: int = 0
    bounties_claimed: int = 0
    total_bounty_earnings: float = 0.0
    
    # History
    contributions: List[str] = field(default_factory=list)  # Contribution IDs
    first_contribution: Optional[float] = None
    last_contribution: Optional[float] = None
    
    def add_contribution(self, contribution: Contribution):
        """Add a contribution and update stats."""
        self.total_points += contribution.points
        self.epoch_points += contribution.points
        self.contributions.append(contribution.contribution_id)
        
        if self.first_contribution is None:
            self.first_contribution = contribution.timestamp
        self.last_contribution = contribution.timestamp
        
        # Update type-specific counts
        if contribution.contribution_type == ContributionType.PR_MERGED:
            self.pr_count += 1
        elif contribution.contribution_type == ContributionType.BUG_FIX:
            self.bug_fixes += 1
        elif contribution.contribution_type == ContributionType.DOCUMENTATION:
            self.doc_contributions += 1
        elif contribution.contribution_type == ContributionType.TEST_ADDED:
            self.tests_added += 1
        elif contribution.contribution_type == ContributionType.CODE_REVIEW:
            self.reviews_given += 1
    
    def reset_epoch(self):
        """Reset epoch points for new epoch."""
        self.epoch_points = 0
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "MinerContributionProfile":
        return cls(**data)


# =============================================================================
# BOUNTY MANAGER
# =============================================================================

class BountyManager:
    """
    Manages the bounty-based open source incentive system.
    
    GITHUB ISSUES = BOUNTIES:
    - Syncs with GitHub Issues in KubeTEE-AI organization repos
    - Issues with `bounty:*` labels become bounties
    - Each bounty gets a hotkey where emissions accumulate
    - Winner receives accumulated emissions when bounty is completed
    
    Key Features:
    - GitHub Issues as single source of truth
    - Emissions accumulate on bounty hotkeys until won
    - Automated validation via CI/CD + AI analysis
    - Subnet owner final authority
    """
    
    def __init__(
        self,
        storage_path: str,
        github_token: str = None,
        github_org: str = GITHUB_ORG,
    ):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        # GitHub integration
        self.github_token = github_token or os.environ.get("GITHUB_TOKEN", "")
        self.github_org = github_org
        
        # Bounties (synced from GitHub Issues)
        self.bounties: Dict[str, Bounty] = {}
        
        # Contributions
        self.contributions: Dict[str, Contribution] = {}
        self.miner_profiles: Dict[str, MinerContributionProfile] = {}
        
        # Epoch tracking
        self.current_epoch: int = 0
        
        # Emission pools (accumulated from subnet emissions)
        self.bounty_pool: float = 0.0
        self.continuous_pool: float = 0.0
        self.benchmark_pool: float = 0.0
        
        # Load data
        self._load_data()
        
        bt.logging.info(
            f"BountyManager initialized:\n"
            f"  GitHub Org: {self.github_org}\n"
            f"  Open Bounties: {len([b for b in self.bounties.values() if b.status == BountyStatus.OPEN])}\n"
            f"  Active Contributors: {len(self.miner_profiles)}\n"
            f"  Bounty Pool: {self.bounty_pool:.2f} Alpha\n"
            f"  Continuous Pool: {self.continuous_pool:.2f} Alpha"
        )
    
    # =========================================================================
    # GITHUB ISSUE SYNC
    # =========================================================================
    
    async def sync_bounties_from_github(self, repos: List[str] = None) -> List[Bounty]:
        """
        Sync bounties from GitHub Issues across KubeTEE-AI organization.
        
        Issues with `bounty:*` labels become bounties.
        Each bounty gets a dedicated hotkey where emissions accumulate.
        
        Args:
            repos: List of repos to sync (e.g., ["blueprints", "kubetee-subnet"])
                   If None, syncs all repos in the organization.
        
        Returns:
            List of new/updated bounties
        """
        if not self.github_token:
            bt.logging.warning("No GitHub token provided, cannot sync bounties")
            return []
        
        synced_bounties = []
        
        async with httpx.AsyncClient() as client:
            # Get repos to sync
            if repos is None:
                repos = await self._get_org_repos(client)
            
            for repo_name in repos:
                issues = await self._get_bounty_issues(client, repo_name)
                
                for issue in issues:
                    bounty = await self._issue_to_bounty(issue, repo_name)
                    if bounty:
                        self.bounties[bounty.bounty_id] = bounty
                        synced_bounties.append(bounty)
        
        self._save_data()
        bt.logging.info(f"Synced {len(synced_bounties)} bounties from GitHub")
        return synced_bounties
    
    async def _get_org_repos(self, client: httpx.AsyncClient) -> List[str]:
        """Get all repositories in the organization."""
        url = f"https://api.github.com/orgs/{self.github_org}/repos"
        response = await client.get(
            url,
            headers=self._github_headers(),
            params={"per_page": 100},
        )
        
        if response.status_code == 200:
            repos = response.json()
            return [repo["name"] for repo in repos]
        return []
    
    async def _get_bounty_issues(
        self,
        client: httpx.AsyncClient,
        repo_name: str,
    ) -> List[dict]:
        """Get all issues with bounty labels from a repository."""
        url = f"https://api.github.com/repos/{self.github_org}/{repo_name}/issues"
        
        # Get open issues with any bounty label
        all_issues = []
        
        for difficulty_label in [
            GITHUB_LABEL_BOUNTY_EASY,
            GITHUB_LABEL_BOUNTY_MEDIUM,
            GITHUB_LABEL_BOUNTY_HARD,
            GITHUB_LABEL_BOUNTY_EPIC,
        ]:
            response = await client.get(
                url,
                headers=self._github_headers(),
                params={
                    "state": "open",
                    "labels": difficulty_label,
                    "per_page": 100,
                },
            )
            
            if response.status_code == 200:
                all_issues.extend(response.json())
        
        # Deduplicate by issue number
        seen = set()
        unique_issues = []
        for issue in all_issues:
            if issue["number"] not in seen:
                seen.add(issue["number"])
                unique_issues.append(issue)
        
        return unique_issues
    
    async def _issue_to_bounty(
        self,
        issue: dict,
        repo_name: str,
    ) -> Optional[Bounty]:
        """Convert a GitHub Issue to a Bounty."""
        labels = [l["name"] for l in issue.get("labels", [])]
        
        # Determine difficulty from labels
        difficulty = BountyDifficulty.MEDIUM
        for label in labels:
            if label in LABEL_TO_DIFFICULTY:
                difficulty = BountyDifficulty(LABEL_TO_DIFFICULTY[label])
                break
        
        # Determine category from labels
        category = BountyCategory.FEATURE
        for label in labels:
            if label in LABEL_TO_CATEGORY:
                category = BountyCategory(LABEL_TO_CATEGORY[label])
                break
        
        # Generate bounty ID
        bounty_id = f"{self.github_org}/{repo_name}#{issue['number']}"
        
        # Check if bounty already exists
        existing = self.bounties.get(bounty_id)
        if existing:
            # Update existing bounty
            existing.title = issue["title"]
            existing.description = issue.get("body", "")
            existing.difficulty = difficulty
            existing.category = category
            existing.emission_weight = DIFFICULTY_MULTIPLIERS[difficulty]
            return existing
        
        # Parse acceptance criteria from issue body (checkboxes)
        acceptance_criteria = self._parse_checkboxes(issue.get("body", ""))
        
        # Extract or generate bounty hotkey from issue body
        bounty_hotkey = self._extract_bounty_hotkey(issue.get("body", ""))
        if not bounty_hotkey:
            bounty_hotkey = self._generate_bounty_hotkey(bounty_id)
        
        # Create new bounty
        bounty = Bounty(
            github_repo=f"{self.github_org}/{repo_name}",
            github_issue_number=issue["number"],
            github_issue_url=issue["html_url"],
            bounty_hotkey=bounty_hotkey,
            bounty_id=bounty_id,
            title=issue["title"],
            description=issue.get("body", ""),
            category=category,
            difficulty=difficulty,
            emission_weight=DIFFICULTY_MULTIPLIERS[difficulty],
            acceptance_criteria=acceptance_criteria,
        )
        
        bt.logging.info(
            f"New bounty from GitHub: {bounty_id} ({difficulty.value})"
        )
        
        return bounty
    
    def _github_headers(self) -> dict:
        """Get GitHub API headers."""
        return {
            "Authorization": f"Bearer {self.github_token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
    
    def _parse_checkboxes(self, body: str) -> List[str]:
        """Parse acceptance criteria from issue body checkboxes."""
        import re
        criteria = []
        
        # Match markdown checkboxes: - [ ] or - [x]
        pattern = r'- \[[ x]\] (.+)'
        matches = re.findall(pattern, body or "", re.MULTILINE)
        
        for match in matches:
            criteria.append(match.strip())
        
        return criteria
    
    def _extract_bounty_hotkey(self, body: str) -> Optional[str]:
        """Extract bounty hotkey from issue body if present."""
        import re
        
        # Look for "Bounty Hotkey: <SS58 address>" pattern
        pattern = r'Bounty Hotkey:\s*`?([a-zA-Z0-9]{48})`?'
        match = re.search(pattern, body or "")
        
        if match:
            return match.group(1)
        return None
    
    def _generate_bounty_hotkey(self, bounty_id: str) -> str:
        """
        Generate a deterministic hotkey for a bounty.
        
        In production, this would generate an actual Bittensor keypair
        and store the mnemonic securely. For now, we create a placeholder.
        """
        # In production: Generate actual keypair
        # wallet = bt.wallet(name=f"bounty_{bounty_id}")
        # wallet.create_new_hotkey(use_password=False)
        # return wallet.hotkey.ss58_address
        
        # Placeholder: Generate deterministic address
        seed = hashlib.sha256(f"bounty:{bounty_id}".encode()).hexdigest()
        return f"5{seed[:47]}"  # Simplified SS58-like address
    
    # =========================================================================
    # BOUNTY MANAGEMENT (Local Operations)
    # =========================================================================
    
    def get_open_bounties(self) -> List[Bounty]:
        """Get all open bounties."""
        return [
            b for b in self.bounties.values()
            if b.status == BountyStatus.OPEN
        ]
    
    def claim_bounty(self, bounty_id: str, miner_hotkey: str) -> Bounty:
        """Claim a bounty for work."""
        if bounty_id not in self.bounties:
            raise ValueError(f"Bounty {bounty_id} not found")
        
        bounty = self.bounties[bounty_id]
        bounty.claim(miner_hotkey)
        
        # Update miner profile
        profile = self._get_or_create_profile(miner_hotkey)
        profile.bounties_claimed += 1
        
        self._save_data()
        
        bt.logging.info(f"Bounty {bounty_id} claimed by {miner_hotkey[:16]}...")
        return bounty
    
    def submit_bounty(
        self,
        bounty_id: str,
        miner_hotkey: str,
        pr_url: str,
    ) -> Bounty:
        """Submit a solution for a bounty."""
        if bounty_id not in self.bounties:
            raise ValueError(f"Bounty {bounty_id} not found")
        
        bounty = self.bounties[bounty_id]
        bounty.submit(miner_hotkey, pr_url)
        
        self._save_data()
        
        bt.logging.info(
            f"Bounty {bounty_id} submission by {miner_hotkey[:16]}...: {pr_url}"
        )
        return bounty
    
    def validate_bounty(
        self,
        bounty_id: str,
        ci_passed: bool,
        ci_results: str,
        code_quality_score: float,
        security_score: float,
        ai_summary: str,
        benchmark_delta: float = 0.0,
    ) -> dict:
        """
        Run automated validation on a bounty submission.
        
        Called by subnet owner's validator after running:
        - CI/CD tests (GitHub Actions)
        - AI code analysis (Claude/GPT-4)
        - Benchmark tests (if applicable)
        
        Returns validation result dict.
        """
        if bounty_id not in self.bounties:
            raise ValueError(f"Bounty {bounty_id} not found")
        
        bounty = self.bounties[bounty_id]
        
        # Record validation results
        bounty.record_validation_results(
            ci_passed=ci_passed,
            ci_results=ci_results,
            code_quality_score=code_quality_score,
            security_score=security_score,
            ai_summary=ai_summary,
            benchmark_delta=benchmark_delta,
        )
        
        # Attempt auto-approval
        auto_approved = bounty.auto_approve()
        
        if auto_approved:
            # Update miner profile
            profile = self._get_or_create_profile(bounty.paid_to)
            profile.bounties_completed += 1
            profile.total_bounty_earnings += bounty.paid_amount
            
            bt.logging.info(
                f"Bounty {bounty_id} AUTO-APPROVED! "
                f"Paid {bounty.paid_amount:.1f} Alpha to {bounty.paid_to[:16]}..."
            )
        else:
            bt.logging.info(
                f"Bounty {bounty_id} needs manual review. "
                f"CI: {'PASS' if ci_passed else 'FAIL'}, "
                f"Quality: {code_quality_score:.0f}/100, "
                f"Security: {security_score:.0f}/100"
            )
        
        self._save_data()
        
        return {
            "bounty_id": bounty_id,
            "auto_approved": auto_approved,
            "ci_passed": ci_passed,
            "code_quality_score": code_quality_score,
            "security_score": security_score,
            "ai_summary": ai_summary,
            "needs_manual_review": not auto_approved,
        }
    
    def subnet_owner_review(
        self,
        bounty_id: str,
        approved: bool,
        notes: str = "",
    ):
        """
        Subnet owner makes final decision on a bounty.
        
        Used for edge cases where auto-approval fails but owner
        wants to approve, or vice versa.
        """
        if bounty_id not in self.bounties:
            raise ValueError(f"Bounty {bounty_id} not found")
        
        bounty = self.bounties[bounty_id]
        bounty.subnet_owner_decision(approved, notes)
        
        if approved:
            # Update miner profile
            profile = self._get_or_create_profile(bounty.paid_to)
            profile.bounties_completed += 1
            profile.total_bounty_earnings += bounty.paid_amount
            
            bt.logging.info(
                f"Bounty {bounty_id} APPROVED by subnet owner! "
                f"Paid {bounty.paid_amount:.1f} Alpha to {bounty.paid_to[:16]}..."
            )
        else:
            bt.logging.info(
                f"Bounty {bounty_id} REJECTED by subnet owner: {notes}"
            )
        
        self._save_data()
    
    # =========================================================================
    # CONTINUOUS CONTRIBUTIONS
    # =========================================================================
    
    def record_contribution(
        self,
        miner_hotkey: str,
        contribution_type: ContributionType,
        description: str,
        pr_url: Optional[str] = None,
    ) -> Contribution:
        """Record a continuous contribution from a miner."""
        
        # Generate ID
        contribution_id = hashlib.sha256(
            f"{miner_hotkey}{time.time()}{description}".encode()
        ).hexdigest()[:12]
        
        points = CONTRIBUTION_POINTS.get(contribution_type, 0)
        
        contribution = Contribution(
            contribution_id=contribution_id,
            miner_hotkey=miner_hotkey,
            contribution_type=contribution_type,
            points=points,
            description=description,
            pr_url=pr_url,
            epoch=self.current_epoch,
        )
        
        self.contributions[contribution_id] = contribution
        
        # Update profile
        profile = self._get_or_create_profile(miner_hotkey)
        profile.add_contribution(contribution)
        
        self._save_data()
        
        bt.logging.debug(
            f"Contribution recorded: {miner_hotkey[:16]}... "
            f"+{points} points ({contribution_type.value})"
        )
        
        return contribution
    
    def get_contribution_leaderboard(self, top_n: int = 20) -> List[Dict]:
        """Get leaderboard of contributors by points."""
        leaderboard = sorted(
            [
                {
                    "rank": 0,
                    "hotkey": profile.miner_hotkey[:16] + "...",
                    "total_points": profile.total_points,
                    "epoch_points": profile.epoch_points,
                    "pr_count": profile.pr_count,
                    "bounties_completed": profile.bounties_completed,
                }
                for profile in self.miner_profiles.values()
            ],
            key=lambda x: x["total_points"],
            reverse=True,
        )
        
        for i, entry in enumerate(leaderboard):
            entry["rank"] = i + 1
        
        return leaderboard[:top_n]
    
    # =========================================================================
    # EMISSION DISTRIBUTION
    # =========================================================================
    
    def receive_emissions(self, total_emissions: float) -> Dict[str, float]:
        """
        Receive emissions and distribute to bounty hotkeys.
        
        Called each epoch with the Open Source mechanism's share.
        
        FLOW:
        1. Split emissions: 60% bounties, 30% continuous, 10% benchmark
        2. Distribute bounty pool to open bounty hotkeys (weighted by difficulty)
        3. Track accumulated emissions on each bounty hotkey
        4. When bounty is won, transfer accumulated emissions to winner
        
        Returns:
            Dict mapping bounty hotkeys to their emission amounts
        """
        # Split into pools
        bounty_emissions = total_emissions * BOUNTY_POOL_SHARE
        self.continuous_pool += total_emissions * CONTINUOUS_SHARE
        self.benchmark_pool += total_emissions * BENCHMARK_BONUS_SHARE
        
        # Get open bounties and their weights
        open_bounties = [
            b for b in self.bounties.values()
            if b.status == BountyStatus.OPEN
        ]
        
        if not open_bounties:
            # No open bounties, add to continuous pool
            self.continuous_pool += bounty_emissions
            bt.logging.info(
                f"No open bounties, added {bounty_emissions:.2f} to continuous pool"
            )
            return {}
        
        # Calculate total weight
        total_weight = sum(b.emission_weight for b in open_bounties)
        
        # Distribute to bounty hotkeys
        bounty_rewards = {}
        for bounty in open_bounties:
            share = bounty.emission_weight / total_weight
            reward = bounty_emissions * share
            
            # Accumulate on bounty hotkey
            bounty.accumulated_emissions += reward
            bounty_rewards[bounty.bounty_hotkey] = reward
        
        bt.logging.info(
            f"Distributed {bounty_emissions:.2f} Alpha to {len(open_bounties)} bounty hotkeys:\n" +
            "\n".join([
                f"  {b.bounty_id}: +{bounty_rewards.get(b.bounty_hotkey, 0):.2f} "
                f"(total: {b.accumulated_emissions:.2f})"
                for b in open_bounties[:5]
            ])
        )
        
        return bounty_rewards
    
    def get_bounty_hotkey_weights(self) -> Dict[str, float]:
        """
        Get weights for all open bounty hotkeys.
        
        Used by validators to set weights for the Open Source mechanism.
        Bounty hotkeys receive emissions which accumulate until the
        bounty is completed.
        """
        open_bounties = [
            b for b in self.bounties.values()
            if b.status == BountyStatus.OPEN
        ]
        
        if not open_bounties:
            return {}
        
        total_weight = sum(b.emission_weight for b in open_bounties)
        
        return {
            bounty.bounty_hotkey: bounty.emission_weight / total_weight
            for bounty in open_bounties
        }
    
    def transfer_bounty_emissions_to_winner(
        self,
        bounty_id: str,
        winner_hotkey: str,
    ) -> float:
        """
        Transfer accumulated emissions from bounty hotkey to winner.
        
        Called when a bounty is completed. The emissions that have been
        accumulating on the bounty's dedicated hotkey are transferred
        to the winner's hotkey.
        
        Returns:
            Amount of Alpha transferred
        """
        if bounty_id not in self.bounties:
            raise ValueError(f"Bounty {bounty_id} not found")
        
        bounty = self.bounties[bounty_id]
        
        if bounty.status != BountyStatus.COMPLETED:
            raise ValueError(f"Bounty {bounty_id} is not completed")
        
        accumulated = bounty.accumulated_emissions
        
        # In production, this would execute an on-chain transfer
        # from bounty.bounty_hotkey to winner_hotkey
        bt.logging.info(
            f"Transferring {accumulated:.2f} Alpha from bounty hotkey "
            f"{bounty.bounty_hotkey[:16]}... to winner {winner_hotkey[:16]}..."
        )
        
        # Reset accumulated (emissions transferred)
        bounty.accumulated_emissions = 0.0
        bounty.paid_amount = accumulated
        
        self._save_data()
        
        return accumulated
    
    def calculate_continuous_rewards(self) -> Dict[str, float]:
        """
        Calculate proportional rewards from continuous contribution pool.
        
        Distribution is proportional to epoch points (not winner takes all!).
        """
        rewards = {}
        
        # Get total epoch points
        total_points = sum(
            p.epoch_points for p in self.miner_profiles.values()
        )
        
        if total_points == 0:
            return rewards
        
        # Distribute proportionally
        for hotkey, profile in self.miner_profiles.items():
            if profile.epoch_points > 0:
                share = profile.epoch_points / total_points
                reward = self.continuous_pool * share
                rewards[hotkey] = reward
        
        return rewards
    
    def finalize_epoch(self, epoch: int):
        """
        Finalize epoch: pay out rewards and reset counters.
        """
        self.current_epoch = epoch
        
        # Calculate and log rewards
        rewards = self.calculate_continuous_rewards()
        
        total_distributed = sum(rewards.values())
        
        bt.logging.info(
            f"Epoch {epoch} Open Source Summary:\n"
            f"  Bounties Completed: {len([b for b in self.bounties.values() if b.status == BountyStatus.COMPLETED])}\n"
            f"  Active Contributors: {len([p for p in self.miner_profiles.values() if p.epoch_points > 0])}\n"
            f"  Continuous Rewards: {total_distributed:.2f} Alpha"
        )
        
        # Reset continuous pool (it's been distributed)
        self.continuous_pool = 0.0
        
        # Reset epoch points
        for profile in self.miner_profiles.values():
            profile.reset_epoch()
        
        # Expire old claims
        self._expire_stale_claims()
        
        self._save_data()
        
        return rewards
    
    def get_miner_weights(
        self,
        miner_uids: List[int],
        metagraph,
    ) -> np.ndarray:
        """
        Calculate weights for open source mechanism.
        
        Combines bounty completions + continuous contributions.
        """
        weights = np.zeros(len(miner_uids), dtype=np.float32)
        
        for idx, uid in enumerate(miner_uids):
            try:
                hotkey = metagraph.hotkeys[uid]
                
                if hotkey not in self.miner_profiles:
                    continue
                
                profile = self.miner_profiles[hotkey]
                
                # Weight = bounty earnings + normalized continuous points
                bounty_weight = profile.total_bounty_earnings / 100.0
                points_weight = profile.total_points / 1000.0
                
                weights[idx] = bounty_weight + points_weight
                
            except (IndexError, KeyError):
                continue
        
        # Normalize
        total = np.sum(weights)
        if total > 0:
            weights = weights / total
        
        return weights
    
    # =========================================================================
    # HELPERS
    # =========================================================================
    
    def _get_or_create_profile(self, miner_hotkey: str) -> MinerContributionProfile:
        """Get or create a miner's contribution profile."""
        if miner_hotkey not in self.miner_profiles:
            self.miner_profiles[miner_hotkey] = MinerContributionProfile(
                miner_hotkey=miner_hotkey
            )
        return self.miner_profiles[miner_hotkey]
    
    def _expire_stale_claims(self):
        """Expire bounty claims that have timed out."""
        now = time.time()
        for bounty in self.bounties.values():
            if bounty.status == BountyStatus.CLAIMED:
                if bounty.claim_expires_at and now > bounty.claim_expires_at:
                    bounty.status = BountyStatus.OPEN
                    bounty.claimed_by = None
                    bounty.claimed_at = None
                    bt.logging.info(f"Bounty {bounty.bounty_id} claim expired, reopened")
    
    def _save_data(self):
        """Save all data to disk."""
        data = {
            "bounties": {k: v.to_dict() for k, v in self.bounties.items()},
            "contributions": {k: v.to_dict() for k, v in self.contributions.items()},
            "profiles": {k: v.to_dict() for k, v in self.miner_profiles.items()},
            "pools": {
                "bounty": self.bounty_pool,
                "continuous": self.continuous_pool,
                "benchmark": self.benchmark_pool,
            },
            "current_epoch": self.current_epoch,
        }
        
        filepath = self.storage_path / "bounty_system.json"
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
    
    def _load_data(self):
        """Load data from disk."""
        filepath = self.storage_path / "bounty_system.json"
        if not filepath.exists():
            return
        
        try:
            with open(filepath, "r") as f:
                data = json.load(f)
            
            self.bounties = {
                k: Bounty.from_dict(v) 
                for k, v in data.get("bounties", {}).items()
            }
            self.contributions = {
                k: Contribution.from_dict(v)
                for k, v in data.get("contributions", {}).items()
            }
            self.miner_profiles = {
                k: MinerContributionProfile.from_dict(v)
                for k, v in data.get("profiles", {}).items()
            }
            
            pools = data.get("pools", {})
            self.bounty_pool = pools.get("bounty", 0.0)
            self.continuous_pool = pools.get("continuous", 0.0)
            self.benchmark_pool = pools.get("benchmark", 0.0)
            
            self.current_epoch = data.get("current_epoch", 0)
            
            bt.logging.info(f"Loaded bounty system data")
            
        except Exception as e:
            bt.logging.warning(f"Could not load bounty data: {e}")


# =============================================================================
# EXAMPLE BOUNTIES
# =============================================================================

def create_example_bounties(manager: BountyManager):
    """Create example bounties for KubeTEE."""
    
    bounties = [
        # Easy bounties - good for newcomers
        {
            "title": "Fix typos in README.md",
            "description": "Find and fix all typos in the main README file.",
            "category": BountyCategory.DOCUMENTATION,
            "difficulty": BountyDifficulty.EASY,
            "acceptance_criteria": [
                "All typos fixed",
                "No new typos introduced",
                "Formatting preserved",
            ],
            "target_repo": "KubeTEE-AI/kubetee-subnet",
        },
        
        # Medium bounties
        {
            "title": "Add unit tests for referral.py",
            "description": "Write comprehensive unit tests for the referral system.",
            "category": BountyCategory.TESTING,
            "difficulty": BountyDifficulty.MEDIUM,
            "acceptance_criteria": [
                "Test coverage > 80%",
                "All edge cases covered",
                "Tests pass in CI",
            ],
            "target_repo": "KubeTEE-AI/kubetee-subnet",
            "automated_tests": ["pytest tests/test_referral.py -v"],
        },
        
        # Hard bounties
        {
            "title": "Implement batch GPU inference optimization",
            "description": "Optimize the inference pipeline to batch multiple requests.",
            "category": BountyCategory.OPTIMIZATION,
            "difficulty": BountyDifficulty.HARD,
            "acceptance_criteria": [
                "Throughput improved by at least 2x",
                "Latency not increased by more than 10%",
                "Memory usage within bounds",
                "All existing tests pass",
            ],
            "target_repo": "KubeTEE-AI/blueprints",
            "automated_tests": ["pytest tests/test_inference.py -v", "python benchmarks/throughput.py"],
        },
        
        # Epic bounties
        {
            "title": "Improve DeepResearch Benchmark score by 10%",
            "description": "Make improvements that increase our DeepResearch Benchmark score by at least 10%.",
            "category": BountyCategory.BENCHMARK,
            "difficulty": BountyDifficulty.EPIC,
            "acceptance_criteria": [
                "DeepResearch score improved by >= 10%",
                "No regression in other benchmarks",
                "Changes are maintainable and documented",
            ],
            "target_repo": "KubeTEE-AI/blueprints",
        },
    ]
    
    for bounty_data in bounties:
        manager.create_bounty(**bounty_data)

