# The MIT License (MIT)
# Copyright © 2023 KubeTEE AI

"""
Open Source Competition Mechanism (Mechanism 1) - 30% of Emissions

Rewards miners for improving the KubeTEE tech stack and NVIDIA Blueprints.
Competition-based: best improvements get highest rewards.

Scoring Criteria:
- Benchmark Scores (50% weight): DeepResearch Bench, RAG evals, etc.
- Code Quality (25% weight): AI-analyzed code quality
- CI/CD Compliance (15% weight): Pipeline status, tests passing
- Security (10% weight): Vulnerability fixes, security improvements

Uses native Bittensor multiple incentive mechanisms:
https://docs.learnbittensor.org/subnets/understanding-multiple-mech-subnets
"""

import time
import json
import numpy as np
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional
from pathlib import Path
import bittensor as bt

from .definitions import MECHANISM_OPEN_SOURCE, MechanismType


# Scoring weights for open source evaluation
BENCHMARK_WEIGHT = 0.50
CODE_QUALITY_WEIGHT = 0.25
CICD_WEIGHT = 0.15
SECURITY_WEIGHT = 0.10


@dataclass
class OpenSourceMetrics:
    """Metrics tracked per miner for open source competition scoring."""
    miner_hotkey: str
    miner_uid: int
    
    # GitHub repository info
    github_repo: Optional[str] = None
    branch: str = "KubeTEE-Staging"
    last_commit_hash: Optional[str] = None
    last_commit_timestamp: float = 0.0
    
    # Benchmark scores (normalized 0-1)
    deep_research_score: float = 0.0
    rag_eval_score: float = 0.0
    arc_agi_score: float = 0.0
    search_eval_score: float = 0.0
    overall_benchmark_score: float = 0.0
    
    # Code quality (0-1)
    code_quality_score: float = 0.0
    documentation_score: float = 0.0
    test_coverage: float = 0.0
    
    # CI/CD status
    cicd_passing: bool = False
    last_pipeline_run: float = 0.0
    pipeline_success_rate: float = 0.0
    
    # Security
    vulnerabilities_fixed: int = 0
    security_score: float = 0.0
    last_security_scan: float = 0.0
    
    # Competition tracking
    ranking: int = 0
    total_contributions: int = 0
    approved_for_production: bool = False
    
    def update_benchmark_scores(
        self,
        deep_research: float = None,
        rag_eval: float = None,
        arc_agi: float = None,
        search_eval: float = None,
    ):
        """Update benchmark scores and recalculate overall."""
        if deep_research is not None:
            self.deep_research_score = min(1.0, max(0.0, deep_research))
        if rag_eval is not None:
            self.rag_eval_score = min(1.0, max(0.0, rag_eval))
        if arc_agi is not None:
            self.arc_agi_score = min(1.0, max(0.0, arc_agi))
        if search_eval is not None:
            self.search_eval_score = min(1.0, max(0.0, search_eval))
        
        # Calculate overall (weighted average of available scores)
        scores = []
        weights = []
        
        if self.deep_research_score > 0:
            scores.append(self.deep_research_score)
            weights.append(0.4)  # Primary benchmark
        if self.rag_eval_score > 0:
            scores.append(self.rag_eval_score)
            weights.append(0.3)
        if self.arc_agi_score > 0:
            scores.append(self.arc_agi_score)
            weights.append(0.2)
        if self.search_eval_score > 0:
            scores.append(self.search_eval_score)
            weights.append(0.1)
        
        if scores:
            total_weight = sum(weights)
            self.overall_benchmark_score = sum(
                s * w for s, w in zip(scores, weights)
            ) / total_weight
    
    def to_dict(self) -> dict:
        return asdict(self)
    
    @classmethod
    def from_dict(cls, data: dict) -> "OpenSourceMetrics":
        return cls(**data)


class OpenSourceScorer:
    """
    Scores miners for the Open Source Competition mechanism.
    
    This scorer evaluates miners based on:
    1. Benchmark performance (DeepResearch, RAG, etc.)
    2. Code quality and documentation
    3. CI/CD pipeline status
    4. Security improvements
    
    Scores are used to set weights for mechanism 1 in the
    native Bittensor multi-mechanism system.
    """
    
    def __init__(self, storage_path: str):
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        # Metrics per miner
        self.metrics: Dict[str, OpenSourceMetrics] = {}
        
        # Load existing data
        self._load_metrics()
        
        bt.logging.info(
            f"OpenSourceScorer initialized: "
            f"emission={MECHANISM_OPEN_SOURCE.emission_percentage}%"
        )
    
    def get_or_create_metrics(self, miner_hotkey: str, miner_uid: int) -> OpenSourceMetrics:
        """Get existing metrics or create new for a miner."""
        if miner_hotkey not in self.metrics:
            self.metrics[miner_hotkey] = OpenSourceMetrics(
                miner_hotkey=miner_hotkey,
                miner_uid=miner_uid
            )
        return self.metrics[miner_hotkey]
    
    def register_repository(
        self,
        miner_hotkey: str,
        miner_uid: int,
        github_repo: str,
        branch: str = "KubeTEE-Staging",
    ):
        """Register a miner's GitHub repository for competition."""
        metrics = self.get_or_create_metrics(miner_hotkey, miner_uid)
        metrics.github_repo = github_repo
        metrics.branch = branch
        
        bt.logging.info(
            f"Registered repo for miner {miner_uid}: {github_repo} ({branch})"
        )
    
    def record_benchmark_results(
        self,
        miner_hotkey: str,
        miner_uid: int,
        deep_research_score: float = None,
        rag_eval_score: float = None,
        arc_agi_score: float = None,
        search_eval_score: float = None,
    ):
        """Record benchmark evaluation results."""
        metrics = self.get_or_create_metrics(miner_hotkey, miner_uid)
        metrics.update_benchmark_scores(
            deep_research=deep_research_score,
            rag_eval=rag_eval_score,
            arc_agi=arc_agi_score,
            search_eval=search_eval_score,
        )
        
        bt.logging.info(
            f"Benchmark results for miner {miner_uid}: "
            f"overall={metrics.overall_benchmark_score:.3f}"
        )
    
    def record_code_quality(
        self,
        miner_hotkey: str,
        miner_uid: int,
        code_quality: float,
        documentation: float = 0.0,
        test_coverage: float = 0.0,
    ):
        """Record code quality assessment results."""
        metrics = self.get_or_create_metrics(miner_hotkey, miner_uid)
        metrics.code_quality_score = min(1.0, max(0.0, code_quality))
        metrics.documentation_score = min(1.0, max(0.0, documentation))
        metrics.test_coverage = min(1.0, max(0.0, test_coverage))
        
        bt.logging.debug(
            f"Code quality for miner {miner_uid}: {code_quality:.2f}"
        )
    
    def record_cicd_status(
        self,
        miner_hotkey: str,
        miner_uid: int,
        passing: bool,
        success_rate: float = 0.0,
    ):
        """Record CI/CD pipeline status."""
        metrics = self.get_or_create_metrics(miner_hotkey, miner_uid)
        metrics.cicd_passing = passing
        metrics.pipeline_success_rate = min(1.0, max(0.0, success_rate))
        metrics.last_pipeline_run = time.time()
    
    def record_security_scan(
        self,
        miner_hotkey: str,
        miner_uid: int,
        vulnerabilities_found: int,
        vulnerabilities_fixed: int,
        security_score: float,
    ):
        """Record security scan results."""
        metrics = self.get_or_create_metrics(miner_hotkey, miner_uid)
        metrics.vulnerabilities_fixed += vulnerabilities_fixed
        metrics.security_score = min(1.0, max(0.0, security_score))
        metrics.last_security_scan = time.time()
    
    def calculate_score(self, miner_hotkey: str) -> float:
        """
        Calculate the open source competition score for a miner.
        
        Score components:
        - Benchmark scores: 50% weight
        - Code quality: 25% weight
        - CI/CD compliance: 15% weight
        - Security: 10% weight
        
        Returns:
            Score between 0.0 and 1.0
        """
        if miner_hotkey not in self.metrics:
            return 0.0
        
        metrics = self.metrics[miner_hotkey]
        
        # Benchmark score (already normalized 0-1)
        benchmark_score = metrics.overall_benchmark_score
        
        # Code quality score
        code_quality = (
            metrics.code_quality_score * 0.5 +
            metrics.documentation_score * 0.3 +
            metrics.test_coverage * 0.2
        )
        
        # CI/CD score
        cicd_score = 0.0
        if metrics.cicd_passing:
            cicd_score = 0.5 + (metrics.pipeline_success_rate * 0.5)
        
        # Security score
        security_score = metrics.security_score
        
        # Combined weighted score
        total_score = (
            BENCHMARK_WEIGHT * benchmark_score +
            CODE_QUALITY_WEIGHT * code_quality +
            CICD_WEIGHT * cicd_score +
            SECURITY_WEIGHT * security_score
        )
        
        return min(1.0, max(0.0, total_score))
    
    def calculate_weights(
        self,
        miner_uids: List[int],
        metagraph,
    ) -> np.ndarray:
        """
        Calculate weights for all miners for the Open Source mechanism.
        
        These weights are set via subtensor.set_weights with mechanism_id=1.
        
        Args:
            miner_uids: List of miner UIDs
            metagraph: Network metagraph
            
        Returns:
            Normalized weight array for mechanism 1
        """
        weights = np.zeros(len(miner_uids), dtype=np.float32)
        
        for idx, uid in enumerate(miner_uids):
            try:
                hotkey = metagraph.hotkeys[uid]
                weights[idx] = self.calculate_score(hotkey)
            except (IndexError, KeyError):
                continue
        
        # Normalize weights
        total = np.sum(weights)
        if total > 0:
            weights = weights / total
        
        return weights
    
    def get_leaderboard(self, top_n: int = 10) -> List[Dict]:
        """Get the competition leaderboard."""
        ranked = sorted(
            [
                {
                    "rank": 0,
                    "miner_uid": m.miner_uid,
                    "hotkey": m.miner_hotkey[:16] + "...",
                    "benchmark_score": m.overall_benchmark_score,
                    "code_quality": m.code_quality_score,
                    "total_score": self.calculate_score(m.miner_hotkey),
                    "github_repo": m.github_repo,
                    "approved_for_production": m.approved_for_production,
                }
                for m in self.metrics.values()
            ],
            key=lambda x: x["total_score"],
            reverse=True
        )
        
        for i, entry in enumerate(ranked):
            entry["rank"] = i + 1
        
        return ranked[:top_n]
    
    def approve_for_production(self, miner_hotkey: str):
        """Mark a miner's contribution as approved for production."""
        if miner_hotkey in self.metrics:
            self.metrics[miner_hotkey].approved_for_production = True
            bt.logging.info(f"Miner {miner_hotkey[:16]}... approved for production")
    
    def _save_metrics(self):
        """Save metrics to disk."""
        data = {
            hotkey: metrics.to_dict()
            for hotkey, metrics in self.metrics.items()
        }
        
        filepath = self.storage_path / "open_source_metrics.json"
        with open(filepath, "w") as f:
            json.dump(data, f, indent=2)
    
    def _load_metrics(self):
        """Load metrics from disk."""
        filepath = self.storage_path / "open_source_metrics.json"
        if filepath.exists():
            try:
                with open(filepath, "r") as f:
                    data = json.load(f)
                
                for hotkey, metrics_data in data.items():
                    self.metrics[hotkey] = OpenSourceMetrics.from_dict(metrics_data)
                
                bt.logging.info(f"Loaded open source metrics for {len(self.metrics)} miners")
            except Exception as e:
                bt.logging.warning(f"Could not load open source metrics: {e}")
    
    def finalize_epoch(self, epoch: int):
        """Finalize epoch and save data."""
        leaderboard = self.get_leaderboard(5)
        
        bt.logging.info(
            f"Open Source Competition Epoch {epoch} Summary:\n"
            f"  Active Competitors: {len(self.metrics)}\n"
            f"  Top 3: {[e['hotkey'] for e in leaderboard[:3]]}"
        )
        self._save_metrics()

