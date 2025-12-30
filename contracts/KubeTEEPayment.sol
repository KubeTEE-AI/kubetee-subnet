// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title KubeTEE Payment Contract
 * @author KubeTEE AI
 * @notice On-chain payment system for Resellers/White Label partners
 * @dev Deployed on Bittensor EVM - designed for future ERC-8004 / x.402 compatibility
 * 
 * ═══════════════════════════════════════════════════════════════════════════
 *                              ARCHITECTURE
 * ═══════════════════════════════════════════════════════════════════════════
 * 
 * RESELLERS/WHITE LABEL:
 * - Category of "miners" that DON'T receive emissions
 * - NOT registered on Bittensor subnet
 * - DO register via KubeTEE CLI → Creates Rancher account
 * - Must have coldkey/hotkey with Alpha
 * - Deposit Alpha/TAO to this contract
 * 
 * VALIDATORS:
 * - Calculate resource usage per reseller per epoch
 * - Submit usage reports on-chain
 * - Trigger transfers from reseller deposits to KubeTEE Owner
 * 
 * PAYMENT FLOW:
 * 1. Reseller deposits Alpha/TAO to this contract
 * 2. Reseller uses KubeTEE services (via Rancher namespace)
 * 3. Validators calculate usage each epoch
 * 4. Validators submit epoch settlement on-chain
 * 5. Contract transfers 50% of usage cost from reseller to KubeTEE Owner
 * 
 * FUTURE COMPATIBILITY:
 * - ERC-8004 (Decentralized Paymaster)
 * - x.402 (HTTP 402 Payment Required protocol)
 * 
 * ═══════════════════════════════════════════════════════════════════════════
 */

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";
import "@openzeppelin/contracts/security/Pausable.sol";

contract KubeTEEPayment is Ownable, ReentrancyGuard, Pausable {
    using SafeERC20 for IERC20;

    // ==========================================================================
    // CONSTANTS
    // ==========================================================================
    
    /// @notice Resellers pay 50% of retail price
    uint256 public constant WHOLESALE_DISCOUNT_BPS = 5000; // 50%
    
    /// @notice Basis points denominator
    uint256 public constant BPS_DENOMINATOR = 10000;
    
    /// @notice Minimum deposit amount
    uint256 public constant MIN_DEPOSIT = 1e18; // 1 token minimum

    // ==========================================================================
    // STATE
    // ==========================================================================
    
    /// @notice Payment token (wTAO or Alpha)
    IERC20 public immutable paymentToken;
    
    /// @notice KubeTEE Owner address (receives payments from resellers)
    address public kubeteeOwner;
    
    /// @notice Current epoch number
    uint256 public currentEpoch;
    
    /// @notice Blocks per epoch
    uint256 public blocksPerEpoch;
    
    /// @notice Last epoch settlement block
    uint256 public lastSettlementBlock;

    // ==========================================================================
    // RESELLER DATA
    // ==========================================================================
    
    struct Reseller {
        // Identity (NOT registered on Bittensor subnet)
        address wallet;           // EVM wallet address
        bytes32 hotkey;           // Bittensor hotkey (for Rancher account)
        bytes32 coldkey;          // Bittensor coldkey
        
        // Registration
        uint256 registeredAt;
        bool active;
        
        // Rancher integration
        string rancherProjectId;  // Rancher project/namespace ID
        
        // Deposits and balance
        uint256 depositBalance;   // Current available balance
        uint256 totalDeposited;   // Lifetime deposits
        uint256 totalSpent;       // Lifetime spending
        
        // Usage tracking (updated by validators)
        uint256 currentEpochUsage;
        uint256 lastSettledEpoch;
    }
    
    /// @notice Registered resellers (by wallet address)
    mapping(address => Reseller) public resellers;
    
    /// @notice Reseller wallet by hotkey (for lookup)
    mapping(bytes32 => address) public hotkeyToWallet;
    
    /// @notice List of all reseller addresses
    address[] public resellerList;

    // ==========================================================================
    // VALIDATOR DATA
    // ==========================================================================
    
    /// @notice Authorized validators
    mapping(address => bool) public authorizedValidators;
    
    /// @notice Validator count
    uint256 public validatorCount;
    
    /// @notice Required validator confirmations for settlement
    uint256 public requiredConfirmations;

    // ==========================================================================
    // EPOCH SETTLEMENT
    // ==========================================================================
    
    struct EpochUsageReport {
        address reseller;
        uint256 usageAmount;      // Amount to charge (50% of retail)
        uint256 tokensProcessed;
        uint256 gpuSecondsUsed;
    }
    
    struct EpochSettlement {
        uint256 epoch;
        uint256 totalUsage;
        uint256 confirmations;
        bool finalized;
        mapping(address => bool) validatorConfirmed;
        mapping(address => uint256) resellerUsage;
    }
    
    /// @notice Pending epoch settlements
    mapping(uint256 => EpochSettlement) public epochSettlements;

    // ==========================================================================
    // EVENTS
    // ==========================================================================
    
    event ResellerRegistered(
        address indexed wallet,
        bytes32 indexed hotkey,
        string rancherProjectId
    );
    event ResellerDeactivated(address indexed wallet);
    
    event Deposit(address indexed reseller, uint256 amount);
    event Withdrawal(address indexed reseller, uint256 amount);
    
    event UsageReported(
        uint256 indexed epoch,
        address indexed validator,
        address indexed reseller,
        uint256 amount
    );
    
    event EpochSettled(
        uint256 indexed epoch,
        uint256 totalTransferred,
        uint256 resellersCharged
    );
    
    event ValidatorAdded(address indexed validator);
    event ValidatorRemoved(address indexed validator);
    
    event KubeTEEOwnerUpdated(address indexed oldOwner, address indexed newOwner);

    // ==========================================================================
    // CONSTRUCTOR
    // ==========================================================================
    
    /**
     * @notice Initialize the payment contract
     * @param _paymentToken Address of payment token (wTAO/Alpha)
     * @param _kubeteeOwner Address that receives reseller payments
     * @param _blocksPerEpoch Number of blocks per epoch
     * @param _requiredConfirmations Number of validator confirmations needed
     */
    constructor(
        address _paymentToken,
        address _kubeteeOwner,
        uint256 _blocksPerEpoch,
        uint256 _requiredConfirmations
    ) Ownable(msg.sender) {
        require(_paymentToken != address(0), "Invalid token");
        require(_kubeteeOwner != address(0), "Invalid owner");
        require(_blocksPerEpoch > 0, "Invalid epoch length");
        
        paymentToken = IERC20(_paymentToken);
        kubeteeOwner = _kubeteeOwner;
        blocksPerEpoch = _blocksPerEpoch;
        requiredConfirmations = _requiredConfirmations;
        
        currentEpoch = 1;
        lastSettlementBlock = block.number;
    }

    // ==========================================================================
    // RESELLER FUNCTIONS
    // ==========================================================================
    
    /**
     * @notice Register as a reseller (called via KubeTEE CLI)
     * @param hotkey Bittensor hotkey (for Rancher account linking)
     * @param coldkey Bittensor coldkey
     * @param rancherProjectId Rancher project/namespace ID
     */
    function registerReseller(
        bytes32 hotkey,
        bytes32 coldkey,
        string calldata rancherProjectId
    ) external whenNotPaused {
        require(resellers[msg.sender].registeredAt == 0, "Already registered");
        require(hotkeyToWallet[hotkey] == address(0), "Hotkey already used");
        require(bytes(rancherProjectId).length > 0, "Invalid Rancher ID");
        
        resellers[msg.sender] = Reseller({
            wallet: msg.sender,
            hotkey: hotkey,
            coldkey: coldkey,
            registeredAt: block.timestamp,
            active: true,
            rancherProjectId: rancherProjectId,
            depositBalance: 0,
            totalDeposited: 0,
            totalSpent: 0,
            currentEpochUsage: 0,
            lastSettledEpoch: currentEpoch
        });
        
        hotkeyToWallet[hotkey] = msg.sender;
        resellerList.push(msg.sender);
        
        emit ResellerRegistered(msg.sender, hotkey, rancherProjectId);
    }
    
    /**
     * @notice Deposit tokens to reseller account
     * @param amount Amount to deposit
     */
    function deposit(uint256 amount) external nonReentrant whenNotPaused {
        require(resellers[msg.sender].active, "Not active reseller");
        require(amount >= MIN_DEPOSIT, "Below minimum deposit");
        
        paymentToken.safeTransferFrom(msg.sender, address(this), amount);
        
        resellers[msg.sender].depositBalance += amount;
        resellers[msg.sender].totalDeposited += amount;
        
        emit Deposit(msg.sender, amount);
    }
    
    /**
     * @notice Withdraw unused balance
     * @param amount Amount to withdraw
     */
    function withdraw(uint256 amount) external nonReentrant {
        Reseller storage reseller = resellers[msg.sender];
        require(reseller.active, "Not active reseller");
        require(reseller.depositBalance >= amount, "Insufficient balance");
        
        // Ensure current epoch usage is covered
        require(
            reseller.depositBalance - amount >= reseller.currentEpochUsage,
            "Must cover current epoch usage"
        );
        
        reseller.depositBalance -= amount;
        paymentToken.safeTransfer(msg.sender, amount);
        
        emit Withdrawal(msg.sender, amount);
    }
    
    /**
     * @notice Get reseller balance
     * @param wallet Reseller wallet address
     */
    function getResellerBalance(address wallet) external view returns (uint256) {
        return resellers[wallet].depositBalance;
    }
    
    /**
     * @notice Get reseller by hotkey
     * @param hotkey Bittensor hotkey
     */
    function getResellerByHotkey(bytes32 hotkey) external view returns (address) {
        return hotkeyToWallet[hotkey];
    }

    // ==========================================================================
    // VALIDATOR FUNCTIONS
    // ==========================================================================
    
    /**
     * @notice Report reseller usage for current epoch
     * @param reports Array of usage reports
     * 
     * Called by validators each epoch with usage data from Rancher/Prometheus.
     * Multiple validators must confirm for settlement to occur.
     */
    function reportEpochUsage(
        EpochUsageReport[] calldata reports
    ) external whenNotPaused {
        require(authorizedValidators[msg.sender], "Not authorized validator");
        
        EpochSettlement storage settlement = epochSettlements[currentEpoch];
        require(!settlement.validatorConfirmed[msg.sender], "Already reported");
        
        // Record usage for each reseller
        for (uint256 i = 0; i < reports.length; i++) {
            EpochUsageReport calldata report = reports[i];
            require(resellers[report.reseller].active, "Inactive reseller");
            
            // Update reseller's current epoch usage
            resellers[report.reseller].currentEpochUsage = report.usageAmount;
            
            // Update settlement data
            settlement.resellerUsage[report.reseller] = report.usageAmount;
            settlement.totalUsage += report.usageAmount;
            
            emit UsageReported(currentEpoch, msg.sender, report.reseller, report.usageAmount);
        }
        
        // Mark validator as confirmed
        settlement.validatorConfirmed[msg.sender] = true;
        settlement.confirmations++;
        settlement.epoch = currentEpoch;
        
        // Check if we have enough confirmations to settle
        if (settlement.confirmations >= requiredConfirmations && !settlement.finalized) {
            _settleEpoch(currentEpoch);
        }
    }
    
    /**
     * @notice Force settle epoch (owner only, for edge cases)
     * @param epoch Epoch to settle
     */
    function forceSettleEpoch(uint256 epoch) external onlyOwner {
        require(!epochSettlements[epoch].finalized, "Already finalized");
        _settleEpoch(epoch);
    }
    
    /**
     * @notice Internal epoch settlement
     * @param epoch Epoch to settle
     */
    function _settleEpoch(uint256 epoch) internal {
        EpochSettlement storage settlement = epochSettlements[epoch];
        require(!settlement.finalized, "Already finalized");
        
        uint256 totalTransferred = 0;
        uint256 resellersCharged = 0;
        
        // Process each reseller
        for (uint256 i = 0; i < resellerList.length; i++) {
            address resellerAddr = resellerList[i];
            Reseller storage reseller = resellers[resellerAddr];
            
            if (!reseller.active) continue;
            
            uint256 usage = settlement.resellerUsage[resellerAddr];
            if (usage == 0) continue;
            
            // Check if reseller has sufficient balance
            if (reseller.depositBalance >= usage) {
                // Deduct from reseller
                reseller.depositBalance -= usage;
                reseller.totalSpent += usage;
                reseller.currentEpochUsage = 0;
                reseller.lastSettledEpoch = epoch;
                
                totalTransferred += usage;
                resellersCharged++;
            } else {
                // Insufficient funds - deactivate reseller
                reseller.active = false;
                emit ResellerDeactivated(resellerAddr);
            }
        }
        
        // Transfer total to KubeTEE Owner
        if (totalTransferred > 0) {
            paymentToken.safeTransfer(kubeteeOwner, totalTransferred);
        }
        
        // Finalize settlement
        settlement.finalized = true;
        
        // Advance epoch
        currentEpoch++;
        lastSettlementBlock = block.number;
        
        emit EpochSettled(epoch, totalTransferred, resellersCharged);
    }
    
    /**
     * @notice Advance to next epoch (if blocks elapsed)
     */
    function advanceEpoch() external {
        require(
            block.number >= lastSettlementBlock + blocksPerEpoch,
            "Epoch not complete"
        );
        
        // If previous epoch not settled, settle it first
        if (!epochSettlements[currentEpoch].finalized) {
            // Auto-settle with whatever confirmations we have
            _settleEpoch(currentEpoch);
        }
    }

    // ==========================================================================
    // ADMIN FUNCTIONS
    // ==========================================================================
    
    /**
     * @notice Add authorized validator
     * @param validator Validator address
     */
    function addValidator(address validator) external onlyOwner {
        require(!authorizedValidators[validator], "Already authorized");
        authorizedValidators[validator] = true;
        validatorCount++;
        emit ValidatorAdded(validator);
    }
    
    /**
     * @notice Remove validator
     * @param validator Validator address
     */
    function removeValidator(address validator) external onlyOwner {
        require(authorizedValidators[validator], "Not authorized");
        authorizedValidators[validator] = false;
        validatorCount--;
        emit ValidatorRemoved(validator);
    }
    
    /**
     * @notice Update KubeTEE Owner address
     * @param newOwner New owner address
     */
    function setKubeTEEOwner(address newOwner) external onlyOwner {
        require(newOwner != address(0), "Invalid address");
        emit KubeTEEOwnerUpdated(kubeteeOwner, newOwner);
        kubeteeOwner = newOwner;
    }
    
    /**
     * @notice Update required confirmations
     * @param _required New requirement
     */
    function setRequiredConfirmations(uint256 _required) external onlyOwner {
        require(_required > 0 && _required <= validatorCount, "Invalid");
        requiredConfirmations = _required;
    }
    
    /**
     * @notice Pause contract
     */
    function pause() external onlyOwner {
        _pause();
    }
    
    /**
     * @notice Unpause contract
     */
    function unpause() external onlyOwner {
        _unpause();
    }
    
    /**
     * @notice Deactivate a reseller (admin)
     * @param wallet Reseller wallet
     */
    function deactivateReseller(address wallet) external onlyOwner {
        resellers[wallet].active = false;
        emit ResellerDeactivated(wallet);
    }

    // ==========================================================================
    // VIEW FUNCTIONS
    // ==========================================================================
    
    /**
     * @notice Get contract statistics
     */
    function getStatistics() external view returns (
        uint256 totalResellers,
        uint256 activeResellers,
        uint256 _currentEpoch,
        uint256 contractBalance,
        uint256 _validatorCount
    ) {
        uint256 active = 0;
        for (uint256 i = 0; i < resellerList.length; i++) {
            if (resellers[resellerList[i]].active) active++;
        }
        
        return (
            resellerList.length,
            active,
            currentEpoch,
            paymentToken.balanceOf(address(this)),
            validatorCount
        );
    }
    
    /**
     * @notice Get epoch settlement status
     * @param epoch Epoch number
     */
    function getEpochStatus(uint256 epoch) external view returns (
        uint256 totalUsage,
        uint256 confirmations,
        bool finalized
    ) {
        EpochSettlement storage settlement = epochSettlements[epoch];
        return (
            settlement.totalUsage,
            settlement.confirmations,
            settlement.finalized
        );
    }
    
    /**
     * @notice Get all reseller addresses
     */
    function getAllResellers() external view returns (address[] memory) {
        return resellerList;
    }
}

