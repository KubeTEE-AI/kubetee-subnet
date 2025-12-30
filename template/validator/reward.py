# The MIT License (MIT)
# Copyright © 2023 Yuma Rao
# Copyright © 2023 KubeTEE AI

# Permission is hereby granted, free of charge, to any person obtaining a copy of this software and associated
# documentation files (the "Software"), to deal in the Software without restriction, including without limitation
# the rights to use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of the Software,
# and to permit persons to whom the Software is furnished to do so, subject to the following conditions:

# The above copyright notice and this permission notice shall be included in all copies or substantial portions of
# the Software.

# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO
# THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL
# THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.

"""
KubeTEE AI Reward System

This module implements the comprehensive reward system for the KubeTEE AI subnet,
combining multiple reward signals:

1. Performance Rewards (Task Completion)
   - Based on successful task completion
   - Quality of responses

2. Revenue-Based Rewards (50% Miner Share)
   - Proportional to revenue generated from user services
   - Incentivizes miners to provide high-quality infrastructure
   - Miners receive 50% of all revenue generated

3. Infrastructure Quality Rewards
   - Uptime and reliability
   - Response latency
   - Resource availability

Reward Weighting:
- Revenue-based rewards: 50% weight (incentivize service provision)
- Performance rewards: 30% weight (incentivize quality)
- Infrastructure rewards: 20% weight (incentivize reliability)
"""

import numpy as np
from typing import List, Optional, Dict, Any
import bittensor as bt
from template.protocol import ServiceRequest, InfrastructureStatus


# Reward weighting configuration
REVENUE_REWARD_WEIGHT = 0.50  # 50% weight for revenue-based rewards
PERFORMANCE_REWARD_WEIGHT = 0.30  # 30% weight for performance
INFRASTRUCTURE_REWARD_WEIGHT = 0.20  # 20% weight for infrastructure quality

# Latency thresholds (milliseconds)
EXCELLENT_LATENCY_MS = 100
GOOD_LATENCY_MS = 500
ACCEPTABLE_LATENCY_MS = 2000


def reward(query: int, response: int) -> float:
    """
    Reward the miner response to the dummy request (legacy compatibility).

    Returns:
    - float: The reward value for the miner.
    """
    bt.logging.info(
        f"In rewards, query val: {query}, response val: {response}, "
        f"rewards val: {1.0 if response == query * 2 else 0}"
    )
    return 1.0 if response == query * 2 else 0


def get_rewards(
    self,
    query: int,
    responses: List[float],
) -> np.ndarray:
    """
    Returns an array of rewards for the given query and responses (legacy).

    Args:
    - query (int): The query sent to the miner.
    - responses (List[float]): A list of responses from the miner.

    Returns:
    - np.ndarray: An array of rewards for the given query and responses.
    """
    return np.array([reward(query, response) for response in responses])


def calculate_service_reward(response: ServiceRequest) -> float:
    """
    Calculate reward for a service request based on quality metrics.
    
    Args:
        response: The service request response from miner
        
    Returns:
        Reward score between 0 and 1
    """
    if not response.success:
        return 0.0
    
    base_reward = 1.0
    
    # Latency scoring (0.0 - 0.3 bonus)
    latency = response.calculate_latency()
    if latency <= EXCELLENT_LATENCY_MS:
        latency_bonus = 0.3
    elif latency <= GOOD_LATENCY_MS:
        latency_bonus = 0.2
    elif latency <= ACCEPTABLE_LATENCY_MS:
        latency_bonus = 0.1
    else:
        latency_bonus = 0.0
    
    # Token efficiency scoring (0.0 - 0.2 bonus)
    total_tokens = response.get_total_tokens()
    if total_tokens > 0:
        # Reward reasonable token usage
        if response.tokens_output >= response.tokens_input * 0.5:
            token_bonus = 0.2
        else:
            token_bonus = 0.1
    else:
        token_bonus = 0.0
    
    return min(1.0, base_reward + latency_bonus + token_bonus)


def calculate_infrastructure_reward(status: InfrastructureStatus) -> float:
    """
    Calculate reward based on infrastructure status.
    
    Args:
        status: Infrastructure status from miner
        
    Returns:
        Reward score between 0 and 1
    """
    reward = 0.0
    
    # Uptime scoring (0.0 - 0.4)
    if status.uptime_percentage >= 99.9:
        reward += 0.4
    elif status.uptime_percentage >= 99.0:
        reward += 0.3
    elif status.uptime_percentage >= 95.0:
        reward += 0.2
    elif status.uptime_percentage >= 90.0:
        reward += 0.1
    
    # TEE enabled bonus (0.0 - 0.2)
    if status.tee_enabled:
        reward += 0.2
    
    # FIPS compliance bonus (0.0 - 0.1)
    if status.fips_enabled:
        reward += 0.1
    
    # Capacity availability (0.0 - 0.3)
    capacity_score = status.get_capacity_score()
    reward += capacity_score * 0.3
    
    return min(1.0, reward)


def get_combined_rewards(
    self,
    miner_uids: List[int],
    service_responses: Optional[List[ServiceRequest]] = None,
    infra_responses: Optional[List[InfrastructureStatus]] = None,
    revenue_rewards: Optional[np.ndarray] = None,
) -> np.ndarray:
    """
    Calculate combined rewards for miners based on multiple signals.
    
    The reward combines:
    - Revenue-based rewards (50% weight) - from RevenueTracker
    - Performance rewards (30% weight) - from service responses
    - Infrastructure rewards (20% weight) - from infrastructure status
    
    Args:
        self: Validator instance
        miner_uids: List of miner UIDs to calculate rewards for
        service_responses: Optional list of service request responses
        infra_responses: Optional list of infrastructure status responses
        revenue_rewards: Pre-calculated revenue-based rewards from RevenueTracker
        
    Returns:
        Combined reward array normalized to [0, 1]
    """
    n_miners = len(miner_uids)
    
    # Initialize reward components
    performance_rewards = np.zeros(n_miners, dtype=np.float32)
    infra_rewards = np.zeros(n_miners, dtype=np.float32)
    rev_rewards = revenue_rewards if revenue_rewards is not None else np.zeros(n_miners, dtype=np.float32)
    
    # Calculate performance rewards from service responses
    if service_responses is not None:
        for idx, response in enumerate(service_responses):
            if response is not None:
                performance_rewards[idx] = calculate_service_reward(response)
    
    # Calculate infrastructure rewards
    if infra_responses is not None:
        for idx, status in enumerate(infra_responses):
            if status is not None:
                infra_rewards[idx] = calculate_infrastructure_reward(status)
    
    # Combine rewards with weights
    combined = (
        REVENUE_REWARD_WEIGHT * rev_rewards +
        PERFORMANCE_REWARD_WEIGHT * performance_rewards +
        INFRASTRUCTURE_REWARD_WEIGHT * infra_rewards
    )
    
    # Normalize to [0, 1]
    max_reward = np.max(combined) if np.max(combined) > 0 else 1.0
    normalized = combined / max_reward
    
    bt.logging.info(
        f"Reward breakdown - Revenue: {np.mean(rev_rewards):.4f}, "
        f"Performance: {np.mean(performance_rewards):.4f}, "
        f"Infrastructure: {np.mean(infra_rewards):.4f}, "
        f"Combined: {np.mean(normalized):.4f}"
    )
    
    return normalized


def get_revenue_weighted_scores(
    miner_revenues: Dict[str, float],
    miner_uids: List[int],
    metagraph,
) -> np.ndarray:
    """
    Calculate scores weighted by revenue contribution.
    
    Miners who generate more revenue get proportionally higher scores,
    reflecting the 50% revenue share incentive mechanism.
    
    Args:
        miner_revenues: Dictionary mapping miner hotkey to revenue generated
        miner_uids: List of miner UIDs
        metagraph: Network metagraph for hotkey lookups
        
    Returns:
        Revenue-weighted score array
    """
    scores = np.zeros(len(miner_uids), dtype=np.float32)
    
    # Calculate total revenue
    total_revenue = sum(miner_revenues.values())
    if total_revenue <= 0:
        return scores
    
    for idx, uid in enumerate(miner_uids):
        try:
            hotkey = metagraph.hotkeys[uid]
            revenue = miner_revenues.get(hotkey, 0.0)
            
            # Score is proportional to revenue share
            # Miners with higher revenue get higher scores
            scores[idx] = revenue / total_revenue
            
            if revenue > 0:
                bt.logging.debug(
                    f"Miner {uid}: revenue={revenue:.6f}, "
                    f"share={scores[idx]*100:.2f}%"
                )
        except (IndexError, KeyError):
            continue
    
    return scores
