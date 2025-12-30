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
KubeTEE AI Subnet Protocol Definitions

This module defines the communication protocols between validators and miners
for the KubeTEE AI subnet. It includes:

1. ServiceRequest - For AI inference and service requests with revenue tracking
2. InfrastructureStatus - For infrastructure health and capacity reporting
3. Dummy - Legacy test protocol

All protocols include metrics for:
- Revenue generation and miner incentivization (50% revenue share)
- Quality of service (latency, success rate)
- Resource consumption (GPU, CPU, memory, tokens)
"""

import time
import typing
from enum import Enum
import bittensor as bt


class ServiceType(str, Enum):
    """Types of AI services offered by miners."""
    INFERENCE = "inference"           # LLM inference
    RAG = "rag"                       # Retrieval-Augmented Generation
    EMBEDDING = "embedding"           # Text embedding
    FINE_TUNING = "fine_tuning"       # Model fine-tuning
    DEEP_RESEARCH = "deep_research"   # Deep research agent
    STREAMING_RAG = "streaming_rag"   # Streaming data to RAG
    CUSTOM = "custom"                 # Custom AI service


class ServiceRequest(bt.Synapse):
    """
    AI Service Request Protocol for KubeTEE AI Subnet.
    
    This protocol enables validators to send AI service requests to miners
    and track usage for revenue calculation and miner incentivization.
    
    Miners receive 50% of the revenue generated from serving user requests.
    
    Attributes:
    - user_hotkey: The hotkey of the user making the request
    - service_type: Type of AI service requested
    - request_id: Unique identifier for the request
    - prompt: The input prompt or query
    - context: Optional context for RAG/retrieval
    - model_name: Optional specific model to use
    - max_tokens: Maximum tokens to generate
    - response: The generated response from the miner
    - tokens_input: Number of input tokens processed
    - tokens_output: Number of output tokens generated
    - gpu_seconds: GPU compute time consumed
    - latency_ms: Total request latency
    - success: Whether the request was successful
    - error_message: Error details if request failed
    - timestamp_start: Request start timestamp
    - timestamp_end: Request end timestamp
    """
    
    # === Request Fields (filled by validator/user) ===
    
    # User identification for billing
    user_hotkey: str
    
    # Service type
    service_type: str = ServiceType.INFERENCE.value
    
    # Unique request ID for tracking
    request_id: str = ""
    
    # The prompt/query to process
    prompt: str
    
    # Optional context for RAG
    context: typing.Optional[str] = None
    
    # Optional model specification
    model_name: typing.Optional[str] = None
    
    # Token limits
    max_tokens: int = 1024
    
    # Request timestamp
    timestamp_start: float = 0.0
    
    # === Response Fields (filled by miner) ===
    
    # The generated response
    response: typing.Optional[str] = None
    
    # Token counts for billing
    tokens_input: int = 0
    tokens_output: int = 0
    
    # Resource consumption for billing
    gpu_seconds: float = 0.0
    cpu_seconds: float = 0.0
    memory_gb_seconds: float = 0.0
    
    # Quality metrics
    latency_ms: float = 0.0
    success: bool = True
    error_message: typing.Optional[str] = None
    
    # Response timestamp
    timestamp_end: float = 0.0
    
    def deserialize(self) -> typing.Optional[str]:
        """Deserialize the response."""
        return self.response
    
    def get_total_tokens(self) -> int:
        """Get total tokens processed (input + output)."""
        return self.tokens_input + self.tokens_output
    
    def calculate_latency(self) -> float:
        """Calculate latency in milliseconds."""
        if self.timestamp_end > 0 and self.timestamp_start > 0:
            return (self.timestamp_end - self.timestamp_start) * 1000
        return self.latency_ms


class InfrastructureStatus(bt.Synapse):
    """
    Infrastructure Status Protocol for KubeTEE AI Subnet.
    
    This protocol enables validators to query miners about their
    infrastructure capacity and health for proper load balancing
    and quality scoring.
    
    Attributes:
    - cluster_id: Miner's Kubernetes cluster identifier
    - region: Geographic region (Americas, EU, Middle East, Africa, Asia)
    - gpu_available: Available GPU compute capacity
    - gpu_total: Total GPU compute capacity
    - gpu_model: GPU model (H100, H200, etc.)
    - cpu_available: Available CPU cores
    - memory_available_gb: Available memory in GB
    - tee_enabled: Whether TEE is enabled
    - uptime_percentage: Infrastructure uptime percentage
    - active_requests: Current active request count
    - max_concurrent_requests: Maximum concurrent request capacity
    """
    
    # === Request Fields ===
    # Request timestamp
    query_timestamp: float = 0.0
    
    # === Response Fields (filled by miner) ===
    
    # Cluster identification
    cluster_id: typing.Optional[str] = None
    region: typing.Optional[str] = None
    continent: typing.Optional[str] = None
    country: typing.Optional[str] = None
    city: typing.Optional[str] = None
    
    # GPU capacity
    gpu_available: float = 0.0
    gpu_total: float = 0.0
    gpu_model: typing.Optional[str] = None
    
    # CPU and memory
    cpu_available: float = 0.0
    cpu_total: float = 0.0
    memory_available_gb: float = 0.0
    memory_total_gb: float = 0.0
    
    # Security features
    tee_enabled: bool = False
    tee_type: typing.Optional[str] = None  # TDX, SGX, SEV
    fips_enabled: bool = False
    
    # Health metrics
    uptime_percentage: float = 100.0
    active_requests: int = 0
    max_concurrent_requests: int = 100
    
    # Services available
    available_services: typing.List[str] = []
    available_models: typing.List[str] = []
    
    # Response timestamp
    response_timestamp: float = 0.0
    
    def deserialize(self) -> dict:
        """Deserialize infrastructure status as a dictionary."""
        return {
            "cluster_id": self.cluster_id,
            "region": self.region,
            "gpu_available": self.gpu_available,
            "gpu_total": self.gpu_total,
            "gpu_model": self.gpu_model,
            "tee_enabled": self.tee_enabled,
            "uptime_percentage": self.uptime_percentage,
            "active_requests": self.active_requests,
            "max_concurrent_requests": self.max_concurrent_requests,
            "available_services": self.available_services
        }
    
    def get_capacity_score(self) -> float:
        """Calculate a capacity score (0-1) based on available resources."""
        if self.gpu_total <= 0:
            return 0.0
        gpu_util = self.gpu_available / self.gpu_total
        request_capacity = 1.0 - (self.active_requests / max(self.max_concurrent_requests, 1))
        return (gpu_util + request_capacity) / 2


class Dummy(bt.Synapse):
    """
    A simple dummy protocol for testing.
    
    This protocol is used for basic connectivity testing between
    validators and miners.

    Attributes:
    - dummy_input: An integer value representing the input request.
    - dummy_output: The response from the miner (should be input * 2).
    """

    # Required request input, filled by sending dendrite caller.
    dummy_input: int

    # Optional request output, filled by receiving axon.
    dummy_output: typing.Optional[int] = None

    def deserialize(self) -> int:
        """
        Deserialize the dummy output.

        Returns:
        - int: The deserialized response (dummy_output value).
        """
        return self.dummy_output
