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
KubeTEE AI Subnet Validator with Multi-Mechanism Support

Implements native Bittensor Multiple Incentive Mechanisms as documented at:
https://docs.learnbittensor.org/subnets/understanding-multiple-mech-subnets

═══════════════════════════════════════════════════════════════════════════════
                         EMISSION MECHANISMS (2 Total)
═══════════════════════════════════════════════════════════════════════════════

1. INFRASTRUCTURE (Mechanism 0) - 60% of emissions
   - Rewards miners for providing Kubernetes infrastructure
   - Metrics: uptime, TEE compliance, capacity, latency
   - Miners can be BOTH infrastructure AND open source contributors

2. OPEN SOURCE (Mechanism 1) - 40% of emissions
   - Rewards miners for improving the subnet tech stack
   - Metrics: benchmark scores, code quality, CI/CD compliance
   - Competition-based scoring

═══════════════════════════════════════════════════════════════════════════════
                   RESELLERS (ON-CHAIN PAYMENTS - NO EMISSIONS)
═══════════════════════════════════════════════════════════════════════════════

Resellers are a special category of "miners" that:
- Do NOT receive emissions
- Do NOT register on the Bittensor subnet
- DO register via KubeTEE CLI → Creates Rancher account
- DO deposit Alpha/TAO to KubeTEEPayment smart contract
- Validators calculate usage and transfer funds each epoch to KubeTEE Owner

PAYMENT FLOW:
1. Reseller deposits Alpha/TAO to on-chain contract
2. Uses KubeTEE services via Rancher namespace
3. Validators report usage per epoch (multi-sig confirmation)
4. Contract transfers funds from reseller to KubeTEE Owner

═══════════════════════════════════════════════════════════════════════════════
                        FUTURE COMPATIBILITY
═══════════════════════════════════════════════════════════════════════════════

- ERC-8004 (Decentralized Paymaster)
- x.402 (HTTP 402 Payment Required protocol)

Each emission mechanism has:
- Independent weight matrix
- Separate bond pools (independent Yuma Consensus)
- Configurable emission split (on-chain transparency)
"""

import time
import numpy as np
from pathlib import Path

# Bittensor
import bittensor as bt

# LEGACY REMOVED (v10 template/base)
# This file still references old BaseValidatorNeuron for mechanisms.
# For v11 owner-recycle use case see scripts/owner_validator.py
# TODO: refactor mechanisms to new structure (no BaseValidatorNeuron).
raise ImportError(
    "Legacy template.base removed. "
    "Use scripts/owner_validator.py for the emission recycle validator. "
    "See docs and testing pyramid for v11 refactor plan."
)

# Multi-mechanism support (2 emission mechanisms only)
from template.mechanisms import (
    MechanismManager,
    MechanismType,
    EMISSION_MECHANISMS,
    MECHANISM_INFRASTRUCTURE,
    MECHANISM_OPEN_SOURCE,
    get_emission_split_vector,
)

# On-chain reseller payment processing
from template.reseller import (
    OnChainClient,
    OnChainConfig,
    ValidatorEpochProcessor,
    EpochUsageReport,
)


class Validator(BaseValidatorNeuron):
    """
    KubeTEE AI Validator Neuron with Multi-Mechanism Support.
    
    Implements the native Bittensor Multiple Incentive Mechanisms feature
    with 2 emission-based mechanisms:
    
    - Infrastructure (60%): Miners providing K8s infrastructure
    - Open Source (40%): Miners improving tech stack
    
    RESELLERS (special category - NO emissions):
    - Register via KubeTEE CLI (not on Bittensor subnet)
    - Deposit Alpha/TAO to on-chain contract
    - Validators report usage each epoch
    - Contract transfers to KubeTEE Owner
    
    Reference: https://docs.learnbittensor.org/subnets/understanding-multiple-mech-subnets
    """

    def __init__(self, config=None):
        super(Validator, self).__init__(config=config)

        bt.logging.info("load_state()")
        self.load_state()

        # Initialize multi-mechanism manager (emissions)
        self._init_mechanism_manager()
        
        # Initialize on-chain reseller payment processor
        self._init_reseller_processor()
        
        # Track current epoch
        self.last_finalized_epoch = 0
        
        # Log mechanism configuration
        self._log_mechanism_config()

    def _init_mechanism_manager(self):
        """Initialize the multi-mechanism manager for emissions."""
        storage_path = self.config.neuron.full_path + "/mechanisms"
        
        self.mechanism_manager = MechanismManager(
            storage_path=storage_path,
            subtensor=self.subtensor,
            wallet=self.wallet,
            netuid=self.config.netuid,
        )
        
        bt.logging.info(f"MechanismManager initialized at {storage_path}")
    
    def _init_reseller_processor(self):
        """
        Initialize on-chain reseller payment processor.
        
        This handles the non-emission reseller payments via
        the KubeTEEPayment smart contract on Bittensor EVM.
        """
        try:
            # Load on-chain config from environment or config file
            onchain_config = OnChainConfig(
                rpc_url=getattr(self.config, 'evm_rpc_url', 'https://evm.bittensor.network'),
                contract_address=getattr(self.config, 'payment_contract', ''),
                payment_token_address=getattr(self.config, 'payment_token', ''),
            )
            
            # Get validator's EVM private key
            validator_evm_key = getattr(self.config, 'validator_evm_key', None)
            
            if onchain_config.contract_address and validator_evm_key:
                self.onchain_client = OnChainClient(onchain_config)
                self.reseller_processor = ValidatorEpochProcessor(
                    self.onchain_client,
                    validator_evm_key
                )
                bt.logging.info("🔗 On-chain reseller processor initialized")
                bt.logging.info(f"   Contract: {onchain_config.contract_address}")
            else:
                self.onchain_client = None
                self.reseller_processor = None
                bt.logging.warning(
                    "⚠️ On-chain reseller processor not configured. "
                    "Set payment_contract and validator_evm_key to enable."
                )
        except Exception as e:
            bt.logging.warning(f"Could not initialize reseller processor: {e}")
            self.onchain_client = None
            self.reseller_processor = None
    
    def _log_mechanism_config(self):
        """Log the mechanism configuration."""
        bt.logging.info("=" * 60)
        bt.logging.info("KubeTEE AI Multi-Mechanism Configuration")
        bt.logging.info("=" * 60)
        
        bt.logging.info("EMISSION MECHANISMS (registered miners):")
        for mechanism in EMISSION_MECHANISMS:
            bt.logging.info(
                f"  Mechanism {mechanism.mechanism_id}: {mechanism.name} "
                f"({mechanism.emission_percentage}% emissions)"
            )
        
        bt.logging.info(f"  Emission split vector: {get_emission_split_vector()}")
        
        bt.logging.info("")
        bt.logging.info("RESELLER PAYMENTS (on-chain, no emissions):")
        if self.reseller_processor:
            bt.logging.info("  ✅ On-chain processor active")
            bt.logging.info(f"  Contract epoch: {self.onchain_client.get_current_epoch()}")
        else:
            bt.logging.info("  ⚠️ On-chain processor not configured")
        
        bt.logging.info("=" * 60)

    async def forward(self):
        """
        Validator forward pass with multi-mechanism support.
        
        For each mechanism, the validator:
        1. Collects relevant metrics from miners
        2. Calculates mechanism-specific scores
        3. Prepares weights for that mechanism
        
        Weights are set separately per mechanism using mechanism_id.
        """
        from template.validator import forward
        return await forward(self)
    
    def set_weights(self):
        """
        Set weights for all mechanisms using native Bittensor multi-mechanism.
        
        This overrides the base class to use separate weight matrices per mechanism.
        Each mechanism has its own Yuma Consensus calculation.
        
        Reference: https://docs.learnbittensor.org/subnets/understanding-multiple-mech-subnets
        """
        # Check if self.scores contains any NaN values
        if np.isnan(self.scores).any():
            bt.logging.warning(
                "Scores contain NaN values. This may be due to a lack of responses."
            )
        
        # Get miner UIDs
        miner_uids = list(range(len(self.metagraph.hotkeys)))
        
        # Try to set weights using multi-mechanism
        results = self.mechanism_manager.set_all_weights(
            miner_uids=miner_uids,
            metagraph=self.metagraph,
            version_key=self.spec_version,
        )
        
        # Check if any mechanism succeeded
        any_success = any(results.values())
        
        if not any_success:
            bt.logging.warning(
                "Multi-mechanism weight setting failed. "
                "Falling back to combined single-mechanism mode."
            )
            
            # Fallback to combined weights
            success = self.mechanism_manager.set_weights_fallback(
                miner_uids=miner_uids,
                metagraph=self.metagraph,
                version_key=self.spec_version,
            )
            
            if success:
                bt.logging.info("✅ Set combined weights (fallback mode)")
            else:
                bt.logging.error("❌ Failed to set weights in any mode")
        else:
            successful = [m.name for m in EMISSION_MECHANISMS if results.get(m.mechanism_type)]
            bt.logging.info(f"✅ Set weights for mechanisms: {successful}")
    
    def sync(self):
        """
        Extended sync to include mechanism epoch finalization.
        
        At the end of each epoch:
        1. Finalizes emission mechanisms
        2. Processes on-chain reseller payments
        3. Logs summary
        4. Prepares for next epoch
        """
        # Check if we should finalize the epoch
        current_epoch = self.block // self.config.neuron.epoch_length
        
        if current_epoch > self.last_finalized_epoch and hasattr(self, 'mechanism_manager'):
            bt.logging.info(f"Finalizing epoch {self.last_finalized_epoch}")
            
            # Finalize emission mechanisms
            self.mechanism_manager.finalize_epoch(self.last_finalized_epoch)
            
            # Process on-chain reseller payments
            self._process_reseller_epoch()
            
            # Log summary
            summary = self.mechanism_manager.get_mechanism_summary()
            bt.logging.info(
                f"Epoch {self.last_finalized_epoch} Summary:\n"
                f"  Infrastructure Miners: {summary['infrastructure'].get('active_miners', 0)}\n"
                f"  Open Source Competitors: {summary['open_source'].get('active_competitors', 0)}"
            )
            
            self.last_finalized_epoch = current_epoch
        
        # Call parent sync
        super().sync()
    
    async def _process_reseller_epoch(self):
        """
        Process on-chain reseller payments for the epoch.
        
        Collects usage data from Rancher/Prometheus and submits
        settlement reports to the KubeTEEPayment smart contract.
        """
        if not self.reseller_processor:
            return
        
        try:
            # TODO: Collect usage data from Rancher/Prometheus
            # This would integrate with the Rancher API to get:
            # - CPU/GPU usage per namespace (reseller project)
            # - LLM token usage
            # - Storage usage
            rancher_usage_data = self._collect_rancher_usage()
            
            if not rancher_usage_data:
                bt.logging.debug("No reseller usage data to report")
                return
            
            # Submit on-chain
            tx_hash = await self.reseller_processor.process_epoch(rancher_usage_data)
            
            if tx_hash:
                bt.logging.info(f"📤 Reseller epoch settlement submitted: {tx_hash}")
        
        except Exception as e:
            bt.logging.error(f"Failed to process reseller epoch: {e}")
    
    def _collect_rancher_usage(self) -> dict:
        """
        Collect usage data from Rancher/Prometheus for reseller namespaces.
        
        Returns:
            Dict mapping rancher_project_id to usage metrics:
            {project_id: {'tokens': int, 'gpu_seconds': int}}
        """
        # TODO: Implement Rancher/Prometheus integration
        # This would query:
        # - Prometheus for GPU/CPU metrics per namespace
        # - Application logs for token counts
        # - Rancher API for namespace -> project mapping
        
        # Placeholder for integration
        return {}
    
    def save_state(self):
        """Extended save_state to include mechanism state."""
        super().save_state()
        
        # Save last finalized epoch
        if hasattr(self, 'last_finalized_epoch'):
            np.savez(
                self.config.neuron.full_path + "/mechanism_state.npz",
                last_finalized_epoch=self.last_finalized_epoch,
            )
    
    def load_state(self):
        """Extended load_state to include mechanism state."""
        super().load_state()
        
        # Load last finalized epoch
        state_file = Path(self.config.neuron.full_path) / "mechanism_state.npz"
        if state_file.exists():
            try:
                state = np.load(state_file)
                self.last_finalized_epoch = int(state["last_finalized_epoch"])
                bt.logging.info(
                    f"Loaded mechanism state: last_finalized_epoch={self.last_finalized_epoch}"
                )
            except Exception as e:
                bt.logging.warning(f"Could not load mechanism state: {e}")
                self.last_finalized_epoch = 0
    
    def configure_emission_splits(self) -> bool:
        """
        Configure emission splits on-chain (subnet owner only).
        
        Sets the emission distribution:
        - Infrastructure: 50%
        - Open Source: 30%
        - Resellers: 20%
        
        Uses sudo_set_mechanism_emission_split extrinsic.
        
        Returns:
            True if successful
        """
        if hasattr(self, 'mechanism_manager'):
            return self.mechanism_manager.configure_emission_splits()
        return False


# The main function parses the configuration and runs the validator.
if __name__ == "__main__":
    with Validator() as validator:
        while True:
            bt.logging.info(
                f"Validator running... block={validator.block}, step={validator.step}"
            )
            
            # Log mechanism stats periodically
            if hasattr(validator, 'mechanism_manager'):
                summary = validator.mechanism_manager.get_mechanism_summary()
                
                bt.logging.info(
                    f"EMISSION Mechanisms Summary:\n"
                    f"  Infrastructure (60%): {summary['infrastructure'].get('active_miners', 0)} active miners\n"
                    f"  Open Source (40%): {summary['open_source'].get('active_competitors', 0)} competitors"
                )
            
            # Log reseller (on-chain payment) stats
            if hasattr(validator, 'onchain_client') and validator.onchain_client:
                try:
                    resellers = validator.onchain_client.get_all_resellers()
                    current_epoch = validator.onchain_client.get_current_epoch()
                    bt.logging.info(
                        f"RESELLER On-Chain Stats:\n"
                        f"  Active Resellers: {len(resellers)}\n"
                        f"  Contract Epoch: {current_epoch}"
                    )
                except Exception:
                    pass
            
            time.sleep(60)  # Log every 60 seconds
