const { expect } = require("chai");
const { ethers, upgrades } = require("hardhat");
const { time } = require("@nomicfoundation/hardhat-network-helpers");

describe("KubeTEEBuybackBurnV2", function () {
    let KubeTEEBuybackBurnV2;
    let buyback;
    let mockUsdc;
    let mockWtao;
    let mockRouter;
    let mockBridge;
    let owner;
    let operator;
    let depositor;
    let nonOperator;
    
    const INITIAL_SUPPLY = ethers.parseUnits("1000000", 6);
    const MIN_BUYBACK = ethers.parseUnits("100", 6);
    const BUYBACK_INTERVAL = 24 * 60 * 60; // 24 hours
    const MAX_SLIPPAGE_BPS = 200; // 2%
    const BITTENSOR_ADDRESS = "5GrwvaEF5zXb26Fz9rcQpDWS57CtERHpNehXCPcNoHGKutQY";
    
    beforeEach(async function () {
        [owner, operator, depositor, nonOperator] = await ethers.getSigners();
        
        // Deploy mock tokens
        const MockERC20 = await ethers.getContractFactory("MockERC20");
        mockUsdc = await MockERC20.deploy("USD Coin", "USDC", 6);
        mockWtao = await MockERC20.deploy("Wrapped TAO", "wTAO", 18);
        await mockUsdc.waitForDeployment();
        await mockWtao.waitForDeployment();
        
        // Deploy mock router
        const MockSwapRouter = await ethers.getContractFactory("MockSwapRouter");
        mockRouter = await MockSwapRouter.deploy(await mockWtao.getAddress());
        await mockRouter.waitForDeployment();
        
        // Deploy mock bridge
        const MockWTAOBridge = await ethers.getContractFactory("MockWTAOBridge");
        mockBridge = await MockWTAOBridge.deploy();
        await mockBridge.waitForDeployment();
        
        // Mint USDC to depositor
        await mockUsdc.mint(depositor.address, INITIAL_SUPPLY);
        
        // Deploy KubeTEEBuybackBurnV2
        KubeTEEBuybackBurnV2 = await ethers.getContractFactory("KubeTEEBuybackBurnV2");
        buyback = await upgrades.deployProxy(
            KubeTEEBuybackBurnV2,
            [await mockUsdc.getAddress(), await mockRouter.getAddress(), BITTENSOR_ADDRESS],
            { kind: "uups" }
        );
        await buyback.waitForDeployment();
        
        // Configure wTAO and bridge
        await buyback.setWtao(await mockWtao.getAddress());
        await buyback.setWtaoBridge(await mockBridge.getAddress());
        
        // Add operator
        await buyback.addOperator(operator.address);
        
        // Approve USDC spending
        await mockUsdc.connect(depositor).approve(await buyback.getAddress(), ethers.MaxUint256);
        
        // Fund router with wTAO for swaps
        await mockWtao.mint(await mockRouter.getAddress(), ethers.parseUnits("10000", 18));
    });

    describe("Deployment & Initialization", function () {
        it("Should deploy as proxy correctly", async function () {
            expect(await buyback.getAddress()).to.be.properAddress;
        });
        
        it("Should initialize with correct owner", async function () {
            expect(await buyback.owner()).to.equal(owner.address);
        });
        
        it("Should initialize with correct USDC", async function () {
            const config = await buyback.getConfig();
            expect(config.usdcAddress).to.equal(await mockUsdc.getAddress());
        });
        
        it("Should initialize with default values", async function () {
            expect(await buyback.minBuybackAmount()).to.equal(MIN_BUYBACK);
            expect(await buyback.maxSlippageBps()).to.equal(MAX_SLIPPAGE_BPS);
            expect(await buyback.buybackInterval()).to.equal(BUYBACK_INTERVAL);
        });
        
        it("Should initialize with Bittensor address", async function () {
            expect(await buyback.bittensorSwapAddress()).to.equal(BITTENSOR_ADDRESS);
        });
        
        it("Should not allow re-initialization", async function () {
            await expect(
                buyback.initialize(await mockUsdc.getAddress(), await mockRouter.getAddress(), BITTENSOR_ADDRESS)
            ).to.be.reverted;
        });
    });

    describe("Access Control - Admin", function () {
        it("Should allow admin to add operator", async function () {
            const newOperator = ethers.Wallet.createRandom().address;
            await expect(buyback.addOperator(newOperator))
                .to.emit(buyback, "OperatorAdded")
                .withArgs(newOperator);
        });
        
        it("Should allow admin to remove operator", async function () {
            await expect(buyback.removeOperator(operator.address))
                .to.emit(buyback, "OperatorRemoved")
                .withArgs(operator.address);
        });
        
        it("Should allow admin to set configuration", async function () {
            await buyback.setMinBuybackAmount(ethers.parseUnits("200", 6));
            expect(await buyback.minBuybackAmount()).to.equal(ethers.parseUnits("200", 6));
        });
        
        it("Should allow admin to pause and unpause", async function () {
            await buyback.pause();
            expect(await buyback.paused()).to.be.true;
            
            await buyback.unpause();
            expect(await buyback.paused()).to.be.false;
        });
        
        it("Should reject max slippage above 5%", async function () {
            await expect(buyback.setMaxSlippageBps(600))
                .to.be.revertedWithCustomError(buyback, "MaxSlippageExceeded");
        });
        
        it("Should reject buyback interval below 1 hour", async function () {
            await expect(buyback.setBuybackInterval(1800))
                .to.be.revertedWithCustomError(buyback, "MinIntervalNotMet");
        });
        
        it("Should reject non-admin from admin functions", async function () {
            await expect(buyback.connect(nonOperator).setMinBuybackAmount(100))
                .to.be.revertedWithCustomError(buyback, "OwnableUnauthorizedAccount");
        });
        
        it("Should allow admin to emergency withdraw", async function () {
            await buyback.connect(depositor).depositUsdc(ethers.parseUnits("100", 6));
            
            const ownerBefore = await mockUsdc.balanceOf(owner.address);
            await buyback.emergencyWithdraw(await mockUsdc.getAddress(), ethers.parseUnits("100", 6));
            const ownerAfter = await mockUsdc.balanceOf(owner.address);
            
            expect(ownerAfter - ownerBefore).to.equal(ethers.parseUnits("100", 6));
        });
    });

    describe("Access Control - Operator", function () {
        it("Should allow operator to trigger manual buyback", async function () {
            // Deposit USDC
            await buyback.connect(depositor).depositUsdc(ethers.parseUnits("200", 6));
            
            // Advance time past interval
            await time.increase(BUYBACK_INTERVAL + 1);
            
            await expect(buyback.connect(operator).manualBuyback())
                .to.emit(buyback, "BuybackExecuted");
        });
        
        it("Should allow owner to trigger manual buyback", async function () {
            await buyback.connect(depositor).depositUsdc(ethers.parseUnits("200", 6));
            await time.increase(BUYBACK_INTERVAL + 1);
            
            await expect(buyback.connect(owner).manualBuyback())
                .to.emit(buyback, "BuybackExecuted");
        });
        
        it("Should reject non-operator from manual buyback", async function () {
            await buyback.connect(depositor).depositUsdc(ethers.parseUnits("200", 6));
            
            await expect(buyback.connect(nonOperator).manualBuyback())
                .to.be.revertedWithCustomError(buyback, "OnlyOperator");
        });
    });

    describe("USDC Deposits", function () {
        it("Should allow anyone to deposit USDC", async function () {
            const amount = ethers.parseUnits("100", 6);
            
            await buyback.connect(depositor).depositUsdc(amount);
            
            const state = await buyback.getState();
            expect(state.usdcBalance).to.equal(amount);
        });
    });

    describe("Chainlink Automation", function () {
        it("Should return false for checkUpkeep when insufficient USDC", async function () {
            const [upkeepNeeded] = await buyback.checkUpkeep("0x");
            expect(upkeepNeeded).to.be.false;
        });
        
        it("Should return false for checkUpkeep when interval not passed", async function () {
            await buyback.connect(depositor).depositUsdc(ethers.parseUnits("200", 6));
            
            const [upkeepNeeded] = await buyback.checkUpkeep("0x");
            expect(upkeepNeeded).to.be.false;
        });
        
        it("Should return true for checkUpkeep when conditions met", async function () {
            await buyback.connect(depositor).depositUsdc(ethers.parseUnits("200", 6));
            await time.increase(BUYBACK_INTERVAL + 1);
            
            const [upkeepNeeded] = await buyback.checkUpkeep("0x");
            expect(upkeepNeeded).to.be.true;
        });
        
        it("Should return false for checkUpkeep when paused", async function () {
            await buyback.connect(depositor).depositUsdc(ethers.parseUnits("200", 6));
            await time.increase(BUYBACK_INTERVAL + 1);
            await buyback.pause();
            
            const [upkeepNeeded] = await buyback.checkUpkeep("0x");
            expect(upkeepNeeded).to.be.false;
        });
        
        it("Should execute performUpkeep when conditions met", async function () {
            await buyback.connect(depositor).depositUsdc(ethers.parseUnits("200", 6));
            await time.increase(BUYBACK_INTERVAL + 1);
            
            await expect(buyback.performUpkeep("0x"))
                .to.emit(buyback, "BuybackExecuted");
        });
        
        it("Should reject performUpkeep when insufficient USDC", async function () {
            await time.increase(BUYBACK_INTERVAL + 1);
            
            await expect(buyback.performUpkeep("0x"))
                .to.be.revertedWithCustomError(buyback, "InsufficientUSDC");
        });
        
        it("Should reject performUpkeep when too soon", async function () {
            await buyback.connect(depositor).depositUsdc(ethers.parseUnits("200", 6));
            
            await expect(buyback.performUpkeep("0x"))
                .to.be.revertedWithCustomError(buyback, "TooSoon");
        });
    });

    describe("Buyback Execution", function () {
        beforeEach(async function () {
            await buyback.connect(depositor).depositUsdc(ethers.parseUnits("200", 6));
            await time.increase(BUYBACK_INTERVAL + 1);
        });
        
        it("Should execute buyback and update state", async function () {
            const stateBefore = await buyback.getStats();
            
            await buyback.connect(operator).manualBuyback();
            
            const stateAfter = await buyback.getStats();
            expect(stateAfter._totalUsdcConverted).to.be.gt(stateBefore._totalUsdcConverted);
            expect(stateAfter._totalWtaoAcquired).to.be.gt(stateBefore._totalWtaoAcquired);
        });
        
        it("Should update last buyback time", async function () {
            const lastBefore = await buyback.lastBuybackTime();
            
            await buyback.connect(operator).manualBuyback();
            
            const lastAfter = await buyback.lastBuybackTime();
            expect(lastAfter).to.be.gt(lastBefore);
        });
        
        it("Should initiate bridge if configured", async function () {
            await expect(buyback.connect(operator).manualBuyback())
                .to.emit(buyback, "BridgeInitiated");
        });
        
        it("Should reject buyback when wTAO not configured", async function () {
            // Deploy new contract without wTAO
            const newBuyback = await upgrades.deployProxy(
                KubeTEEBuybackBurnV2,
                [await mockUsdc.getAddress(), await mockRouter.getAddress(), BITTENSOR_ADDRESS],
                { kind: "uups" }
            );
            await newBuyback.addOperator(operator.address);
            await mockUsdc.connect(depositor).approve(await newBuyback.getAddress(), ethers.MaxUint256);
            await newBuyback.connect(depositor).depositUsdc(ethers.parseUnits("200", 6));
            await time.increase(BUYBACK_INTERVAL + 1);
            
            await expect(newBuyback.connect(operator).manualBuyback())
                .to.be.revertedWithCustomError(newBuyback, "WtaoNotConfigured");
        });
    });

    describe("Manual Bridge", function () {
        it("Should allow operator to trigger manual bridge", async function () {
            // First do a buyback to get wTAO in contract
            await buyback.connect(depositor).depositUsdc(ethers.parseUnits("200", 6));
            await time.increase(BUYBACK_INTERVAL + 1);
            
            // Disable auto-bridge temporarily by setting bridge to zero
            await buyback.setWtaoBridge(ethers.ZeroAddress);
            await buyback.connect(operator).manualBuyback();
            
            // Re-enable bridge
            await buyback.setWtaoBridge(await mockBridge.getAddress());
            
            // Manual bridge
            await expect(buyback.connect(operator).manualBridge())
                .to.emit(buyback, "BridgeInitiated");
        });
        
        it("Should reject manual bridge when bridge not configured", async function () {
            await buyback.setWtaoBridge(ethers.ZeroAddress);
            
            await expect(buyback.connect(operator).manualBridge())
                .to.be.revertedWithCustomError(buyback, "BridgeNotConfigured");
        });
        
        it("Should reject manual bridge when no wTAO available", async function () {
            await expect(buyback.connect(operator).manualBridge())
                .to.be.revertedWithCustomError(buyback, "NoWtaoToBridge");
        });
    });

    describe("View Functions", function () {
        it("Should return correct state", async function () {
            await buyback.connect(depositor).depositUsdc(ethers.parseUnits("200", 6));
            
            const state = await buyback.getState();
            expect(state.usdcBalance).to.equal(ethers.parseUnits("200", 6));
            expect(state.canExecute).to.be.false; // Interval not passed
        });
        
        it("Should return correct stats", async function () {
            const stats = await buyback.getStats();
            expect(stats._totalUsdcConverted).to.equal(0);
            expect(stats._totalWtaoAcquired).to.equal(0);
        });
        
        it("Should return correct config", async function () {
            const config = await buyback.getConfig();
            expect(config.usdcAddress).to.equal(await mockUsdc.getAddress());
            expect(config.wtaoAddress).to.equal(await mockWtao.getAddress());
            expect(config.swapRouterAddress).to.equal(await mockRouter.getAddress());
            expect(config.wtaoBridgeAddress).to.equal(await mockBridge.getAddress());
        });
    });

    describe("Upgradeability", function () {
        it("Should upgrade to V3 successfully", async function () {
            const KubeTEEBuybackBurnV3 = await ethers.getContractFactory("KubeTEEBuybackBurnV2");
            const upgraded = await upgrades.upgradeProxy(await buyback.getAddress(), KubeTEEBuybackBurnV3);
            expect(await upgraded.getAddress()).to.equal(await buyback.getAddress());
        });
        
        it("Should preserve state after upgrade", async function () {
            await buyback.connect(depositor).depositUsdc(ethers.parseUnits("200", 6));
            
            const KubeTEEBuybackBurnV3 = await ethers.getContractFactory("KubeTEEBuybackBurnV2");
            const upgraded = await upgrades.upgradeProxy(await buyback.getAddress(), KubeTEEBuybackBurnV3);
            
            const state = await upgraded.getState();
            expect(state.usdcBalance).to.equal(ethers.parseUnits("200", 6));
        });
    });
});

// Additional mock contracts for testing
