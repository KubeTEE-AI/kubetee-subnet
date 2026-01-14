// SPDX-License-Identifier: MIT
pragma solidity ^0.8.20;

/**
 * @title KubeTEE AI Escrow Contract
 * @author KubeTEE AI
 * @notice Trustless escrow for reseller deposits and miner payments
 * @dev Deployed on Bittensor EVM for trustless wholesale transactions
 * 
 * ═══════════════════════════════════════════════════════════════════════════
 *                              KEY CONCEPT
 * ═══════════════════════════════════════════════════════════════════════════
 * 
 * RESELLERS are PURE DISTRIBUTORS - they DON'T have infrastructure!
 * - They deposit Alpha at 50% of retail price
 * - They use the subnet's MINER infrastructure
 * - They charge their customers whatever they want
 * 
 * MINERS provide the infrastructure that resellers use!
 * - They receive 50% of what resellers pay
 * - They don't need subnet registration for wholesale payments
 * 
 * ═══════════════════════════════════════════════════════════════════════════
 *                              PAYMENT FLOW
 * ═══════════════════════════════════════════════════════════════════════════
 * 
 * 1. Reseller deposits wTAO/Alpha to this contract (50% of retail price)
 * 2. Reseller uses API → requests served by MINER infrastructure
 * 3. Validator submits usage attestation (resources consumed)
 * 4. Contract automatically releases payments:
 *    - 50% to the MINER who provided infrastructure
 *    - 50% to the TREASURY for subnet operations
 * 
 * REFERENCE:
 * Bittensor EVM: https://docs.learnbittensor.org/evm-tutorials/subnet-precompile
 */

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";
import "@openzeppelin/contracts/access/Ownable.sol";
import "@openzeppelin/contracts/security/ReentrancyGuard.sol";

contract KubeTEEEscrow is Ownable, ReentrancyGuard {
    using SafeERC20 for IERC20;

    // ==========================================================================
    // CONSTANTS
    // ==========================================================================
    
    /// @notice Miner receives 50% of wholesale price
    uint256 public constant MINER_SHARE_BPS = 5000; // 50% in basis points
    
    /// @notice Treasury receives 50% of wholesale price
    uint256 public constant TREASURY_SHARE_BPS = 5000; // 50% in basis points
    
    /// @notice Basis points denominator
    uint256 public constant BPS_DENOMINATOR = 10000;

    // ==========================================================================
    // STATE
    // ==========================================================================
    
    /// @notice The token used for payments (wTAO or Alpha)
    IERC20 public paymentToken;
    
    /// @notice Treasury address for subnet operations
    address public treasury;
    
    /// @notice Reseller credit balances
    mapping(address => uint256) public resellerBalances;
    
    /// @notice Miner pending payments
    mapping(address => uint256) public minerPendingPayments;
    
    /// @notice Authorized validators who can submit usage attestations
    mapping(address => bool) public authorizedValidators;
    
    /// @notice Registered resellers
    mapping(address => bool) public registeredResellers;
    
    /// @notice Registered miners
    mapping(address => bool) public registeredMiners;
    
    /// @notice Processed attestation hashes (prevent replay)
    mapping(bytes32 => bool) public processedAttestations;
    
    /// @notice Total deposits received
    uint256 public totalDeposits;
    
    /// @notice Total payments to miners
    uint256 public totalMinerPayments;
    
    /// @notice Total treasury accumulation
    uint256 public totalTreasuryPayments;

    // ==========================================================================
    // EVENTS
    // ==========================================================================
    
    event ResellerRegistered(address indexed reseller);
    event MinerRegistered(address indexed miner);
    event ValidatorAuthorized(address indexed validator);
    event ValidatorRevoked(address indexed validator);
    
    event Deposit(address indexed reseller, uint256 amount);
    event ServiceProcessed(
        bytes32 indexed attestationHash,
        address indexed reseller,
        address indexed miner,
        uint256 totalCost,
        uint256 minerPayment,
        uint256 treasuryShare
    );
    event MinerWithdrawal(address indexed miner, uint256 amount);
    event ResellerWithdrawal(address indexed reseller, uint256 amount);

    // ==========================================================================
    // CONSTRUCTOR
    // ==========================================================================
    
    /**
     * @notice Initialize the escrow contract
     * @param _paymentToken Address of the payment token (wTAO/Alpha)
     * @param _treasury Treasury address for subnet operations
     */
    constructor(
        address _paymentToken,
        address _treasury
    ) Ownable(msg.sender) {
        require(_paymentToken != address(0), "Invalid token address");
        require(_treasury != address(0), "Invalid treasury address");
        
        paymentToken = IERC20(_paymentToken);
        treasury = _treasury;
    }

    // ==========================================================================
    // ADMIN FUNCTIONS
    // ==========================================================================
    
    /**
     * @notice Register a reseller
     * @param reseller Address of the reseller
     */
    function registerReseller(address reseller) external onlyOwner {
        require(reseller != address(0), "Invalid address");
        registeredResellers[reseller] = true;
        emit ResellerRegistered(reseller);
    }
    
    /**
     * @notice Register a miner
     * @param miner Address of the miner
     */
    function registerMiner(address miner) external onlyOwner {
        require(miner != address(0), "Invalid address");
        registeredMiners[miner] = true;
        emit MinerRegistered(miner);
    }
    
    /**
     * @notice Authorize a validator to submit attestations
     * @param validator Address of the validator
     */
    function authorizeValidator(address validator) external onlyOwner {
        require(validator != address(0), "Invalid address");
        authorizedValidators[validator] = true;
        emit ValidatorAuthorized(validator);
    }
    
    /**
     * @notice Revoke validator authorization
     * @param validator Address of the validator
     */
    function revokeValidator(address validator) external onlyOwner {
        authorizedValidators[validator] = false;
        emit ValidatorRevoked(validator);
    }
    
    /**
     * @notice Update treasury address
     * @param _treasury New treasury address
     */
    function setTreasury(address _treasury) external onlyOwner {
        require(_treasury != address(0), "Invalid address");
        treasury = _treasury;
    }

    // ==========================================================================
    // RESELLER FUNCTIONS
    // ==========================================================================
    
    /**
     * @notice Deposit tokens to get credits at wholesale price
     * @param amount Amount of tokens to deposit
     * 
     * NOTE: Reseller pays 50% of retail price. The amount deposited
     * equals their credit balance (wholesale pricing already applied off-chain).
     */
    function deposit(uint256 amount) external nonReentrant {
        require(registeredResellers[msg.sender], "Not a registered reseller");
        require(amount > 0, "Amount must be > 0");
        
        paymentToken.safeTransferFrom(msg.sender, address(this), amount);
        
        resellerBalances[msg.sender] += amount;
        totalDeposits += amount;
        
        emit Deposit(msg.sender, amount);
    }
    
    /**
     * @notice Withdraw unused credits
     * @param amount Amount to withdraw
     */
    function withdrawCredits(uint256 amount) external nonReentrant {
        require(resellerBalances[msg.sender] >= amount, "Insufficient balance");
        
        resellerBalances[msg.sender] -= amount;
        paymentToken.safeTransfer(msg.sender, amount);
        
        emit ResellerWithdrawal(msg.sender, amount);
    }

    // ==========================================================================
    // VALIDATOR FUNCTIONS
    // ==========================================================================
    
    /**
     * @notice Submit a service usage attestation
     * @param reseller Address of the reseller
     * @param miner Address of the miner who served the request
     * @param totalCost Total wholesale cost of the service
     * @param requestId Unique request identifier (for deduplication)
     * @param signature Validator's signature (for verification)
     * 
     * Flow:
     * 1. Validator submits attestation after service is completed
     * 2. Contract verifies validator is authorized
     * 3. Contract verifies attestation hasn't been processed
     * 4. Contract deducts from reseller balance
     * 5. Contract credits 50% to miner, 50% to treasury
     */
    function submitServiceAttestation(
        address reseller,
        address miner,
        uint256 totalCost,
        bytes32 requestId,
        bytes calldata signature
    ) external nonReentrant {
        require(authorizedValidators[msg.sender], "Not authorized validator");
        require(registeredResellers[reseller], "Unknown reseller");
        require(registeredMiners[miner], "Unknown miner");
        require(resellerBalances[reseller] >= totalCost, "Insufficient reseller balance");
        
        // Create attestation hash for deduplication
        bytes32 attestationHash = keccak256(
            abi.encodePacked(reseller, miner, totalCost, requestId)
        );
        require(!processedAttestations[attestationHash], "Already processed");
        
        // TODO: Verify signature using ED25519 precompile
        // See: https://docs.learnbittensor.org/evm-tutorials/ed25519-verify-precompile
        
        // Mark as processed
        processedAttestations[attestationHash] = true;
        
        // Calculate shares
        uint256 minerPayment = (totalCost * MINER_SHARE_BPS) / BPS_DENOMINATOR;
        uint256 treasuryShare = totalCost - minerPayment;
        
        // Update balances
        resellerBalances[reseller] -= totalCost;
        minerPendingPayments[miner] += minerPayment;
        
        // Transfer treasury share immediately
        paymentToken.safeTransfer(treasury, treasuryShare);
        totalTreasuryPayments += treasuryShare;
        
        emit ServiceProcessed(
            attestationHash,
            reseller,
            miner,
            totalCost,
            minerPayment,
            treasuryShare
        );
    }

    // ==========================================================================
    // MINER FUNCTIONS
    // ==========================================================================
    
    /**
     * @notice Withdraw pending miner payments
     */
    function withdrawMinerPayments() external nonReentrant {
        uint256 amount = minerPendingPayments[msg.sender];
        require(amount > 0, "No pending payments");
        
        minerPendingPayments[msg.sender] = 0;
        totalMinerPayments += amount;
        
        paymentToken.safeTransfer(msg.sender, amount);
        
        emit MinerWithdrawal(msg.sender, amount);
    }

    // ==========================================================================
    // VIEW FUNCTIONS
    // ==========================================================================
    
    /**
     * @notice Get reseller credit balance
     * @param reseller Address of the reseller
     */
    function getResellerBalance(address reseller) external view returns (uint256) {
        return resellerBalances[reseller];
    }
    
    /**
     * @notice Get miner pending payments
     * @param miner Address of the miner
     */
    function getMinerPending(address miner) external view returns (uint256) {
        return minerPendingPayments[miner];
    }
    
    /**
     * @notice Get contract statistics
     */
    function getStatistics() external view returns (
        uint256 _totalDeposits,
        uint256 _totalMinerPayments,
        uint256 _totalTreasuryPayments,
        uint256 _contractBalance
    ) {
        return (
            totalDeposits,
            totalMinerPayments,
            totalTreasuryPayments,
            paymentToken.balanceOf(address(this))
        );
    }
}

