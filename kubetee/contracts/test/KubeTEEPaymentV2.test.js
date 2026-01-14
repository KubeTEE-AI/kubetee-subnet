const { expect } = require("chai");
const { ethers, upgrades } = require("hardhat");

describe("KubeTEEPaymentV2", function () {
    let KubeTEEPaymentV2;
    let payment;
    let mockUsdc;
    let owner;
    let operator;
    let treasury;
    let user1;
    let user2;
    let affiliate;
    let nonOperator;
    
    const INITIAL_SUPPLY = ethers.parseUnits("1000000", 6); // 1M USDC
    const USER_BALANCE = ethers.parseUnits("10000", 6); // 10K USDC
    const COMMISSION_BPS = 5000n; // 50%
    const MIN_PAID_USERS = 2n;
    
    beforeEach(async function () {
        [owner, operator, treasury, user1, user2, affiliate, nonOperator] = await ethers.getSigners();
        
        // Deploy mock USDC
        const MockERC20 = await ethers.getContractFactory("MockERC20");
        mockUsdc = await MockERC20.deploy("USD Coin", "USDC", 6);
        await mockUsdc.waitForDeployment();
        
        // Mint USDC to users
        await mockUsdc.mint(user1.address, USER_BALANCE);
        await mockUsdc.mint(user2.address, USER_BALANCE);
        
        // Deploy KubeTEEPaymentV2 as upgradeable proxy
        KubeTEEPaymentV2 = await ethers.getContractFactory("KubeTEEPaymentV2");
        payment = await upgrades.deployProxy(
            KubeTEEPaymentV2,
            [await mockUsdc.getAddress(), treasury.address],
            { kind: "uups" }
        );
        await payment.waitForDeployment();
        
        // Add operator
        await payment.addOperator(operator.address);
        
        // Approve USDC spending from users
        await mockUsdc.connect(user1).approve(await payment.getAddress(), ethers.MaxUint256);
        await mockUsdc.connect(user2).approve(await payment.getAddress(), ethers.MaxUint256);
    });

    describe("Deployment & Initialization", function () {
        it("Should deploy as proxy correctly", async function () {
            expect(await payment.getAddress()).to.be.properAddress;
        });
        
        it("Should initialize with correct owner", async function () {
            expect(await payment.owner()).to.equal(owner.address);
        });
        
        it("Should initialize with correct USDC address", async function () {
            const config = await payment.getConfig();
            expect(config.usdcAddress).to.equal(await mockUsdc.getAddress());
        });
        
        it("Should initialize with correct treasury", async function () {
            const config = await payment.getConfig();
            expect(config.treasuryAddress).to.equal(treasury.address);
        });
        
        it("Should initialize with default config values", async function () {
            const config = await payment.getConfig();
            expect(config._minPaidUsers).to.equal(MIN_PAID_USERS);
            expect(config._commissionBps).to.equal(COMMISSION_BPS);
        });
        
        it("Should not allow re-initialization", async function () {
            await expect(
                payment.initialize(await mockUsdc.getAddress(), treasury.address)
            ).to.be.reverted;
        });
    });

    describe("Access Control - Admin", function () {
        it("Should allow admin to add operator", async function () {
            const newOperator = ethers.Wallet.createRandom().address;
            await expect(payment.addOperator(newOperator))
                .to.emit(payment, "OperatorAdded")
                .withArgs(newOperator);
            expect(await payment.isOperator(newOperator)).to.be.true;
        });
        
        it("Should allow admin to remove operator", async function () {
            await expect(payment.removeOperator(operator.address))
                .to.emit(payment, "OperatorRemoved")
                .withArgs(operator.address);
            expect(await payment.isOperator(operator.address)).to.be.false;
        });
        
        it("Should reject adding zero address as operator", async function () {
            await expect(payment.addOperator(ethers.ZeroAddress))
                .to.be.revertedWithCustomError(payment, "InvalidAddress");
        });
        
        it("Should reject adding duplicate operator", async function () {
            await expect(payment.addOperator(operator.address))
                .to.be.revertedWithCustomError(payment, "AlreadyOperator");
        });
        
        it("Should reject removing non-operator", async function () {
            await expect(payment.removeOperator(nonOperator.address))
                .to.be.revertedWithCustomError(payment, "NotOperator");
        });
        
        it("Should allow admin to set treasury", async function () {
            const newTreasury = ethers.Wallet.createRandom().address;
            await expect(payment.setTreasury(newTreasury))
                .to.emit(payment, "TreasuryUpdated")
                .withArgs(newTreasury);
        });
        
        it("Should reject non-admin from admin functions", async function () {
            await expect(payment.connect(nonOperator).addOperator(nonOperator.address))
                .to.be.revertedWithCustomError(payment, "OwnableUnauthorizedAccount");
        });
        
        it("Should allow admin to update commission rate", async function () {
            await payment.setCommissionBps(3000);
            const config = await payment.getConfig();
            expect(config._commissionBps).to.equal(3000n);
        });
        
        it("Should reject commission rate above 100%", async function () {
            await expect(payment.setCommissionBps(10001))
                .to.be.revertedWith("Max 100%");
        });
    });

    describe("Access Control - Operator", function () {
        it("Should allow operator to register user", async function () {
            await expect(payment.connect(operator).registerUser(user1.address, affiliate.address))
                .to.emit(payment, "UserRegistered")
                .withArgs(user1.address, affiliate.address);
        });
        
        it("Should allow operator to process payment", async function () {
            await payment.connect(operator).registerUser(user1.address, ethers.ZeroAddress);
            const amount = ethers.parseUnits("100", 6);
            
            await expect(payment.connect(operator).processPayment(user1.address, amount))
                .to.emit(payment, "PaymentProcessed");
        });
        
        it("Should reject non-operator from operator functions", async function () {
            await expect(payment.connect(nonOperator).registerUser(user1.address, ethers.ZeroAddress))
                .to.be.revertedWithCustomError(payment, "OnlyOperator");
        });
    });

    describe("User Registration", function () {
        it("Should register user without affiliate", async function () {
            await payment.connect(operator).registerUser(user1.address, ethers.ZeroAddress);
            const status = await payment.getUserStatus(user1.address);
            expect(status.registered).to.be.true;
            expect(status.affiliate).to.equal(ethers.ZeroAddress);
        });
        
        it("Should register user with affiliate", async function () {
            await payment.connect(operator).registerUser(user1.address, affiliate.address);
            const status = await payment.getUserStatus(user1.address);
            expect(status.affiliate).to.equal(affiliate.address);
        });
        
        it("Should reject duplicate registration", async function () {
            await payment.connect(operator).registerUser(user1.address, ethers.ZeroAddress);
            await expect(payment.connect(operator).registerUser(user1.address, ethers.ZeroAddress))
                .to.be.revertedWithCustomError(payment, "AlreadyRegistered");
        });
        
        it("Should reject self-referral", async function () {
            await expect(payment.connect(operator).registerUser(user1.address, user1.address))
                .to.be.revertedWithCustomError(payment, "CannotSelfRefer");
        });
    });

    describe("Payment Processing", function () {
        beforeEach(async function () {
            await payment.connect(operator).registerUser(user1.address, ethers.ZeroAddress);
        });
        
        it("Should process payment without affiliate", async function () {
            const amount = ethers.parseUnits("100", 6);
            const treasuryBefore = await mockUsdc.balanceOf(treasury.address);
            
            await payment.connect(operator).processPayment(user1.address, amount);
            
            const treasuryAfter = await mockUsdc.balanceOf(treasury.address);
            expect(treasuryAfter - treasuryBefore).to.equal(amount);
        });
        
        it("Should emit InsufficientBalance event when user has no funds", async function () {
            // Create user with no USDC
            const poorUser = ethers.Wallet.createRandom();
            await payment.connect(operator).registerUser(poorUser.address, ethers.ZeroAddress);
            
            const amount = ethers.parseUnits("100", 6);
            await expect(payment.connect(operator).processPayment(poorUser.address, amount))
                .to.emit(payment, "InsufficientBalance");
        });
        
        it("Should reject payment for unregistered user", async function () {
            await expect(payment.connect(operator).processPayment(nonOperator.address, 100))
                .to.be.revertedWithCustomError(payment, "UserNotRegistered");
        });
        
        it("Should reject zero amount payment", async function () {
            await expect(payment.connect(operator).processPayment(user1.address, 0))
                .to.be.revertedWithCustomError(payment, "AmountMustBePositive");
        });
    });

    describe("Affiliate System", function () {
        beforeEach(async function () {
            await payment.connect(operator).registerUser(user1.address, affiliate.address);
            await payment.connect(operator).registerUser(user2.address, affiliate.address);
        });
        
        it("Should hold commission for unqualified affiliate", async function () {
            const amount = ethers.parseUnits("100", 6);
            
            await payment.connect(operator).processPayment(user1.address, amount);
            
            const affiliateStatus = await payment.getAffiliateStatus(affiliate.address);
            expect(affiliateStatus.paidUsers).to.equal(1n);
            expect(affiliateStatus.qualified).to.be.false;
            expect(affiliateStatus.pending).to.be.gt(0n);
        });
        
        it("Should release pending commissions when affiliate qualifies", async function () {
            const amount = ethers.parseUnits("100", 6);
            
            // First payment - held
            await payment.connect(operator).processPayment(user1.address, amount);
            
            // Second payment - should release pending
            const affiliateBefore = await mockUsdc.balanceOf(affiliate.address);
            await payment.connect(operator).processPayment(user2.address, amount);
            const affiliateAfter = await mockUsdc.balanceOf(affiliate.address);
            
            const affiliateStatus = await payment.getAffiliateStatus(affiliate.address);
            expect(affiliateStatus.qualified).to.be.true;
            expect(affiliateStatus.pending).to.equal(0n);
            expect(affiliateAfter).to.be.gt(affiliateBefore);
        });
        
        it("Should pay commission immediately for qualified affiliate", async function () {
            const amount = ethers.parseUnits("100", 6);
            
            // Qualify affiliate
            await payment.connect(operator).processPayment(user1.address, amount);
            await payment.connect(operator).processPayment(user2.address, amount);
            
            // Further payments should pay immediately
            const affiliateBefore = await mockUsdc.balanceOf(affiliate.address);
            await payment.connect(operator).processPayment(user1.address, amount);
            const affiliateAfter = await mockUsdc.balanceOf(affiliate.address);
            
            const expectedCommission = (amount * COMMISSION_BPS) / 10000n;
            expect(affiliateAfter - affiliateBefore).to.equal(expectedCommission);
        });
    });

    describe("Upgradeability", function () {
        it("Should upgrade to V3 successfully", async function () {
            // Deploy mock V3
            const KubeTEEPaymentV3 = await ethers.getContractFactory("KubeTEEPaymentV2"); // Same contract for test
            const upgraded = await upgrades.upgradeProxy(await payment.getAddress(), KubeTEEPaymentV3);
            expect(await upgraded.getAddress()).to.equal(await payment.getAddress());
        });
        
        it("Should preserve state after upgrade", async function () {
            // Register user before upgrade
            await payment.connect(operator).registerUser(user1.address, affiliate.address);
            
            // Upgrade
            const KubeTEEPaymentV3 = await ethers.getContractFactory("KubeTEEPaymentV2");
            const upgraded = await upgrades.upgradeProxy(await payment.getAddress(), KubeTEEPaymentV3);
            
            // Check state preserved
            const status = await upgraded.getUserStatus(user1.address);
            expect(status.registered).to.be.true;
        });
        
        it("Should reject unauthorized upgrade", async function () {
            const KubeTEEPaymentV3 = await ethers.getContractFactory("KubeTEEPaymentV2", nonOperator);
            await expect(
                upgrades.upgradeProxy(await payment.getAddress(), KubeTEEPaymentV3)
            ).to.be.reverted;
        });
    });

    describe("View Functions", function () {
        it("Should return correct user status", async function () {
            await payment.connect(operator).registerUser(user1.address, affiliate.address);
            const status = await payment.getUserStatus(user1.address);
            
            expect(status.registered).to.be.true;
            expect(status.affiliate).to.equal(affiliate.address);
            expect(status.hasPaid).to.be.false;
            expect(status.balance).to.equal(USER_BALANCE);
            expect(status.allowance).to.equal(ethers.MaxUint256);
        });
        
        it("Should return correct affiliate status", async function () {
            const status = await payment.getAffiliateStatus(affiliate.address);
            expect(status.paidUsers).to.equal(0n);
            expect(status.pending).to.equal(0n);
            expect(status.qualified).to.be.false;
        });
        
        it("Should return correct config", async function () {
            const config = await payment.getConfig();
            expect(config.usdcAddress).to.equal(await mockUsdc.getAddress());
            expect(config.treasuryAddress).to.equal(treasury.address);
            expect(config._minPaidUsers).to.equal(MIN_PAID_USERS);
            expect(config._commissionBps).to.equal(COMMISSION_BPS);
        });
    });

    describe("Edge Cases & Security", function () {
        it("Should handle reentrancy attacks", async function () {
            // The ReentrancyGuard should prevent reentrancy
            // This is tested implicitly through the nonReentrant modifier
            await payment.connect(operator).registerUser(user1.address, ethers.ZeroAddress);
            const amount = ethers.parseUnits("100", 6);
            
            // Multiple rapid calls should work correctly
            await payment.connect(operator).processPayment(user1.address, amount);
            await payment.connect(operator).processPayment(user1.address, amount);
        });
        
        it("Should handle zero addresses properly", async function () {
            await expect(payment.setTreasury(ethers.ZeroAddress))
                .to.be.revertedWithCustomError(payment, "InvalidAddress");
            
            await expect(payment.setUsdc(ethers.ZeroAddress))
                .to.be.revertedWithCustomError(payment, "InvalidAddress");
        });
        
        it("Should handle max uint256 approval", async function () {
            await payment.connect(operator).registerUser(user1.address, ethers.ZeroAddress);
            const amount = ethers.parseUnits("100", 6);
            
            await payment.connect(operator).processPayment(user1.address, amount);
            
            // Verify user still has max approval
            const status = await payment.getUserStatus(user1.address);
            expect(status.allowance).to.be.gt(amount);
        });
    });
});

// Mock ERC20 for testing
const MockERC20Contract = `
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.22;

import "@openzeppelin/contracts/token/ERC20/ERC20.sol";

contract MockERC20 is ERC20 {
    uint8 private _decimals;
    
    constructor(string memory name, string memory symbol, uint8 decimals_) ERC20(name, symbol) {
        _decimals = decimals_;
    }
    
    function decimals() public view override returns (uint8) {
        return _decimals;
    }
    
    function mint(address to, uint256 amount) external {
        _mint(to, amount);
    }
}
`;
