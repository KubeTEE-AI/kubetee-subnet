const { expect } = require("chai");
const { ethers, upgrades } = require("hardhat");
const { time } = require("@nomicfoundation/hardhat-network-helpers");

describe("KubeTEEReseller", function () {
    let KubeTEEReseller;
    let reseller;
    let mockUsdc;
    let owner;
    let operator1;
    let operator2;
    let treasury;
    let resellerUser1;
    let resellerUser2;
    let nonOperator;
    
    const INITIAL_SUPPLY = ethers.parseUnits("1000000", 6);
    const RESELLER_BALANCE = ethers.parseUnits("10000", 6);
    const MIN_DEPOSIT = ethers.parseUnits("10", 6);
    const EPOCH_DURATION = 3600; // 1 hour
    
    beforeEach(async function () {
        [owner, operator1, operator2, treasury, resellerUser1, resellerUser2, nonOperator] = await ethers.getSigners();
        
        // Deploy mock USDC
        const MockERC20 = await ethers.getContractFactory("MockERC20");
        mockUsdc = await MockERC20.deploy("USD Coin", "USDC", 6);
        await mockUsdc.waitForDeployment();
        
        // Mint USDC to resellers
        await mockUsdc.mint(resellerUser1.address, RESELLER_BALANCE);
        await mockUsdc.mint(resellerUser2.address, RESELLER_BALANCE);
        
        // Deploy KubeTEEReseller
        KubeTEEReseller = await ethers.getContractFactory("KubeTEEReseller");
        reseller = await upgrades.deployProxy(
            KubeTEEReseller,
            [await mockUsdc.getAddress(), treasury.address, EPOCH_DURATION],
            { kind: "uups" }
        );
        await reseller.waitForDeployment();
        
        // Add operators
        await reseller.addOperator(operator1.address);
        await reseller.addOperator(operator2.address);
        
        // Approve spending
        await mockUsdc.connect(resellerUser1).approve(await reseller.getAddress(), ethers.MaxUint256);
        await mockUsdc.connect(resellerUser2).approve(await reseller.getAddress(), ethers.MaxUint256);
    });

    describe("Deployment & Initialization", function () {
        it("Should deploy as proxy correctly", async function () {
            expect(await reseller.getAddress()).to.be.properAddress;
        });
        
        it("Should initialize with correct owner", async function () {
            expect(await reseller.owner()).to.equal(owner.address);
        });
        
        it("Should initialize with correct treasury", async function () {
            expect(await reseller.treasury()).to.equal(treasury.address);
        });
        
        it("Should initialize with correct epoch duration", async function () {
            expect(await reseller.epochDuration()).to.equal(EPOCH_DURATION);
        });
        
        it("Should start at epoch 1", async function () {
            expect(await reseller.currentEpoch()).to.equal(1);
        });
        
        it("Should not allow re-initialization", async function () {
            await expect(
                reseller.initialize(await mockUsdc.getAddress(), treasury.address, EPOCH_DURATION)
            ).to.be.reverted;
        });
    });

    describe("Access Control - Admin", function () {
        it("Should allow admin to add operator", async function () {
            const newOperator = ethers.Wallet.createRandom().address;
            await expect(reseller.addOperator(newOperator))
                .to.emit(reseller, "OperatorAdded")
                .withArgs(newOperator);
        });
        
        it("Should allow admin to remove operator", async function () {
            await expect(reseller.removeOperator(operator1.address))
                .to.emit(reseller, "OperatorRemoved")
                .withArgs(operator1.address);
        });
        
        it("Should auto-adjust required confirmations on operator changes", async function () {
            // With 2 operators, required should be 2 (2/2 + 1 = 2)
            expect(await reseller.requiredConfirmations()).to.equal(2);
            
            // Remove one operator
            await reseller.removeOperator(operator2.address);
            expect(await reseller.requiredConfirmations()).to.equal(1);
        });
        
        it("Should allow admin to pause and unpause", async function () {
            await reseller.pause();
            expect(await reseller.paused()).to.be.true;
            
            await reseller.unpause();
            expect(await reseller.paused()).to.be.false;
        });
        
        it("Should allow admin to deactivate reseller", async function () {
            await reseller.connect(resellerUser1).register("namespace1", "Business 1");
            
            await expect(reseller.deactivateReseller(resellerUser1.address))
                .to.emit(reseller, "ResellerDeactivated")
                .withArgs(resellerUser1.address);
        });
        
        it("Should allow admin to reactivate reseller", async function () {
            await reseller.connect(resellerUser1).register("namespace1", "Business 1");
            await reseller.deactivateReseller(resellerUser1.address);
            
            await expect(reseller.reactivateReseller(resellerUser1.address))
                .to.emit(reseller, "ResellerReactivated")
                .withArgs(resellerUser1.address);
        });
        
        it("Should reject non-admin from admin functions", async function () {
            await expect(reseller.connect(nonOperator).addOperator(nonOperator.address))
                .to.be.revertedWithCustomError(reseller, "OwnableUnauthorizedAccount");
        });
    });

    describe("Reseller Registration", function () {
        it("Should allow user to register as reseller", async function () {
            await expect(reseller.connect(resellerUser1).register("namespace1", "Business 1"))
                .to.emit(reseller, "ResellerRegistered")
                .withArgs(resellerUser1.address, "namespace1", "Business 1");
        });
        
        it("Should reject duplicate registration", async function () {
            await reseller.connect(resellerUser1).register("namespace1", "Business 1");
            
            await expect(reseller.connect(resellerUser1).register("namespace2", "Business 2"))
                .to.be.revertedWithCustomError(reseller, "AlreadyRegistered");
        });
        
        it("Should reject duplicate namespace", async function () {
            await reseller.connect(resellerUser1).register("namespace1", "Business 1");
            
            await expect(reseller.connect(resellerUser2).register("namespace1", "Business 2"))
                .to.be.revertedWithCustomError(reseller, "NamespaceTaken");
        });
        
        it("Should reject empty namespace", async function () {
            await expect(reseller.connect(resellerUser1).register("", "Business 1"))
                .to.be.revertedWithCustomError(reseller, "EmptyNamespace");
        });
        
        it("Should reject registration when paused", async function () {
            await reseller.pause();
            
            await expect(reseller.connect(resellerUser1).register("namespace1", "Business 1"))
                .to.be.revertedWithCustomError(reseller, "EnforcedPause");
        });
    });

    describe("Deposits & Withdrawals", function () {
        beforeEach(async function () {
            await reseller.connect(resellerUser1).register("namespace1", "Business 1");
        });
        
        it("Should allow deposit above minimum", async function () {
            const depositAmount = ethers.parseUnits("100", 6);
            
            await expect(reseller.connect(resellerUser1).deposit(depositAmount))
                .to.emit(reseller, "Deposited")
                .withArgs(resellerUser1.address, depositAmount, depositAmount);
        });
        
        it("Should reject deposit below minimum", async function () {
            const smallAmount = ethers.parseUnits("5", 6);
            
            await expect(reseller.connect(resellerUser1).deposit(smallAmount))
                .to.be.revertedWithCustomError(reseller, "BelowMinDeposit");
        });
        
        it("Should allow withdrawal of unused balance", async function () {
            const depositAmount = ethers.parseUnits("100", 6);
            await reseller.connect(resellerUser1).deposit(depositAmount);
            
            const withdrawAmount = ethers.parseUnits("50", 6);
            await expect(reseller.connect(resellerUser1).withdraw(withdrawAmount))
                .to.emit(reseller, "Withdrawn")
                .withArgs(resellerUser1.address, withdrawAmount);
        });
        
        it("Should reject withdrawal exceeding available balance", async function () {
            const depositAmount = ethers.parseUnits("100", 6);
            await reseller.connect(resellerUser1).deposit(depositAmount);
            
            const withdrawAmount = ethers.parseUnits("101", 6);
            await expect(reseller.connect(resellerUser1).withdraw(withdrawAmount))
                .to.be.revertedWithCustomError(reseller, "InsufficientBalance");
        });
    });

    describe("Usage Reporting & Settlement", function () {
        beforeEach(async function () {
            await reseller.connect(resellerUser1).register("namespace1", "Business 1");
            await reseller.connect(resellerUser2).register("namespace2", "Business 2");
            await reseller.connect(resellerUser1).deposit(ethers.parseUnits("100", 6));
            await reseller.connect(resellerUser2).deposit(ethers.parseUnits("100", 6));
        });
        
        it("Should allow operator to report usage", async function () {
            const usage = ethers.parseUnits("10", 6);
            
            await expect(reseller.connect(operator1).reportUsage(
                [resellerUser1.address],
                [usage]
            )).to.emit(reseller, "UsageReported");
        });
        
        it("Should reject duplicate usage report from same operator", async function () {
            const usage = ethers.parseUnits("10", 6);
            
            await reseller.connect(operator1).reportUsage([resellerUser1.address], [usage]);
            
            await expect(reseller.connect(operator1).reportUsage([resellerUser1.address], [usage]))
                .to.be.revertedWithCustomError(reseller, "AlreadyReported");
        });
        
        it("Should auto-settle when confirmations reached", async function () {
            const usage = ethers.parseUnits("10", 6);
            
            // First operator reports
            await reseller.connect(operator1).reportUsage([resellerUser1.address], [usage]);
            
            // Second operator reports - should trigger settlement
            await expect(reseller.connect(operator2).reportUsage([resellerUser1.address], [usage]))
                .to.emit(reseller, "EpochSettled");
        });
        
        it("Should transfer funds to treasury on settlement", async function () {
            const usage = ethers.parseUnits("10", 6);
            const treasuryBefore = await mockUsdc.balanceOf(treasury.address);
            
            await reseller.connect(operator1).reportUsage([resellerUser1.address], [usage]);
            await reseller.connect(operator2).reportUsage([resellerUser1.address], [usage]);
            
            const treasuryAfter = await mockUsdc.balanceOf(treasury.address);
            expect(treasuryAfter - treasuryBefore).to.equal(usage);
        });
        
        it("Should deactivate reseller with insufficient balance", async function () {
            const hugeUsage = ethers.parseUnits("1000", 6); // More than deposited
            
            await reseller.connect(operator1).reportUsage([resellerUser1.address], [hugeUsage]);
            await reseller.connect(operator2).reportUsage([resellerUser1.address], [hugeUsage]);
            
            expect(await reseller.isReseller(resellerUser1.address)).to.be.false;
        });
        
        it("Should allow manual epoch settlement by admin", async function () {
            // Advance time past epoch duration
            await time.increase(EPOCH_DURATION + 1);
            
            await expect(reseller.connect(owner).settleEpoch())
                .to.emit(reseller, "EpochSettled");
        });
    });

    describe("View Functions", function () {
        beforeEach(async function () {
            await reseller.connect(resellerUser1).register("namespace1", "Business 1");
            await reseller.connect(resellerUser1).deposit(ethers.parseUnits("100", 6));
        });
        
        it("Should return correct reseller info", async function () {
            const info = await reseller.getResellerInfo(resellerUser1.address);
            
            expect(info.namespace).to.equal("namespace1");
            expect(info.name).to.equal("Business 1");
            expect(info.active).to.be.true;
            expect(info.balance).to.equal(ethers.parseUnits("100", 6));
        });
        
        it("Should return correct stats", async function () {
            const stats = await reseller.getStats();
            
            expect(stats.totalResellers).to.equal(1);
            expect(stats.activeResellers).to.equal(1);
            expect(stats._currentEpoch).to.equal(1);
            expect(stats._operatorCount).to.equal(2);
        });
        
        it("Should return all resellers", async function () {
            const allResellers = await reseller.getAllResellers();
            expect(allResellers).to.include(resellerUser1.address);
        });
    });

    describe("Upgradeability", function () {
        it("Should upgrade to V3 successfully", async function () {
            const KubeTEEResellerV3 = await ethers.getContractFactory("KubeTEEReseller");
            const upgraded = await upgrades.upgradeProxy(await reseller.getAddress(), KubeTEEResellerV3);
            expect(await upgraded.getAddress()).to.equal(await reseller.getAddress());
        });
        
        it("Should preserve state after upgrade", async function () {
            await reseller.connect(resellerUser1).register("namespace1", "Business 1");
            
            const KubeTEEResellerV3 = await ethers.getContractFactory("KubeTEEReseller");
            const upgraded = await upgrades.upgradeProxy(await reseller.getAddress(), KubeTEEResellerV3);
            
            expect(await upgraded.isReseller(resellerUser1.address)).to.be.true;
        });
    });
});
