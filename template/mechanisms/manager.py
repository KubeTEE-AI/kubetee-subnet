# The MIT License (MIT)
# Copyright © 2023 KubeTEE AI

"""
Mechanism Manager for KubeTEE AI Subnet

Coordinates all three incentive mechanisms using native Bittensor
multiple incentive mechanism support.

Reference: https://docs.learnbittensor.org/subnets/understanding-multiple-mech-subnets

Key Features:
- Manages separate weight matrices per mechanism
- Sets weights using mechanism_id parameter
- Configures emission splits on-chain
- Coordinates scoring across all mechanisms
"""

import numpy as np
from typing import Dict, List, Optional, Tuple
from pathlib import Path
import bittensor as bt

from .definitions import (
    MechanismType,
    MechanismConfig,
    MECHANISMS,
    MECHANISM_INFRASTRUCTURE,
    MECHANISM_OPEN_SOURCE,
    MECHANISM_RESELLERS,
    get_emission_split_vector,
    validate_emission_splits,
    log_mechanism_config,
)
from .infrastructure import InfrastructureScorer
from .open_source import OpenSourceScorer
from .resellers import ResellerScorer


class MechanismManager:
    """
    Manages multiple incentive mechanisms for the KubeTEE AI subnet.
    
    This class coordinates:
    1. Infrastructure Mechanism (50% emissions) - Service provision rewards
    2. Open Source Mechanism (30% emissions) - Competition rewards
    3. Reseller Mechanism (20% emissions) - Distribution channel rewards
    
    Each mechanism has:
    - Independent weight matrix
    - Separate bond pools (Yuma Consensus)
    - Configurable emission split
    
    NOTE: As of current Bittensor runtime, only 2 mechanisms are supported.
    This implementation is future-ready for when the cap is raised to 3+.
    """
    
    # Current Bittensor limit
    MAX_MECHANISMS_SUPPORTED = 2
    
    def __init__(self, storage_path: str, subtensor=None, wallet=None, netuid: int = None):
        """
        Initialize the mechanism manager.
        
        Args:
            storage_path: Path for storing mechanism data
            subtensor: Bittensor subtensor instance (for on-chain operations)
            wallet: Bittensor wallet (for signing transactions)
            netuid: Subnet network UID
        """
        self.storage_path = Path(storage_path)
        self.storage_path.mkdir(parents=True, exist_ok=True)
        
        self.subtensor = subtensor
        self.wallet = wallet
        self.netuid = netuid
        
        # Initialize scorers for each mechanism
        self.infrastructure_scorer = InfrastructureScorer(
            str(self.storage_path / "infrastructure")
        )
        self.open_source_scorer = OpenSourceScorer(
            str(self.storage_path / "open_source")
        )
        self.reseller_scorer = ResellerScorer(
            str(self.storage_path / "resellers")
        )
        
        # Map mechanism IDs to scorers
        self.scorers = {
            MechanismType.INFRASTRUCTURE: self.infrastructure_scorer,
            MechanismType.OPEN_SOURCE: self.open_source_scorer,
            MechanismType.RESELLERS: self.reseller_scorer,
        }
        
        # Validate configuration
        if not validate_emission_splits():
            raise ValueError("Emission splits must sum to 100%")
        
        # Log configuration
        log_mechanism_config()
        
        # Check mechanism limit
        if len(MECHANISMS) > self.MAX_MECHANISMS_SUPPORTED:
            bt.logging.warning(
                f"⚠️ KubeTEE uses {len(MECHANISMS)} mechanisms, but Bittensor currently "
                f"only supports {self.MAX_MECHANISMS_SUPPORTED}. "
                f"Waiting for cap to be raised. See: "
                f"https://docs.learnbittensor.org/subnets/understanding-multiple-mech-subnets"
            )
        
        bt.logging.info(
            f"MechanismManager initialized with {len(MECHANISMS)} mechanisms"
        )
    
    def configure_emission_splits(self) -> bool:
        """
        Configure emission splits on-chain using sudo_set_mechanism_emission_split.
        
        This should be called by the subnet owner to set up the emission distribution.
        
        The emission split vector is calculated as:
        - Infrastructure (50%): 32767 (50% × 65535)
        - Open Source (30%): 19661 (30% × 65535)
        - Resellers (20%): 13107 (20% × 65535)
        
        Returns:
            True if successful, False otherwise
        """
        if self.subtensor is None or self.wallet is None or self.netuid is None:
            bt.logging.error("Subtensor, wallet, and netuid required for on-chain operations")
            return False
        
        emission_split = get_emission_split_vector()
        
        bt.logging.info(
            f"Configuring emission splits for netuid {self.netuid}:\n"
            f"  Mechanism 0 (Infrastructure): {MECHANISM_INFRASTRUCTURE.emission_percentage}%\n"
            f"  Mechanism 1 (Open Source): {MECHANISM_OPEN_SOURCE.emission_percentage}%\n"
            f"  Mechanism 2 (Resellers): {MECHANISM_RESELLERS.emission_percentage}%\n"
            f"  Split vector: {emission_split}"
        )
        
        try:
            # Note: This uses the Bittensor SDK's sudo_set_mechanism_emission_split
            # The exact API may vary - adjust based on SDK version
            result = self.subtensor.sudo_set_mechanism_emission_split(
                wallet=self.wallet,
                netuid=self.netuid,
                emission_split=emission_split,
            )
            
            if result:
                bt.logging.info("✅ Emission splits configured successfully on-chain")
                return True
            else:
                bt.logging.error("❌ Failed to configure emission splits")
                return False
                
        except AttributeError:
            bt.logging.warning(
                "sudo_set_mechanism_emission_split not available in current SDK. "
                "This feature requires Bittensor SDK with multi-mechanism support."
            )
            return False
        except Exception as e:
            bt.logging.error(f"Error configuring emission splits: {e}")
            return False
    
    def calculate_all_weights(
        self,
        miner_uids: List[int],
        metagraph,
    ) -> Dict[MechanismType, np.ndarray]:
        """
        Calculate weights for all mechanisms.
        
        Returns separate weight arrays for each mechanism, which should be
        set on-chain using set_weights with the appropriate mechanism_id.
        
        Args:
            miner_uids: List of miner UIDs
            metagraph: Network metagraph
            
        Returns:
            Dictionary mapping mechanism type to weight array
        """
        weights = {}
        
        for mechanism in MECHANISMS:
            scorer = self.scorers.get(mechanism.mechanism_type)
            if scorer:
                mechanism_weights = scorer.calculate_weights(miner_uids, metagraph)
                weights[mechanism.mechanism_type] = mechanism_weights
                
                bt.logging.debug(
                    f"Calculated weights for {mechanism.name}: "
                    f"non-zero={np.count_nonzero(mechanism_weights)}/{len(mechanism_weights)}"
                )
        
        return weights
    
    def set_all_weights(
        self,
        miner_uids: List[int],
        metagraph,
        version_key: int = 0,
    ) -> Dict[MechanismType, bool]:
        """
        Set weights for all mechanisms on-chain.
        
        Uses the native Bittensor set_weights with mechanism_id parameter.
        
        Reference: https://docs.learnbittensor.org/subnets/understanding-multiple-mech-subnets
        
        Args:
            miner_uids: List of miner UIDs
            metagraph: Network metagraph
            version_key: Version key for the weights
            
        Returns:
            Dictionary mapping mechanism type to success status
        """
        if self.subtensor is None or self.wallet is None or self.netuid is None:
            bt.logging.error("Subtensor, wallet, and netuid required for on-chain operations")
            return {m.mechanism_type: False for m in MECHANISMS}
        
        # Calculate weights for all mechanisms
        all_weights = self.calculate_all_weights(miner_uids, metagraph)
        
        results = {}
        
        for mechanism in MECHANISMS:
            weights = all_weights.get(mechanism.mechanism_type)
            if weights is None:
                results[mechanism.mechanism_type] = False
                continue
            
            try:
                # Convert to uint16 format required by Bittensor
                uint_weights = (weights * 65535).astype(np.uint16)
                
                bt.logging.info(
                    f"Setting weights for {mechanism.name} (mechanism_id={mechanism.mechanism_id})"
                )
                
                # Set weights with mechanism_id
                # Note: The exact API may vary based on SDK version
                result, msg = self.subtensor.set_weights(
                    wallet=self.wallet,
                    netuid=self.netuid,
                    uids=miner_uids,
                    weights=uint_weights,
                    mechanism_id=mechanism.mechanism_id,
                    version_key=version_key,
                    wait_for_finalization=False,
                    wait_for_inclusion=False,
                )
                
                results[mechanism.mechanism_type] = result
                
                if result:
                    bt.logging.info(f"✅ Set weights for {mechanism.name}")
                else:
                    bt.logging.warning(f"⚠️ Failed to set weights for {mechanism.name}: {msg}")
                    
            except TypeError as e:
                # mechanism_id parameter not supported in current SDK
                bt.logging.warning(
                    f"mechanism_id parameter not supported: {e}. "
                    f"Using fallback single-mechanism mode."
                )
                results[mechanism.mechanism_type] = False
            except Exception as e:
                bt.logging.error(f"Error setting weights for {mechanism.name}: {e}")
                results[mechanism.mechanism_type] = False
        
        return results
    
    def set_weights_fallback(
        self,
        miner_uids: List[int],
        metagraph,
        version_key: int = 0,
    ) -> bool:
        """
        Fallback: Set combined weights for single-mechanism mode.
        
        If multi-mechanism is not available, combine all mechanism scores
        into a single weight vector using their emission percentages.
        
        Args:
            miner_uids: List of miner UIDs
            metagraph: Network metagraph
            version_key: Version key
            
        Returns:
            True if successful
        """
        if self.subtensor is None or self.wallet is None or self.netuid is None:
            bt.logging.error("Subtensor, wallet, and netuid required")
            return False
        
        # Calculate weights for all mechanisms
        all_weights = self.calculate_all_weights(miner_uids, metagraph)
        
        # Combine with emission percentage weights
        combined_weights = np.zeros(len(miner_uids), dtype=np.float32)
        
        for mechanism in MECHANISMS:
            weights = all_weights.get(mechanism.mechanism_type)
            if weights is not None:
                emission_weight = mechanism.emission_percentage / 100.0
                combined_weights += emission_weight * weights
        
        # Normalize
        total = np.sum(combined_weights)
        if total > 0:
            combined_weights = combined_weights / total
        
        # Convert to uint16
        uint_weights = (combined_weights * 65535).astype(np.uint16)
        
        try:
            result, msg = self.subtensor.set_weights(
                wallet=self.wallet,
                netuid=self.netuid,
                uids=miner_uids,
                weights=uint_weights,
                version_key=version_key,
                wait_for_finalization=False,
                wait_for_inclusion=False,
            )
            
            if result:
                bt.logging.info("✅ Set combined weights (fallback mode)")
            else:
                bt.logging.warning(f"⚠️ Failed to set weights: {msg}")
            
            return result
            
        except Exception as e:
            bt.logging.error(f"Error setting weights: {e}")
            return False
    
    def finalize_epoch(self, epoch: int):
        """Finalize all mechanisms for the epoch."""
        bt.logging.info(f"Finalizing epoch {epoch} for all mechanisms")
        
        self.infrastructure_scorer.finalize_epoch(epoch)
        self.open_source_scorer.finalize_epoch(epoch)
        self.reseller_scorer.finalize_epoch(epoch)
        
        bt.logging.info(f"Epoch {epoch} finalized for all mechanisms")
    
    def get_mechanism_summary(self) -> Dict:
        """Get summary of all mechanisms."""
        return {
            "mechanisms": [
                {
                    "id": m.mechanism_id,
                    "name": m.name,
                    "emission_percentage": m.emission_percentage,
                    "miner_revenue_share": m.miner_revenue_share * 100 if m.miner_revenue_share > 0 else 0,
                }
                for m in MECHANISMS
            ],
            "emission_split_vector": get_emission_split_vector(),
            "infrastructure": self.infrastructure_scorer.get_revenue_summary(),
            "open_source": {
                "active_competitors": len(self.open_source_scorer.metrics),
                "leaderboard": self.open_source_scorer.get_leaderboard(3),
            },
            "resellers": self.reseller_scorer.get_reseller_summary(),
            "max_mechanisms_supported": self.MAX_MECHANISMS_SUPPORTED,
            "mechanisms_configured": len(MECHANISMS),
        }
    
    # ==========================================================================
    # Convenience methods for recording data
    # ==========================================================================
    
    def record_infrastructure_health(
        self,
        miner_hotkey: str,
        miner_uid: int,
        **kwargs
    ):
        """Record infrastructure health check. See InfrastructureScorer for params."""
        self.infrastructure_scorer.record_health_check(miner_hotkey, miner_uid, **kwargs)
    
    def record_service_revenue(
        self,
        miner_hotkey: str,
        miner_uid: int,
        revenue_amount: float,
        user_hotkey: Optional[str] = None,
    ):
        """
        Record service revenue for a miner.
        
        Also attributes to reseller if user was referred.
        """
        # Record for infrastructure mechanism (miner gets 50%)
        self.infrastructure_scorer.record_service_revenue(miner_hotkey, miner_uid, revenue_amount)
        
        # Attribute to reseller if applicable
        if user_hotkey:
            self.reseller_scorer.record_user_revenue(user_hotkey, revenue_amount)
    
    def record_benchmark_results(
        self,
        miner_hotkey: str,
        miner_uid: int,
        **kwargs
    ):
        """Record benchmark results. See OpenSourceScorer for params."""
        self.open_source_scorer.record_benchmark_results(miner_hotkey, miner_uid, **kwargs)
    
    def register_reseller(
        self,
        reseller_hotkey: str,
        reseller_uid: int,
        **kwargs
    ):
        """Register a reseller. See ResellerScorer for params."""
        self.reseller_scorer.register_reseller(reseller_hotkey, reseller_uid, **kwargs)
    
    def record_referral(
        self,
        reseller_hotkey: str,
        reseller_uid: int,
        user_hotkey: str,
    ):
        """Record a user referral."""
        self.reseller_scorer.record_referral(reseller_hotkey, reseller_uid, user_hotkey)

