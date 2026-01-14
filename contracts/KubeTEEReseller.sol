// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title KubeTEE Reseller Payment Contract
 * @author KubeTEE AI
 * @notice SIMPLIFIED on-chain payment system for Resellers on BASE
 * @dev Deployed on BASE L2 - USDC only for maximum simplicity
 * 
 * ═══════════════════════════════════════════════════════════════════════════
 *                      DESIGN PHILOSOPHY: SIMPLICITY
 * ═══════════════════════════════════════════════════════════════════════════
 * 
 * WHY USDC ONLY?
 * 1. Zero volatility risk for resellers
 * 2. Deep liquidity (no bootstrapping)
 * 3. x402 protocol native compatibility
 * 4. One-step CLI onboarding
 * 5. Enterprise-friendly stable pricing
 * 
 * ═══════════════════════════════════════════════════════════════════════════
 *                          CLI WORKFLOW
 * ═══════════════════════════════════════════════════════════════════════════
 * 
 * # 1. Register as reseller (one-time)
 * kubetee reseller register
 *   → Creates Rancher namespace
 *   → Registers on this contract
 * 
 * # 2. Deposit USDC (anytime)
 * kubetee reseller deposit 100
 *   → Approves USDC transfer
 *   → Deposits to contract
 * 
 * # 3. Check balance
 * kubetee reseller balance
 *   → Shows current USDC balance
 *   → Shows usage this epoch
 * 
 * # 4. Automatic deduction (per epoch)
 *   → Validators report usage
 *   → Contract deducts from balance
 *   → Transfers to KubeTEE Owner
 * 
 * ═══════════════════════════════════════════════════════════════════════════
 */

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/utils/ReentrancyGuard.sol";
import "@openzeppelin/contracts/utils/Pausable.sol";

contract KubeTEEReseller is Ownable, ReentrancyGuard, Pausable {
    using SafeERC20 for IERC20;

    // =========================================================================
    // CONSTANTS
    // =========================================================================
    
    /// @notice USDC on BASE (6 decimals)
    IERC20 public immutable usdc;
    
    /// @notice Minimum deposit: $10 USDC
    uint256 public constant MIN_DEPOSIT = 10 * 1e6;
    
    /// @notice Wholesale discount: 50% of retail
    uint256 public constant WHOLESALE_RATE_BPS = 5000;

    // =========================================================================
    // STATE
    // =========================================================================
    
    /// @notice KubeTEE Owner (receives payments)
    address public kubeteeOwner;
    
    /// @notice Current epoch (incremented each settlement)
    uint256 public currentEpoch;
    
    /// @notice Epoch duration in seconds (default: 1 hour)
    uint256 public epochDuration;
    
    /// @notice Last epoch settlement timestamp
    uint256 public lastSettlement;

    // =========================================================================
    // RESELLER DATA (Simplified!)
    // =========================================================================
    
    struct Reseller {
        // Identity
        address wallet;
        string rancherNamespace;    // e.g., "reseller-acme-corp"
        
        // Registration
        uint256 registeredAt;
        bool active;
        
        // Balances (all in USDC - 6 decimals)
        uint256 balance;            // Current available balance
        uint256 currentUsage;       // Usage this epoch (pending deduction)
        uint256 totalDeposited;     // Lifetime deposits
        uint256 totalSpent;         // Lifetime spending
        
        // Metadata
        string name;                // Business name
    }
    
    /// @notice Reseller data by wallet
    mapping(address => Reseller) public resellers;
    
    /// @notice All reseller addresses (for iteration)
    address[] public resellerList;
    
    /// @notice Rancher namespace to wallet mapping
    mapping(string => address) public namespaceToWallet;

    // =========================================================================
    // VALIDATOR DATA
    // =========================================================================
    
    /// @notice Authorized validators
    mapping(address => bool) public validators;
    uint256 public validatorCount;
    
    /// @notice Required confirmations for settlement
    uint256 public requiredConfirmations;
    
    /// @notice Epoch settlements
    struct EpochSettlement {
        uint256 totalUsage;
        uint256 confirmations;
        bool finalized;
        mapping(address => bool) confirmedBy;
    }
    mapping(uint256 => EpochSettlement) public settlements;

    // =========================================================================
    // EVENTS
    // =========================================================================
    
    event ResellerRegistered(address indexed wallet, string namespace, string name);
    event ResellerDeactivated(address indexed wallet);
    event Deposited(address indexed wallet, uint256 amount, uint256 newBalance);
    event Withdrawn(address indexed wallet, uint256 amount);
    event UsageReported(uint256 indexed epoch, address indexed validator, address indexed reseller, uint256 amount);
    event EpochSettled(uint256 indexed epoch, uint256 totalTransferred, uint256 resellersCharged);
    event ValidatorAdded(address indexed validator);
    event ValidatorRemoved(address indexed validator);

    // =========================================================================
    // CONSTRUCTOR
    // =========================================================================
    
    /**
     * @notice Deploy KubeTEE Reseller contract
     * @param _usdc USDC token address on BASE
     * @param _kubeteeOwner Address to receive payments
     * @param _epochDuration Seconds per epoch (default: 3600 = 1 hour)
     */
    constructor(
        address _usdc,
        address _kubeteeOwner,
        uint256 _epochDuration
    ) Ownable(msg.sender) {
        require(_usdc != address(0), "Invalid USDC");
        require(_kubeteeOwner != address(0), "Invalid owner");
        
        usdc = IERC20(_usdc);
        kubeteeOwner = _kubeteeOwner;
        epochDuration = _epochDuration > 0 ? _epochDuration : 3600;
        
        currentEpoch = 1;
        lastSettlement = block.timestamp;
        requiredConfirmations = 1; // Start with 1, increase as validators added
    }

    // =========================================================================
    // RESELLER FUNCTIONS (Used by KubeTEE CLI)
    // =========================================================================
    
    /**
     * @notice Register as a reseller
     * @param namespace Rancher namespace (e.g., "reseller-acme")
     * @param name Business name
     * 
     * CLI: kubetee reseller register --namespace acme --name "ACME Corp"
     */
    function register(
        string calldata namespace,
        string calldata name
    ) external whenNotPaused {
        require(resellers[msg.sender].registeredAt == 0, "Already registered");
        require(bytes(namespace).length > 0, "Empty namespace");
        require(namespaceToWallet[namespace] == address(0), "Namespace taken");
        
        resellers[msg.sender] = Reseller({
            wallet: msg.sender,
            rancherNamespace: namespace,
            registeredAt: block.timestamp,
            active: true,
            balance: 0,
            currentUsage: 0,
            totalDeposited: 0,
            totalSpent: 0,
            name: name
        });
        
        namespaceToWallet[namespace] = msg.sender;
        resellerList.push(msg.sender);
        
        emit ResellerRegistered(msg.sender, namespace, name);
    }
    
    /**
     * @notice Deposit USDC to reseller account
     * @param amount Amount in USDC (6 decimals, e.g., 100000000 = $100)
     * 
     * CLI: kubetee reseller deposit 100
     * 
     * FLOW:
     * 1. CLI calls USDC.approve(this contract, amount)
     * 2. CLI calls this.deposit(amount)
     */
    function deposit(uint256 amount) external nonReentrant whenNotPaused {
        require(resellers[msg.sender].active, "Not active reseller");
        require(amount >= MIN_DEPOSIT, "Below $10 minimum");
        
        // Transfer USDC from reseller to this contract
        usdc.safeTransferFrom(msg.sender, address(this), amount);
        
        // Update balance
        resellers[msg.sender].balance += amount;
        resellers[msg.sender].totalDeposited += amount;
        
        emit Deposited(msg.sender, amount, resellers[msg.sender].balance);
    }
    
    /**
     * @notice Withdraw unused USDC balance
     * @param amount Amount to withdraw
     * 
     * CLI: kubetee reseller withdraw 50
     */
    function withdraw(uint256 amount) external nonReentrant {
        Reseller storage r = resellers[msg.sender];
        require(r.active, "Not active");
        
        // Must cover current epoch usage
        uint256 available = r.balance > r.currentUsage 
            ? r.balance - r.currentUsage 
            : 0;
        require(amount <= available, "Insufficient available balance");
        
        r.balance -= amount;
        usdc.safeTransfer(msg.sender, amount);
        
        emit Withdrawn(msg.sender, amount);
    }
    
    /**
     * @notice Get reseller info (for CLI display)
     * @param wallet Reseller wallet address
     */
    function getResellerInfo(address wallet) external view returns (
        string memory namespace,
        string memory name,
        bool active,
        uint256 balance,
        uint256 currentUsage,
        uint256 available,
        uint256 totalSpent
    ) {
        Reseller storage r = resellers[wallet];
        return (
            r.rancherNamespace,
            r.name,
            r.active,
            r.balance,
            r.currentUsage,
            r.balance > r.currentUsage ? r.balance - r.currentUsage : 0,
            r.totalSpent
        );
    }

    // =========================================================================
    // VALIDATOR FUNCTIONS (Called by KubeTEE validators)
    // =========================================================================
    
    /**
     * @notice Report reseller usage for current epoch
     * @param resellerWallets Array of reseller addresses
     * @param usageAmounts Array of usage amounts (USDC, 6 decimals)
     * 
     * Called by validators at epoch end with usage from Prometheus/Rancher.
     * Multiple validators must confirm for settlement.
     */
    function reportUsage(
        address[] calldata resellerWallets,
        uint256[] calldata usageAmounts
    ) external whenNotPaused {
        require(validators[msg.sender], "Not a validator");
        require(resellerWallets.length == usageAmounts.length, "Length mismatch");
        
        EpochSettlement storage s = settlements[currentEpoch];
        require(!s.confirmedBy[msg.sender], "Already reported");
        
        // Record usage for each reseller
        for (uint256 i = 0; i < resellerWallets.length; i++) {
            address wallet = resellerWallets[i];
            uint256 usage = usageAmounts[i];
            
            if (resellers[wallet].active && usage > 0) {
                resellers[wallet].currentUsage = usage;
                s.totalUsage += usage;
                
                emit UsageReported(currentEpoch, msg.sender, wallet, usage);
            }
        }
        
        // Mark validator as confirmed
        s.confirmedBy[msg.sender] = true;
        s.confirmations++;
        
        // Auto-settle if enough confirmations
        if (s.confirmations >= requiredConfirmations && !s.finalized) {
            _settleEpoch();
        }
    }
    
    /**
     * @notice Settle current epoch
     * 
     * Called automatically when confirmations reached, or manually by owner.
     */
    function settleEpoch() external {
        require(
            msg.sender == owner() || 
            block.timestamp >= lastSettlement + epochDuration,
            "Epoch not complete"
        );
        _settleEpoch();
    }
    
    function _settleEpoch() internal {
        EpochSettlement storage s = settlements[currentEpoch];
        require(!s.finalized, "Already settled");
        
        uint256 totalTransferred = 0;
        uint256 resellersCharged = 0;
        
        // Process each reseller
        for (uint256 i = 0; i < resellerList.length; i++) {
            address wallet = resellerList[i];
            Reseller storage r = resellers[wallet];
            
            if (!r.active || r.currentUsage == 0) continue;
            
            uint256 usage = r.currentUsage;
            
            if (r.balance >= usage) {
                // Deduct usage
                r.balance -= usage;
                r.totalSpent += usage;
                r.currentUsage = 0;
                
                totalTransferred += usage;
                resellersCharged++;
            } else {
                // Insufficient balance - deactivate
                r.active = false;
                emit ResellerDeactivated(wallet);
            }
        }
        
        // Transfer total to KubeTEE Owner
        if (totalTransferred > 0) {
            usdc.safeTransfer(kubeteeOwner, totalTransferred);
        }
        
        // Finalize
        s.finalized = true;
        currentEpoch++;
        lastSettlement = block.timestamp;
        
        emit EpochSettled(currentEpoch - 1, totalTransferred, resellersCharged);
    }

    // =========================================================================
    // ADMIN FUNCTIONS
    // =========================================================================
    
    function addValidator(address validator) external onlyOwner {
        require(!validators[validator], "Already validator");
        validators[validator] = true;
        validatorCount++;
        
        // Auto-adjust required confirmations
        if (requiredConfirmations < validatorCount / 2 + 1) {
            requiredConfirmations = validatorCount / 2 + 1;
        }
        
        emit ValidatorAdded(validator);
    }
    
    function removeValidator(address validator) external onlyOwner {
        require(validators[validator], "Not validator");
        validators[validator] = false;
        validatorCount--;
        
        // Adjust confirmations
        if (validatorCount > 0 && requiredConfirmations > validatorCount / 2 + 1) {
            requiredConfirmations = validatorCount / 2 + 1;
        }
        
        emit ValidatorRemoved(validator);
    }
    
    function setKubeTEEOwner(address newOwner) external onlyOwner {
        require(newOwner != address(0), "Invalid");
        kubeteeOwner = newOwner;
    }
    
    function setRequiredConfirmations(uint256 _required) external onlyOwner {
        require(_required > 0 && _required <= validatorCount, "Invalid");
        requiredConfirmations = _required;
    }
    
    function pause() external onlyOwner { _pause(); }
    function unpause() external onlyOwner { _unpause(); }
    
    function deactivateReseller(address wallet) external onlyOwner {
        resellers[wallet].active = false;
        emit ResellerDeactivated(wallet);
    }

    // =========================================================================
    // VIEW FUNCTIONS
    // =========================================================================
    
    function getStats() external view returns (
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
            usdc.balanceOf(address(this)),
            validatorCount
        );
    }
    
    function getAllResellers() external view returns (address[] memory) {
        return resellerList;
    }
    
    function isReseller(address wallet) external view returns (bool) {
        return resellers[wallet].registeredAt > 0 && resellers[wallet].active;
    }
}

