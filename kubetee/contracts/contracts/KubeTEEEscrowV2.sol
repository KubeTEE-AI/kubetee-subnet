// SPDX-License-Identifier: MIT
pragma solidity ^0.8.22;

import "@openzeppelin/contracts-upgradeable/access/OwnableUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/proxy/utils/Initializable.sol";
import "@openzeppelin/contracts-upgradeable/proxy/utils/UUPSUpgradeable.sol";
import "@openzeppelin/contracts-upgradeable/utils/ReentrancyGuardUpgradeable.sol";
import "@openzeppelin/contracts/token/ERC20/IERC20.sol";
import "@openzeppelin/contracts/token/ERC20/utils/SafeERC20.sol";

/**
 * @title KubeTEEEscrowV2
 * @notice Trustless escrow for reseller deposits and miner payments
 * @dev Upgradeable (UUPS pattern), uses Admin/Operator access control model
 * 
 * Access Control:
 * - Admin (owner): Full rights - add/remove operators, register miners/resellers, configure
 * - Operator: Can submit service attestations
 * 
 * Key Concept:
 * - RESELLERS are PURE DISTRIBUTORS - they DON'T have infrastructure
 * - MINERS provide the infrastructure that resellers use
 * - Payment split: 50% to miner, 50% to treasury
 */
contract KubeTEEEscrowV2 is
    Initializable,
    OwnableUpgradeable,
    UUPSUpgradeable,
    ReentrancyGuardUpgradeable
{
    using SafeERC20 for IERC20;

    // =========================================================================
    // CONSTANTS & STATE
    // =========================================================================
    
    /// @notice Miner receives 50% of wholesale price
    uint256 public constant MINER_SHARE_BPS = 5000;
    
    /// @notice Treasury receives 50% of wholesale price
    uint256 public constant TREASURY_SHARE_BPS = 5000;
    
    /// @notice Basis points denominator
    uint256 public constant BPS_DENOMINATOR = 10000;
    
    /// @notice The token used for payments (wTAO or Alpha)
    IERC20 public paymentToken;
    
    /// @notice Treasury address for subnet operations
    address public treasury;
    
    /// @notice Operator whitelist
    mapping(address => bool) public isOperator;
    
    /// @notice Reseller credit balances
    mapping(address => uint256) public resellerBalances;
    
    /// @notice Miner pending payments
    mapping(address => uint256) public minerPendingPayments;
    
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

    // =========================================================================
    // EVENTS
    // =========================================================================
    
    event ResellerRegistered(address indexed reseller);
    event ResellerUnregistered(address indexed reseller);
    event MinerRegistered(address indexed miner);
    event MinerUnregistered(address indexed miner);
    event OperatorAdded(address indexed operator);
    event OperatorRemoved(address indexed operator);
    
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
    event TreasuryUpdated(address indexed newTreasury);

    // =========================================================================
    // ERRORS
    // =========================================================================
    
    error OnlyOperator();
    error InvalidAddress();
    error NotRegisteredReseller();
    error NotRegisteredMiner();
    error AlreadyRegistered();
    error AlreadyOperator();
    error NotOperator();
    error InsufficientBalance();
    error AlreadyProcessed();
    error AmountMustBePositive();
    error NoPendingPayments();

    // =========================================================================
    // MODIFIERS
    // =========================================================================
    
    modifier onlyOperator() {
        if (!isOperator[msg.sender]) revert OnlyOperator();
        _;
    }

    // =========================================================================
    // CONSTRUCTOR & INITIALIZER
    // =========================================================================
    
    /// @custom:oz-upgrades-unsafe-allow constructor
    constructor() {
        _disableInitializers();
    }
    
    /**
     * @notice Initialize the escrow contract
     * @param _paymentToken Address of the payment token (wTAO/Alpha)
     * @param _treasury Treasury address for subnet operations
     */
    function initialize(
        address _paymentToken,
        address _treasury
    ) public initializer {
        if (_paymentToken == address(0) || _treasury == address(0)) revert InvalidAddress();
        
        __Ownable_init(msg.sender);
        __UUPSUpgradeable_init();
        __ReentrancyGuard_init();
        
        paymentToken = IERC20(_paymentToken);
        treasury = _treasury;
    }
    
    function _authorizeUpgrade(address) internal override onlyOwner {}

    // =========================================================================
    // ADMIN FUNCTIONS
    // =========================================================================
    
    /**
     * @notice Register a reseller
     * @param reseller Address of the reseller
     */
    function registerReseller(address reseller) external onlyOwner {
        if (reseller == address(0)) revert InvalidAddress();
        if (registeredResellers[reseller]) revert AlreadyRegistered();
        registeredResellers[reseller] = true;
        emit ResellerRegistered(reseller);
    }
    
    /**
     * @notice Unregister a reseller
     * @param reseller Address of the reseller
     */
    function unregisterReseller(address reseller) external onlyOwner {
        if (!registeredResellers[reseller]) revert NotRegisteredReseller();
        registeredResellers[reseller] = false;
        emit ResellerUnregistered(reseller);
    }
    
    /**
     * @notice Register a miner
     * @param miner Address of the miner
     */
    function registerMiner(address miner) external onlyOwner {
        if (miner == address(0)) revert InvalidAddress();
        if (registeredMiners[miner]) revert AlreadyRegistered();
        registeredMiners[miner] = true;
        emit MinerRegistered(miner);
    }
    
    /**
     * @notice Unregister a miner
     * @param miner Address of the miner
     */
    function unregisterMiner(address miner) external onlyOwner {
        if (!registeredMiners[miner]) revert NotRegisteredMiner();
        registeredMiners[miner] = false;
        emit MinerUnregistered(miner);
    }
    
    /**
     * @notice Add an operator
     * @param operator Address of the operator
     */
    function addOperator(address operator) external onlyOwner {
        if (operator == address(0)) revert InvalidAddress();
        if (isOperator[operator]) revert AlreadyOperator();
        isOperator[operator] = true;
        emit OperatorAdded(operator);
    }
    
    /**
     * @notice Remove an operator
     * @param operator Address of the operator
     */
    function removeOperator(address operator) external onlyOwner {
        if (!isOperator[operator]) revert NotOperator();
        isOperator[operator] = false;
        emit OperatorRemoved(operator);
    }
    
    /**
     * @notice Update treasury address
     * @param _treasury New treasury address
     */
    function setTreasury(address _treasury) external onlyOwner {
        if (_treasury == address(0)) revert InvalidAddress();
        treasury = _treasury;
        emit TreasuryUpdated(_treasury);
    }
    
    /**
     * @notice Update payment token (for migrations)
     * @param _paymentToken New payment token address
     */
    function setPaymentToken(address _paymentToken) external onlyOwner {
        if (_paymentToken == address(0)) revert InvalidAddress();
        paymentToken = IERC20(_paymentToken);
    }

    // =========================================================================
    // RESELLER FUNCTIONS
    // =========================================================================
    
    /**
     * @notice Deposit tokens to get credits at wholesale price
     * @param amount Amount of tokens to deposit
     */
    function deposit(uint256 amount) external nonReentrant {
        if (!registeredResellers[msg.sender]) revert NotRegisteredReseller();
        if (amount == 0) revert AmountMustBePositive();
        
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
        if (resellerBalances[msg.sender] < amount) revert InsufficientBalance();
        
        resellerBalances[msg.sender] -= amount;
        paymentToken.safeTransfer(msg.sender, amount);
        
        emit ResellerWithdrawal(msg.sender, amount);
    }

    // =========================================================================
    // OPERATOR FUNCTIONS
    // =========================================================================
    
    /**
     * @notice Submit a service usage attestation
     * @param reseller Address of the reseller
     * @param miner Address of the miner who served the request
     * @param totalCost Total wholesale cost of the service
     * @param requestId Unique request identifier (for deduplication)
     * 
     * Flow:
     * 1. Operator submits attestation after service is completed
     * 2. Contract verifies attestation hasn't been processed
     * 3. Contract deducts from reseller balance
     * 4. Contract credits 50% to miner, 50% to treasury
     */
    function submitServiceAttestation(
        address reseller,
        address miner,
        uint256 totalCost,
        bytes32 requestId
    ) external onlyOperator nonReentrant {
        if (!registeredResellers[reseller]) revert NotRegisteredReseller();
        if (!registeredMiners[miner]) revert NotRegisteredMiner();
        if (resellerBalances[reseller] < totalCost) revert InsufficientBalance();
        
        // Create attestation hash for deduplication
        bytes32 attestationHash = keccak256(
            abi.encodePacked(reseller, miner, totalCost, requestId)
        );
        if (processedAttestations[attestationHash]) revert AlreadyProcessed();
        
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
    
    /**
     * @notice Submit multiple service attestations in batch
     * @param resellers Array of reseller addresses
     * @param miners Array of miner addresses
     * @param costs Array of costs
     * @param requestIds Array of request IDs
     */
    function submitBatchAttestations(
        address[] calldata resellers,
        address[] calldata miners,
        uint256[] calldata costs,
        bytes32[] calldata requestIds
    ) external onlyOperator nonReentrant {
        require(
            resellers.length == miners.length &&
            miners.length == costs.length &&
            costs.length == requestIds.length,
            "Length mismatch"
        );
        
        for (uint256 i = 0; i < resellers.length; i++) {
            _processAttestation(resellers[i], miners[i], costs[i], requestIds[i]);
        }
    }
    
    function _processAttestation(
        address reseller,
        address miner,
        uint256 totalCost,
        bytes32 requestId
    ) internal {
        if (!registeredResellers[reseller] || !registeredMiners[miner]) return;
        if (resellerBalances[reseller] < totalCost) return;
        
        bytes32 attestationHash = keccak256(
            abi.encodePacked(reseller, miner, totalCost, requestId)
        );
        if (processedAttestations[attestationHash]) return;
        
        processedAttestations[attestationHash] = true;
        
        uint256 minerPayment = (totalCost * MINER_SHARE_BPS) / BPS_DENOMINATOR;
        uint256 treasuryShare = totalCost - minerPayment;
        
        resellerBalances[reseller] -= totalCost;
        minerPendingPayments[miner] += minerPayment;
        
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

    // =========================================================================
    // MINER FUNCTIONS
    // =========================================================================
    
    /**
     * @notice Withdraw pending miner payments
     */
    function withdrawMinerPayments() external nonReentrant {
        uint256 amount = minerPendingPayments[msg.sender];
        if (amount == 0) revert NoPendingPayments();
        
        minerPendingPayments[msg.sender] = 0;
        totalMinerPayments += amount;
        
        paymentToken.safeTransfer(msg.sender, amount);
        
        emit MinerWithdrawal(msg.sender, amount);
    }

    // =========================================================================
    // VIEW FUNCTIONS
    // =========================================================================
    
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
     * @notice Check if attestation has been processed
     * @param reseller Reseller address
     * @param miner Miner address
     * @param totalCost Cost
     * @param requestId Request ID
     */
    function isAttestationProcessed(
        address reseller,
        address miner,
        uint256 totalCost,
        bytes32 requestId
    ) external view returns (bool) {
        bytes32 attestationHash = keccak256(
            abi.encodePacked(reseller, miner, totalCost, requestId)
        );
        return processedAttestations[attestationHash];
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
    
    /**
     * @notice Get contract configuration
     */
    function getConfig() external view returns (
        address paymentTokenAddress,
        address treasuryAddress,
        uint256 minerShareBps,
        uint256 treasuryShareBps
    ) {
        return (
            address(paymentToken),
            treasury,
            MINER_SHARE_BPS,
            TREASURY_SHARE_BPS
        );
    }
}
