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
KubeTEE AI Validator Forward Pass with Multi-Mechanism Support

Implements the validator's forward pass using native Bittensor Multiple
Incentive Mechanisms as documented at:
https://docs.learnbittensor.org/subnets/understanding-multiple-mech-subnets

The forward pass collects data for all 3 mechanisms:

1. INFRASTRUCTURE (Mechanism 0) - 50% emissions
   - Queries miners for infrastructure status
   - Processes service requests with revenue tracking
   - Miners receive 50% of service revenue

2. OPEN SOURCE (Mechanism 1) - 30% emissions
   - Evaluates code contributions
   - Runs benchmarks on miner submissions
   - Competition-based scoring

3. RESELLERS (Mechanism 2) - 20% emissions
   - Tracks user referrals
   - Attributes revenue to referring resellers
   - Distribution channel rewards

Each mechanism has separate weight matrices set via mechanism_id.
"""

import time
import uuid
import bittensor as bt

from template.protocol import Dummy, ServiceRequest, InfrastructureStatus, ServiceType
from template.validator.reward import get_rewards
from template.utils.uids import get_random_uids


async def forward(self):
    """
    Validator forward pass with multi-mechanism support.

    Collects metrics for all 3 incentive mechanisms:
    - Infrastructure: health checks, service processing, revenue tracking
    - Open Source: benchmark evaluation (periodic)
    - Resellers: referral attribution

    Each mechanism's scores are tracked separately and weights are
    set per mechanism using the native Bittensor multi-mechanism API.

    Reference: https://docs.learnbittensor.org/subnets/understanding-multiple-mech-subnets

    Args:
        self: The validator neuron instance
    """
    # Select miners to query
    miner_uids = get_random_uids(self, k=self.config.neuron.sample_size)
    
    if not miner_uids:
        bt.logging.warning("No miners available to query")
        time.sleep(5)
        return

    # Ensure mechanism manager is initialized
    if not hasattr(self, 'mechanism_manager'):
        bt.logging.warning("MechanismManager not initialized, skipping forward")
        time.sleep(5)
        return

    # ==========================================================================
    # MECHANISM 0: INFRASTRUCTURE (50% emissions)
    # ==========================================================================
    
    # Phase 1: Query infrastructure status for health metrics
    infra_responses = await query_infrastructure_status(self, miner_uids)
    
    # Record infrastructure health for each miner
    for idx, uid in enumerate(miner_uids):
        response = infra_responses[idx] if idx < len(infra_responses) else None
        if response is not None and response.cluster_id:
            self.mechanism_manager.record_infrastructure_health(
                miner_hotkey=self.metagraph.hotkeys[uid],
                miner_uid=uid,
                success=True,
                latency_ms=response.latency_ms if hasattr(response, 'latency_ms') else 0,
                tee_enabled=response.tee_enabled,
                tee_type=response.tee_type,
                fips_enabled=response.fips_enabled,
                gpu_available=response.gpu_available,
                gpu_total=response.gpu_total,
                cluster_id=response.cluster_id,
                region=response.region,
            )
        else:
            self.mechanism_manager.record_infrastructure_health(
                miner_hotkey=self.metagraph.hotkeys[uid],
                miner_uid=uid,
                success=False,
            )
    
    # Phase 2: Process service requests and track revenue
    service_responses = await process_service_requests(self, miner_uids)
    
    # Phase 3: Run basic connectivity test
    dummy_responses = await query_dummy(self, miner_uids)
    
    # ==========================================================================
    # MECHANISM 1: OPEN SOURCE (30% emissions)
    # - Benchmark evaluation runs periodically (not every forward pass)
    # ==========================================================================
    
    if self.step % 100 == 0:  # Every 100 steps
        bt.logging.info("Running periodic open source benchmark evaluation...")
        # This would trigger benchmark runs on miner code submissions
        # Results are recorded via mechanism_manager.record_benchmark_results()
    
    # ==========================================================================
    # MECHANISM 2: RESELLERS (20% emissions)
    # - Revenue attribution happens automatically when services are processed
    # - via mechanism_manager.record_service_revenue() with user_hotkey
    # ==========================================================================
    
    # ==========================================================================
    # SCORE UPDATES
    # ==========================================================================
    
    # Calculate weights for each mechanism
    all_weights = self.mechanism_manager.calculate_all_weights(
        miner_uids=miner_uids,
        metagraph=self.metagraph,
    )
    
    # Log mechanism summaries
    bt.logging.info(f"Step {self.step}: Processed {len(miner_uids)} miners")
    
    for mech_type, weights in all_weights.items():
        non_zero = (weights > 0).sum()
        bt.logging.debug(
            f"  {mech_type.name}: {non_zero}/{len(weights)} miners with non-zero weight"
        )
    
    # Update combined scores for base class compatibility
    # The actual per-mechanism weights are set in set_weights()
    from template.mechanisms import MechanismType, MECHANISMS
    import numpy as np
    
    combined_scores = np.zeros(len(miner_uids), dtype=np.float32)
    for mechanism in MECHANISMS:
        weights = all_weights.get(mechanism.mechanism_type)
        if weights is not None:
            emission_weight = mechanism.emission_percentage / 100.0
            combined_scores += emission_weight * weights
    
    # Normalize
    total = np.sum(combined_scores)
    if total > 0:
        combined_scores = combined_scores / total
    
    self.update_scores(combined_scores, miner_uids)
    
    time.sleep(5)


async def query_infrastructure_status(self, miner_uids: list) -> list:
    """
    Query miners for their infrastructure status.
    
    Args:
        self: Validator instance
        miner_uids: List of miner UIDs to query
        
    Returns:
        List of InfrastructureStatus responses
    """
    try:
        responses = await self.dendrite(
            axons=[self.metagraph.axons[uid] for uid in miner_uids],
            synapse=InfrastructureStatus(query_timestamp=time.time()),
            deserialize=False,
            timeout=10.0,
        )
        
        valid_count = sum(1 for r in responses if r is not None and r.cluster_id)
        bt.logging.debug(f"Infrastructure status: {valid_count}/{len(miner_uids)} valid responses")
        
        return responses
    except Exception as e:
        bt.logging.error(f"Error querying infrastructure status: {e}")
        return [None] * len(miner_uids)


async def process_service_requests(self, miner_uids: list) -> list:
    """
    Process pending service requests and track revenue.
    
    This simulates processing user service requests. In production,
    requests would come from the user API/queue.
    
    Args:
        self: Validator instance
        miner_uids: List of miner UIDs to query
        
    Returns:
        List of ServiceRequest responses
    """
    # Check if there are pending service requests
    # In production, this would pull from a request queue
    if not hasattr(self, 'pending_service_requests'):
        self.pending_service_requests = []
    
    if not self.pending_service_requests:
        bt.logging.debug("No pending service requests")
        return [None] * len(miner_uids)
    
    responses = []
    
    for uid in miner_uids:
        # Get next pending request if available
        if self.pending_service_requests:
            request = self.pending_service_requests.pop(0)
            
            try:
                # Send request to miner
                request.timestamp_start = time.time()
                response = await self.dendrite(
                    axons=[self.metagraph.axons[uid]],
                    synapse=request,
                    deserialize=False,
                    timeout=30.0,
                )
                
                if response and len(response) > 0:
                    resp = response[0]
                    
                    # Record service usage for revenue tracking
                    if resp.success:
                        usage = create_service_usage_from_request(
                            user_hotkey=resp.user_hotkey,
                            miner_hotkey=self.metagraph.hotkeys[uid],
                            miner_uid=uid,
                            service_type=resp.service_type,
                            tokens_processed=resp.get_total_tokens(),
                            gpu_seconds=resp.gpu_seconds,
                            latency_ms=resp.calculate_latency(),
                            success=resp.success,
                        )
                        
                        # Record in revenue tracker - miners get 50% of this
                        self.revenue_tracker.record_service_usage(usage)
                        
                        bt.logging.info(
                            f"Service completed: miner={uid}, "
                            f"type={resp.service_type}, "
                            f"tokens={resp.get_total_tokens()}, "
                            f"billed=${usage.billed_amount:.6f}"
                        )
                    
                    responses.append(resp)
                else:
                    responses.append(None)
                    
            except Exception as e:
                bt.logging.error(f"Error processing service request for miner {uid}: {e}")
                responses.append(None)
        else:
            responses.append(None)
    
    return responses


async def query_dummy(self, miner_uids: list) -> list:
    """
    Query miners with dummy request for basic connectivity testing.
    
    Args:
        self: Validator instance
        miner_uids: List of miner UIDs to query
        
    Returns:
        List of dummy responses
    """
    try:
        responses = await self.dendrite(
            axons=[self.metagraph.axons[uid] for uid in miner_uids],
            synapse=Dummy(dummy_input=self.step),
            deserialize=True,
            timeout=10.0,
        )
        
        bt.logging.debug(f"Dummy responses: {responses}")
        return responses
    except Exception as e:
        bt.logging.error(f"Error querying dummy: {e}")
        return [None] * len(miner_uids)


def submit_service_request(
    self,
    user_hotkey: str,
    prompt: str,
    service_type: str = ServiceType.INFERENCE.value,
    model_name: str = None,
    max_tokens: int = 1024,
    context: str = None,
) -> str:
    """
    Submit a new service request from a user.
    
    This function is called by the user API to submit requests
    that will be processed by the validator and forwarded to miners.
    
    Args:
        self: Validator instance
        user_hotkey: The user's hotkey for billing
        prompt: The prompt/query to process
        service_type: Type of AI service
        model_name: Optional model specification
        max_tokens: Maximum tokens to generate
        context: Optional context for RAG
        
    Returns:
        Request ID for tracking
    """
    if not hasattr(self, 'pending_service_requests'):
        self.pending_service_requests = []
    
    request_id = str(uuid.uuid4())
    
    request = ServiceRequest(
        user_hotkey=user_hotkey,
        service_type=service_type,
        request_id=request_id,
        prompt=prompt,
        context=context,
        model_name=model_name,
        max_tokens=max_tokens,
    )
    
    self.pending_service_requests.append(request)
    
    bt.logging.info(
        f"Submitted service request: id={request_id}, "
        f"user={user_hotkey[:16]}..., type={service_type}"
    )
    
    return request_id
