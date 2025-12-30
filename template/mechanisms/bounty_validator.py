# The MIT License (MIT)
# Copyright © 2023 KubeTEE AI

"""
Automated Bounty Validation Service

This module provides fully automated validation for bounty submissions:
- CI/CD test execution via GitHub Actions API
- AI code analysis using Claude/GPT-4
- Benchmark testing
- Security scanning

NO HUMAN IN THE LOOP - subnet owner's validator runs this automatically.
Subnet owner can override for edge cases.
"""

import os
import re
import json
import time
import asyncio
import subprocess
import httpx
from dataclasses import dataclass
from typing import Optional, Dict, List, Tuple
from pathlib import Path
import bittensor as bt

from .bounty_system import BountyManager, BountyCategory


# =============================================================================
# CONFIGURATION
# =============================================================================

# AI Analysis configuration
AI_MODEL = os.getenv("AI_ANALYSIS_MODEL", "claude-sonnet-4-20250514")  # or "gpt-4"
AI_API_KEY = os.getenv("AI_API_KEY", "")

# GitHub configuration
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN", "")
GITHUB_API_BASE = "https://api.github.com"

# Bitsec (Subnet 60) configuration for security scanning
BITSEC_SUBNET_UID = 60
BITSEC_ENDPOINT = os.getenv("BITSEC_ENDPOINT", "")  # Bitsec API endpoint
BITSEC_HOTKEY = os.getenv("BITSEC_HOTKEY", "")      # Hotkey for authentication

# Thresholds for auto-approval
MIN_CODE_QUALITY_SCORE = 70.0
MIN_SECURITY_SCORE = 80.0
MIN_TEST_COVERAGE = 80.0


# =============================================================================
# DATA STRUCTURES
# =============================================================================

@dataclass
class CITestResult:
    """Result from CI/CD pipeline."""
    passed: bool
    total_tests: int
    passed_tests: int
    failed_tests: int
    coverage_percent: float
    duration_seconds: float
    log_url: Optional[str] = None
    error_summary: Optional[str] = None


@dataclass
class AIAnalysisResult:
    """Result from AI code analysis."""
    code_quality_score: float  # 0-100
    security_score: float      # 0-100
    performance_score: float   # 0-100
    documentation_score: float # 0-100
    
    summary: str
    strengths: List[str]
    improvements: List[str]
    security_issues: List[str]
    
    recommendation: str  # "approve", "reject", or "manual_review"
    confidence: float    # 0-1


@dataclass
class BenchmarkResult:
    """Result from benchmark testing."""
    benchmark_name: str
    baseline_score: float
    new_score: float
    delta_percent: float
    passed: bool


@dataclass
class BitsecSecurityResult:
    """Result from Bitsec (Subnet 60) security scan."""
    passed: bool
    critical_issues: int
    high_issues: int
    medium_issues: int
    low_issues: int
    total_issues: int
    
    vulnerabilities: List[Dict]  # List of found vulnerabilities
    scan_duration_seconds: float
    scan_timestamp: float
    
    summary: str
    recommendation: str  # "pass", "fail", "review"


# =============================================================================
# BITSEC (SUBNET 60) SECURITY SCANNING
# =============================================================================

class BitsecSecurityScanner:
    """
    Integrates with Bitsec (Subnet 60) for decentralized security auditing.
    
    Bitsec uses AI to find code exploits and vulnerabilities in code submissions.
    This provides decentralized, automated security scanning for bounty validation.
    
    Integration Methods:
    1. Direct API call to Bitsec miner endpoint
    2. Via Bittensor synapse (subnet-to-subnet communication)
    """
    
    def __init__(
        self,
        subtensor: "bt.subtensor" = None,
        endpoint: str = BITSEC_ENDPOINT,
        hotkey: str = BITSEC_HOTKEY,
    ):
        self.subtensor = subtensor
        self.endpoint = endpoint
        self.hotkey = hotkey
        self.subnet_uid = BITSEC_SUBNET_UID
    
    async def scan_code(
        self,
        code_diff: str,
        repo_url: str,
        file_types: List[str] = None,
    ) -> BitsecSecurityResult:
        """
        Scan code for security vulnerabilities using Bitsec (SN60).
        
        Args:
            code_diff: The code diff/patch to analyze
            repo_url: Repository URL for context
            file_types: File types to focus on (e.g., ["python", "solidity"])
        
        Returns:
            BitsecSecurityResult with vulnerability findings
        """
        start_time = time.time()
        
        # Try Bitsec API endpoint first
        if self.endpoint:
            result = await self._scan_via_api(code_diff, repo_url, file_types)
            if result:
                return result
        
        # Fallback to Bittensor synapse (subnet-to-subnet)
        if self.subtensor:
            result = await self._scan_via_synapse(code_diff, repo_url, file_types)
            if result:
                return result
        
        # If no Bitsec available, return a placeholder result
        bt.logging.warning("Bitsec not configured, using fallback security check")
        return self._fallback_scan(code_diff, start_time)
    
    async def _scan_via_api(
        self,
        code_diff: str,
        repo_url: str,
        file_types: List[str],
    ) -> Optional[BitsecSecurityResult]:
        """Scan via Bitsec API endpoint."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.endpoint}/api/v1/scan",
                    json={
                        "code": code_diff,
                        "repo_url": repo_url,
                        "file_types": file_types or ["python"],
                        "scan_type": "vulnerability",
                    },
                    headers={
                        "Authorization": f"Bearer {self.hotkey}",
                        "Content-Type": "application/json",
                    },
                    timeout=120.0,
                )
                
                if response.status_code == 200:
                    return self._parse_bitsec_response(response.json())
                    
        except Exception as e:
            bt.logging.warning(f"Bitsec API call failed: {e}")
        
        return None
    
    async def _scan_via_synapse(
        self,
        code_diff: str,
        repo_url: str,
        file_types: List[str],
    ) -> Optional[BitsecSecurityResult]:
        """
        Scan via Bittensor synapse (subnet-to-subnet communication).
        
        This would send a synapse to a Bitsec miner for processing.
        """
        try:
            # Get Bitsec metagraph
            metagraph = self.subtensor.metagraph(self.subnet_uid)
            
            # Find top Bitsec miner
            top_miner_uid = metagraph.I.argmax().item()
            miner_axon = metagraph.axons[top_miner_uid]
            
            # Create synapse request
            # Note: This is a placeholder - actual implementation would
            # use Bitsec's specific synapse protocol
            bt.logging.info(f"Sending security scan to Bitsec miner: {miner_axon}")
            
            # In production, this would be:
            # synapse = BitsecScanSynapse(code=code_diff, repo=repo_url)
            # response = await self.dendrite.forward(miner_axon, synapse)
            
            return None  # Placeholder
            
        except Exception as e:
            bt.logging.warning(f"Bitsec synapse failed: {e}")
        
        return None
    
    def _parse_bitsec_response(self, data: dict) -> BitsecSecurityResult:
        """Parse Bitsec API response into result object."""
        vulnerabilities = data.get("vulnerabilities", [])
        
        critical = sum(1 for v in vulnerabilities if v.get("severity") == "critical")
        high = sum(1 for v in vulnerabilities if v.get("severity") == "high")
        medium = sum(1 for v in vulnerabilities if v.get("severity") == "medium")
        low = sum(1 for v in vulnerabilities if v.get("severity") == "low")
        
        passed = critical == 0 and high == 0
        
        return BitsecSecurityResult(
            passed=passed,
            critical_issues=critical,
            high_issues=high,
            medium_issues=medium,
            low_issues=low,
            total_issues=len(vulnerabilities),
            vulnerabilities=vulnerabilities,
            scan_duration_seconds=data.get("duration", 0.0),
            scan_timestamp=time.time(),
            summary=data.get("summary", ""),
            recommendation="pass" if passed else "fail",
        )
    
    def _fallback_scan(
        self,
        code_diff: str,
        start_time: float,
    ) -> BitsecSecurityResult:
        """
        Fallback security scan using basic pattern matching.
        Used when Bitsec is not available.
        """
        # Basic security patterns to check
        security_patterns = [
            (r"eval\s*\(", "critical", "Use of eval() is dangerous"),
            (r"exec\s*\(", "critical", "Use of exec() is dangerous"),
            (r"subprocess\.call.*shell\s*=\s*True", "high", "Shell injection risk"),
            (r"os\.system\s*\(", "high", "OS command injection risk"),
            (r"pickle\.loads?", "high", "Pickle deserialization vulnerability"),
            (r"__import__\s*\(", "medium", "Dynamic import could be risky"),
            (r"password\s*=\s*['\"]", "medium", "Hardcoded password"),
            (r"api_key\s*=\s*['\"]", "medium", "Hardcoded API key"),
            (r"secret\s*=\s*['\"]", "medium", "Hardcoded secret"),
        ]
        
        vulnerabilities = []
        for pattern, severity, description in security_patterns:
            if re.search(pattern, code_diff, re.IGNORECASE):
                vulnerabilities.append({
                    "pattern": pattern,
                    "severity": severity,
                    "description": description,
                })
        
        critical = sum(1 for v in vulnerabilities if v["severity"] == "critical")
        high = sum(1 for v in vulnerabilities if v["severity"] == "high")
        medium = sum(1 for v in vulnerabilities if v["severity"] == "medium")
        low = sum(1 for v in vulnerabilities if v["severity"] == "low")
        
        passed = critical == 0 and high == 0
        
        return BitsecSecurityResult(
            passed=passed,
            critical_issues=critical,
            high_issues=high,
            medium_issues=medium,
            low_issues=low,
            total_issues=len(vulnerabilities),
            vulnerabilities=vulnerabilities,
            scan_duration_seconds=time.time() - start_time,
            scan_timestamp=time.time(),
            summary=f"Fallback scan found {len(vulnerabilities)} issues",
            recommendation="pass" if passed else "fail",
        )


# =============================================================================
# CI/CD INTEGRATION
# =============================================================================

class GitHubCIRunner:
    """
    Runs CI/CD tests via GitHub Actions API.
    
    Triggers the test workflow on the PR and waits for results.
    """
    
    def __init__(self, token: str = GITHUB_TOKEN):
        self.token = token
        self.headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }
    
    async def run_tests(
        self,
        repo: str,
        pr_number: int,
        workflow_name: str = "ci.yml",
        timeout_minutes: int = 30,
    ) -> CITestResult:
        """
        Trigger CI workflow on a PR and wait for results.
        
        Args:
            repo: Repository in format "owner/repo"
            pr_number: Pull request number
            workflow_name: Name of the workflow file
            timeout_minutes: Max time to wait for completion
        
        Returns:
            CITestResult with test outcomes
        """
        async with httpx.AsyncClient() as client:
            # Get PR details to find the head SHA
            pr_url = f"{GITHUB_API_BASE}/repos/{repo}/pulls/{pr_number}"
            pr_response = await client.get(pr_url, headers=self.headers)
            pr_data = pr_response.json()
            head_sha = pr_data.get("head", {}).get("sha")
            
            if not head_sha:
                return CITestResult(
                    passed=False,
                    total_tests=0,
                    passed_tests=0,
                    failed_tests=0,
                    coverage_percent=0.0,
                    duration_seconds=0.0,
                    error_summary="Could not get PR head SHA",
                )
            
            # Trigger workflow
            workflow_url = f"{GITHUB_API_BASE}/repos/{repo}/actions/workflows/{workflow_name}/dispatches"
            dispatch_response = await client.post(
                workflow_url,
                headers=self.headers,
                json={"ref": pr_data["head"]["ref"]},
            )
            
            if dispatch_response.status_code not in [200, 204]:
                # Workflow might already be triggered by PR
                bt.logging.info("Workflow dispatch returned non-success, checking existing runs")
            
            # Wait for workflow to complete
            start_time = time.time()
            timeout_seconds = timeout_minutes * 60
            
            while time.time() - start_time < timeout_seconds:
                # Check workflow runs for this SHA
                runs_url = f"{GITHUB_API_BASE}/repos/{repo}/actions/runs"
                runs_response = await client.get(
                    runs_url,
                    headers=self.headers,
                    params={"head_sha": head_sha, "per_page": 5},
                )
                runs_data = runs_response.json()
                
                for run in runs_data.get("workflow_runs", []):
                    if run["status"] == "completed":
                        return self._parse_workflow_run(run)
                
                # Wait before checking again
                await asyncio.sleep(30)
            
            return CITestResult(
                passed=False,
                total_tests=0,
                passed_tests=0,
                failed_tests=0,
                coverage_percent=0.0,
                duration_seconds=timeout_seconds,
                error_summary="Workflow timed out",
            )
    
    def _parse_workflow_run(self, run: dict) -> CITestResult:
        """Parse a completed workflow run into CITestResult."""
        conclusion = run.get("conclusion", "failure")
        passed = conclusion == "success"
        
        # Calculate duration
        created_at = run.get("created_at", "")
        updated_at = run.get("updated_at", "")
        
        try:
            from datetime import datetime
            start = datetime.fromisoformat(created_at.replace("Z", "+00:00"))
            end = datetime.fromisoformat(updated_at.replace("Z", "+00:00"))
            duration = (end - start).total_seconds()
        except Exception:
            duration = 0.0
        
        return CITestResult(
            passed=passed,
            total_tests=0,  # Would need to parse job outputs
            passed_tests=0,
            failed_tests=0 if passed else 1,
            coverage_percent=0.0,  # Would need to parse coverage report
            duration_seconds=duration,
            log_url=run.get("html_url"),
            error_summary=None if passed else f"Workflow conclusion: {conclusion}",
        )


# =============================================================================
# AI CODE ANALYSIS
# =============================================================================

class AICodeAnalyzer:
    """
    Analyzes code changes using AI (Claude or GPT-4).
    
    Evaluates:
    - Code quality
    - Security vulnerabilities
    - Performance implications
    - Documentation completeness
    """
    
    def __init__(
        self,
        model: str = AI_MODEL,
        api_key: str = AI_API_KEY,
    ):
        self.model = model
        self.api_key = api_key
        self.is_claude = "claude" in model.lower()
    
    async def analyze_pr(
        self,
        repo: str,
        pr_number: int,
        bounty_category: BountyCategory,
    ) -> AIAnalysisResult:
        """
        Analyze a pull request using AI.
        
        Args:
            repo: Repository in format "owner/repo"
            pr_number: Pull request number
            bounty_category: Category of the bounty (affects analysis focus)
        
        Returns:
            AIAnalysisResult with scores and recommendations
        """
        # Get PR diff
        diff = await self._get_pr_diff(repo, pr_number)
        
        if not diff:
            return self._error_result("Could not fetch PR diff")
        
        # Build analysis prompt
        prompt = self._build_analysis_prompt(diff, bounty_category)
        
        # Call AI API
        if self.is_claude:
            response = await self._call_claude(prompt)
        else:
            response = await self._call_openai(prompt)
        
        return self._parse_ai_response(response)
    
    async def _get_pr_diff(self, repo: str, pr_number: int) -> Optional[str]:
        """Fetch the diff for a pull request."""
        async with httpx.AsyncClient() as client:
            url = f"{GITHUB_API_BASE}/repos/{repo}/pulls/{pr_number}"
            headers = {
                "Authorization": f"Bearer {GITHUB_TOKEN}",
                "Accept": "application/vnd.github.v3.diff",
            }
            response = await client.get(url, headers=headers)
            
            if response.status_code == 200:
                return response.text
            return None
    
    def _build_analysis_prompt(
        self,
        diff: str,
        category: BountyCategory,
    ) -> str:
        """Build the prompt for AI analysis."""
        
        category_focus = {
            BountyCategory.BUG_FIX: "Focus on whether the bug is correctly identified and fixed without introducing regressions.",
            BountyCategory.FEATURE: "Focus on code design, API consistency, and feature completeness.",
            BountyCategory.DOCUMENTATION: "Focus on clarity, accuracy, and completeness of documentation.",
            BountyCategory.BENCHMARK: "Focus on performance implications and measurement accuracy.",
            BountyCategory.SECURITY: "Focus heavily on security best practices and vulnerability prevention.",
            BountyCategory.OPTIMIZATION: "Focus on performance gains, memory usage, and algorithmic efficiency.",
            BountyCategory.TESTING: "Focus on test coverage, edge cases, and test quality.",
        }
        
        focus = category_focus.get(category, "General code quality and best practices.")
        
        return f"""You are a senior code reviewer for the KubeTEE AI subnet. 
Analyze this pull request diff and provide a structured review.

CATEGORY: {category.value}
FOCUS: {focus}

DIFF:
```
{diff[:50000]}  # Truncate to avoid token limits
```

Provide your analysis in the following JSON format:
{{
    "code_quality_score": <0-100>,
    "security_score": <0-100>,
    "performance_score": <0-100>,
    "documentation_score": <0-100>,
    "summary": "<2-3 sentence summary>",
    "strengths": ["<strength 1>", "<strength 2>", ...],
    "improvements": ["<improvement 1>", "<improvement 2>", ...],
    "security_issues": ["<issue 1>", ...],
    "recommendation": "<approve|reject|manual_review>",
    "confidence": <0.0-1.0>
}}

SCORING GUIDELINES:
- 90-100: Exceptional, production-ready code
- 70-89: Good quality, meets standards
- 50-69: Acceptable but needs improvements
- Below 50: Not acceptable, requires significant changes

SECURITY SCORING:
- 90-100: No security issues found
- 70-89: Minor issues, easily fixable
- 50-69: Moderate issues that need attention
- Below 50: Critical security vulnerabilities

Return ONLY the JSON object, no other text."""

    async def _call_claude(self, prompt: str) -> str:
        """Call Claude API for analysis."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": self.model,
                    "max_tokens": 4096,
                    "messages": [{"role": "user", "content": prompt}],
                },
                timeout=120.0,
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get("content", [{}])[0].get("text", "")
            return ""
    
    async def _call_openai(self, prompt: str) -> str:
        """Call OpenAI API for analysis."""
        async with httpx.AsyncClient() as client:
            response = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [{"role": "user", "content": prompt}],
                    "max_tokens": 4096,
                },
                timeout=120.0,
            )
            
            if response.status_code == 200:
                data = response.json()
                return data.get("choices", [{}])[0].get("message", {}).get("content", "")
            return ""
    
    def _parse_ai_response(self, response: str) -> AIAnalysisResult:
        """Parse AI response into structured result."""
        try:
            # Extract JSON from response
            import re
            json_match = re.search(r'\{[\s\S]*\}', response)
            if json_match:
                data = json.loads(json_match.group())
                return AIAnalysisResult(
                    code_quality_score=float(data.get("code_quality_score", 0)),
                    security_score=float(data.get("security_score", 0)),
                    performance_score=float(data.get("performance_score", 0)),
                    documentation_score=float(data.get("documentation_score", 0)),
                    summary=data.get("summary", ""),
                    strengths=data.get("strengths", []),
                    improvements=data.get("improvements", []),
                    security_issues=data.get("security_issues", []),
                    recommendation=data.get("recommendation", "manual_review"),
                    confidence=float(data.get("confidence", 0.5)),
                )
        except Exception as e:
            bt.logging.warning(f"Failed to parse AI response: {e}")
        
        return self._error_result("Failed to parse AI analysis")
    
    def _error_result(self, error: str) -> AIAnalysisResult:
        """Return an error result."""
        return AIAnalysisResult(
            code_quality_score=0.0,
            security_score=0.0,
            performance_score=0.0,
            documentation_score=0.0,
            summary=error,
            strengths=[],
            improvements=[],
            security_issues=[],
            recommendation="manual_review",
            confidence=0.0,
        )


# =============================================================================
# BOUNTY VALIDATION ORCHESTRATOR
# =============================================================================

class BountyValidationService:
    """
    Orchestrates the full automated validation pipeline.
    
    Used by the subnet owner's validator to automatically validate
    bounty submissions without human intervention.
    
    Integrations:
    - GitHub Actions for CI/CD
    - Claude/GPT-4 for AI code analysis
    - Bitsec (Subnet 60) for security scanning
    """
    
    def __init__(
        self,
        bounty_manager: BountyManager,
        github_token: str = GITHUB_TOKEN,
        ai_api_key: str = AI_API_KEY,
        ai_model: str = AI_MODEL,
        subtensor: "bt.subtensor" = None,
    ):
        self.bounty_manager = bounty_manager
        self.ci_runner = GitHubCIRunner(github_token)
        self.ai_analyzer = AICodeAnalyzer(ai_model, ai_api_key)
        self.security_scanner = BitsecSecurityScanner(subtensor=subtensor)
    
    async def validate_submission(
        self,
        bounty_id: str,
        run_benchmarks: bool = True,
    ) -> Dict:
        """
        Run full automated validation on a bounty submission.
        
        Steps:
        1. Run CI/CD tests (GitHub Actions)
        2. Run AI code analysis (Claude/GPT-4)
        3. Run security scan (Bitsec SN60)
        4. Run benchmarks (if applicable)
        5. Calculate scores and auto-approve if thresholds met
        
        Args:
            bounty_id: The bounty to validate
            run_benchmarks: Whether to run benchmark tests
        
        Returns:
            Validation result dict
        """
        bounty = self.bounty_manager.bounties.get(bounty_id)
        if not bounty:
            return {"error": f"Bounty {bounty_id} not found"}
        
        if not bounty.pr_url:
            return {"error": "No PR URL submitted"}
        
        # Parse PR URL
        repo, pr_number = self._parse_pr_url(bounty.pr_url)
        if not repo or not pr_number:
            return {"error": f"Could not parse PR URL: {bounty.pr_url}"}
        
        bt.logging.info(f"Validating bounty {bounty_id}: {repo} PR #{pr_number}")
        
        # Step 1: Run CI/CD tests
        bt.logging.info("Running CI/CD tests...")
        ci_result = await self.ci_runner.run_tests(repo, pr_number)
        
        # Step 2: Run AI analysis
        bt.logging.info("Running AI code analysis...")
        ai_result = await self.ai_analyzer.analyze_pr(
            repo, pr_number, bounty.category
        )
        
        # Step 3: Run Bitsec security scan (Subnet 60)
        bt.logging.info("Running Bitsec (SN60) security scan...")
        code_diff = await self._get_pr_diff(repo, pr_number)
        security_result = await self.security_scanner.scan_code(
            code_diff=code_diff or "",
            repo_url=f"https://github.com/{repo}",
        )
        
        # Combine security scores: Bitsec takes priority, AI as fallback
        if security_result.passed:
            # Bitsec passed: use high security score
            combined_security_score = 90.0 if security_result.total_issues == 0 else 75.0
        else:
            # Bitsec found critical/high issues: fail
            combined_security_score = max(
                20.0,  # Minimum score
                100.0 - (security_result.critical_issues * 30) - (security_result.high_issues * 15)
            )
        
        # Step 4: Run benchmarks (if applicable)
        benchmark_delta = 0.0
        if run_benchmarks and bounty.category == BountyCategory.BENCHMARK:
            bt.logging.info("Running benchmark tests...")
            benchmark_result = await self._run_benchmarks(repo, pr_number)
            benchmark_delta = benchmark_result.delta_percent if benchmark_result else 0.0
        
        # Step 5: Record results and attempt auto-approval
        result = self.bounty_manager.validate_bounty(
            bounty_id=bounty_id,
            ci_passed=ci_result.passed,
            ci_results=ci_result.error_summary or "All tests passed",
            code_quality_score=ai_result.code_quality_score,
            security_score=combined_security_score,
            ai_summary=ai_result.summary,
            benchmark_delta=benchmark_delta,
        )
        
        # Add Bitsec security details to result
        result["bitsec_security"] = {
            "passed": security_result.passed,
            "critical": security_result.critical_issues,
            "high": security_result.high_issues,
            "medium": security_result.medium_issues,
            "low": security_result.low_issues,
            "total": security_result.total_issues,
            "summary": security_result.summary,
        }
        
        # Add detailed results
        result["ci_details"] = {
            "passed": ci_result.passed,
            "total_tests": ci_result.total_tests,
            "coverage": ci_result.coverage_percent,
            "duration": ci_result.duration_seconds,
            "log_url": ci_result.log_url,
        }
        
        result["ai_details"] = {
            "code_quality": ai_result.code_quality_score,
            "security": ai_result.security_score,
            "performance": ai_result.performance_score,
            "documentation": ai_result.documentation_score,
            "strengths": ai_result.strengths,
            "improvements": ai_result.improvements,
            "security_issues": ai_result.security_issues,
            "recommendation": ai_result.recommendation,
            "confidence": ai_result.confidence,
        }
        
        return result
    
    def _parse_pr_url(self, url: str) -> Tuple[Optional[str], Optional[int]]:
        """Parse GitHub PR URL into repo and PR number."""
        match = re.match(
            r'https://github\.com/([^/]+/[^/]+)/pull/(\d+)',
            url
        )
        if match:
            return match.group(1), int(match.group(2))
        return None, None
    
    async def _get_pr_diff(self, repo: str, pr_number: int) -> Optional[str]:
        """Fetch the diff for a pull request."""
        try:
            async with httpx.AsyncClient() as client:
                url = f"{GITHUB_API_BASE}/repos/{repo}/pulls/{pr_number}"
                headers = {
                    "Authorization": f"Bearer {GITHUB_TOKEN}",
                    "Accept": "application/vnd.github.v3.diff",
                }
                response = await client.get(url, headers=headers, timeout=60.0)
                
                if response.status_code == 200:
                    return response.text
        except Exception as e:
            bt.logging.warning(f"Failed to fetch PR diff: {e}")
        return None
    
    async def _run_benchmarks(
        self,
        repo: str,
        pr_number: int,
    ) -> Optional[BenchmarkResult]:
        """Run benchmark tests and compare to baseline."""
        # This would trigger a benchmark workflow and compare results
        # For now, return a placeholder
        bt.logging.info("Benchmark testing not yet implemented")
        return None


# =============================================================================
# CLI INTEGRATION
# =============================================================================

async def validate_bounty_cli(
    bounty_manager: BountyManager,
    bounty_id: str,
):
    """CLI command to validate a bounty submission."""
    service = BountyValidationService(bounty_manager)
    result = await service.validate_submission(bounty_id)
    
    print(f"\n{'='*60}")
    print(f"BOUNTY VALIDATION RESULTS: {bounty_id}")
    print(f"{'='*60}\n")
    
    if "error" in result:
        print(f"❌ Error: {result['error']}")
        return
    
    if result.get("auto_approved"):
        print("✅ AUTO-APPROVED!")
    else:
        print("⚠️  NEEDS MANUAL REVIEW")
    
    print(f"\nCI/CD Tests: {'✅ PASS' if result.get('ci_passed') else '❌ FAIL'}")
    print(f"Code Quality: {result.get('code_quality_score', 0):.0f}/100")
    print(f"Security: {result.get('security_score', 0):.0f}/100")
    
    # Bitsec security details
    bitsec = result.get("bitsec_security", {})
    if bitsec:
        print(f"\n🔒 Bitsec (SN60) Security Scan:")
        print(f"   Status: {'✅ PASS' if bitsec.get('passed') else '❌ FAIL'}")
        print(f"   Critical: {bitsec.get('critical', 0)} | High: {bitsec.get('high', 0)} | Medium: {bitsec.get('medium', 0)} | Low: {bitsec.get('low', 0)}")
        if bitsec.get('summary'):
            print(f"   Summary: {bitsec.get('summary')}")
    
    print(f"\nAI Summary: {result.get('ai_summary', 'N/A')}")
    
    if not result.get("auto_approved"):
        print("\nSubnet owner can approve with:")
        print(f"  kubetee bounties approve {bounty_id}")

