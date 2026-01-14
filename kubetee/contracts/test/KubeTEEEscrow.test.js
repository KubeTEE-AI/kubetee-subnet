const { expect } = require("chai");
const { ethers, upgrades } = require("hardhat");

describe("KubeTEEEscrow", function () {
    let KubeTEEEscrow;
    let escrow;
    let mockToken;
    let owner;
    let operator;
    let treasury;
    let reseller1;
    let reseller2;
    let miner1;
    let miner2;
    let nonOperator;
    
    const INITIAL_SUPPLY = ethers.parseUnits("1000000", 18);
    const RESELLER_BALANCE = ethers.parseUnits("10000", 18);
    const MINER_SHARE_BPS = 5000n; // 50%
    const TREASURY_SHARE_BPS = 5000n; // 50%
    
    beforeEach(async function () {
        [owner, operator, treasury, reseller1, reseller2, miner1, miner2, nonOperator] = await ethers.getSigners();
        
        // Deploy mock payment token (wTAO/Alpha)
        const MockERC20 = await ethers.getContractFactory("MockERC20");
        mockToken = await MockERC20.deploy("Wrapped TAO", "wTAO", 18);
        await mockToken.waitForDeployment();
        
        // Mint tokens to resellers
        await mockToken.mint(reseller1.address, RESELLER_BALANCE);
        await mockToken.mint(reseller2.address, RESELLER_BALANCE);
        
        // Deploy KubeTEEEscrow
        KubeTEEEscrow = await ethers.getContractFactory("KubeTEEEscrow");
        escrow = await upgrades.deployProxy(
            KubeTEEEscrow,
            [await mockToken.getAddress(), treasury.address],
            { kind: "uups" }
        );
        await escrow.waitForDeployment();
        
        // Add operator
        await escrow.addOperator(operator.address);
        
        // Register resellers and miners
        await escrow.registerReseller(reseller1.address);
        await escrow.registerReseller(reseller2.address);
        await escrow.registerMiner(miner1.address);
        await escrow.registerMiner(miner2.address);
        
        // Approve spending
        await mockToken.connect(reseller1).approve(await escrow.getAddress(), ethers.MaxUint256);
        await mockToken.connect(reseller2).approve(await escrow.getAddress(), ethers.MaxUint256);
    });

    describe("Deployment & Initialization", function () {
        it("Should deploy as proxy correctly", async function () {
            expect(await escrow.getAddress()).to.be.properAddress;
        });
        
        it("Should initialize with correct owner", async function () {
            expect(await escrow.owner()).to.equal(owner.address);
        });
        
        it("Should initialize with correct payment token", async function () {
            const config = await escrow.getConfig();
            expect(config.paymentTokenAddress).to.equal(await mockToken.getAddress());
        });
        
        it("Should initialize with correct treasury", async function () {
            const config = await escrow.getConfig();
            expect(config.treasuryAddress).to.equal(treasury.address);
        });
        
        it("Should have correct share percentages", async function () {
            const config = await escrow.getConfig();
            expect(config.minerShareBps).to.equal(MINER_SHARE_BPS);
            expect(config.treasuryShareBps).to.equal(TREASURY_SHARE_BPS);
        });
        
        it("Should not allow re-initialization", async function () {
            await expect(
                escrow.initialize(await mockToken.getAddress(), treasury.address)
            ).to.be.reverted;
        });
    });

    describe("Access Control - Admin", function () {
        it("Should allow admin to register reseller", async function () {
            const newReseller = ethers.Wallet.createRandom().address;
            await expect(escrow.registerReseller(newReseller))
                .to.emit(escrow, "ResellerRegistered")
                .withArgs(newReseller);
        });
        
        it("Should allow admin to unregister reseller", async function () {
            await expect(escrow.unregisterReseller(reseller1.address))
                .to.emit(escrow, "ResellerUnregistered")
                .withArgs(reseller1.address);
        });
        
        it("Should allow admin to register miner", async function () {
            const newMiner = ethers.Wallet.createRandom().address;
            await expect(escrow.registerMiner(newMiner))
                .to.emit(escrow, "MinerRegistered")
                .withArgs(newMiner);
        });
        
        it("Should allow admin to unregister miner", async function () {
            await expect(escrow.unregisterMiner(miner1.address))
                .to.emit(escrow, "MinerUnregistered")
                .withArgs(miner1.address);
        });
        
        it("Should allow admin to add operator", async function () {
            const newOperator = ethers.Wallet.createRandom().address;
            await expect(escrow.addOperator(newOperator))
                .to.emit(escrow, "OperatorAdded")
                .withArgs(newOperator);
        });
        
        it("Should allow admin to remove operator", async function () {
            await expect(escrow.removeOperator(operator.address))
                .to.emit(escrow, "OperatorRemoved")
                .withArgs(operator.address);
        });
        
        it("Should reject non-admin from admin functions", async function () {
            await expect(escrow.connect(nonOperator).registerReseller(nonOperator.address))
                .to.be.revertedWithCustomError(escrow, "OwnableUnauthorizedAccount");
        });
        
        it("Should reject registering zero address", async function () {
            await expect(escrow.registerReseller(ethers.ZeroAddress))
                .to.be.revertedWithCustomError(escrow, "InvalidAddress");
        });
        
        it("Should reject duplicate registration", async function () {
            await expect(escrow.registerReseller(reseller1.address))
                .to.be.revertedWithCustomError(escrow, "AlreadyRegistered");
        });
    });

    describe("Reseller Functions", function () {
        it("Should allow reseller to deposit", async function () {
            const depositAmount = ethers.parseUnits("100", 18);
            
            await expect(escrow.connect(reseller1).deposit(depositAmount))
                .to.emit(escrow, "Deposit")
                .withArgs(reseller1.address, depositAmount);
        });
        
        it("Should update balance after deposit", async function () {
            const depositAmount = ethers.parseUnits("100", 18);
            await escrow.connect(reseller1).deposit(depositAmount);
            
            expect(await escrow.getResellerBalance(reseller1.address)).to.equal(depositAmount);
        });
        
        it("Should reject deposit from non-reseller", async function () {
            await expect(escrow.connect(nonOperator).deposit(100))
                .to.be.revertedWithCustomError(escrow, "NotRegisteredReseller");
        });
        
        it("Should reject zero amount deposit", async function () {
            await expect(escrow.connect(reseller1).deposit(0))
                .to.be.revertedWithCustomError(escrow, "AmountMustBePositive");
        });
        
        it("Should allow reseller to withdraw credits", async function () {
            const depositAmount = ethers.parseUnits("100", 18);
            await escrow.connect(reseller1).deposit(depositAmount);
            
            const withdrawAmount = ethers.parseUnits("50", 18);
            await expect(escrow.connect(reseller1).withdrawCredits(withdrawAmount))
                .to.emit(escrow, "ResellerWithdrawal")
                .withArgs(reseller1.address, withdrawAmount);
        });
        
        it("Should reject withdrawal exceeding balance", async function () {
            const depositAmount = ethers.parseUnits("100", 18);
            await escrow.connect(reseller1).deposit(depositAmount);
            
            const withdrawAmount = ethers.parseUnits("101", 18);
            await expect(escrow.connect(reseller1).withdrawCredits(withdrawAmount))
                .to.be.revertedWithCustomError(escrow, "InsufficientBalance");
        });
    });

    describe("Service Attestation", function () {
        beforeEach(async function () {
            // Deposit for reseller
            await escrow.connect(reseller1).deposit(ethers.parseUnits("1000", 18));
        });
        
        it("Should allow operator to submit attestation", async function () {
            const cost = ethers.parseUnits("100", 18);
            const requestId = ethers.keccak256(ethers.toUtf8Bytes("request1"));
            
            await expect(escrow.connect(operator).submitServiceAttestation(
                reseller1.address,
                miner1.address,
                cost,
                requestId
            )).to.emit(escrow, "ServiceProcessed");
        });
        
        it("Should correctly split payment between miner and treasury", async function () {
            const cost = ethers.parseUnits("100", 18);
            const requestId = ethers.keccak256(ethers.toUtf8Bytes("request1"));
            
            const treasuryBefore = await mockToken.balanceOf(treasury.address);
            
            await escrow.connect(operator).submitServiceAttestation(
                reseller1.address,
                miner1.address,
                cost,
                requestId
            );
            
            const treasuryAfter = await mockToken.balanceOf(treasury.address);
            const minerPending = await escrow.getMinerPending(miner1.address);
            
            const expectedTreasuryShare = (cost * TREASURY_SHARE_BPS) / 10000n;
            const expectedMinerShare = (cost * MINER_SHARE_BPS) / 10000n;
            
            expect(treasuryAfter - treasuryBefore).to.equal(expectedTreasuryShare);
            expect(minerPending).to.equal(expectedMinerShare);
        });
        
        it("Should reject duplicate attestation", async function () {
            const cost = ethers.parseUnits("100", 18);
            const requestId = ethers.keccak256(ethers.toUtf8Bytes("request1"));
            
            await escrow.connect(operator).submitServiceAttestation(
                reseller1.address,
                miner1.address,
                cost,
                requestId
            );
            
            await expect(escrow.connect(operator).submitServiceAttestation(
                reseller1.address,
                miner1.address,
                cost,
                requestId
            )).to.be.revertedWithCustomError(escrow, "AlreadyProcessed");
        });
        
        it("Should reject attestation with insufficient reseller balance", async function () {
            const cost = ethers.parseUnits("10000", 18); // More than deposited
            const requestId = ethers.keccak256(ethers.toUtf8Bytes("request1"));
            
            await expect(escrow.connect(operator).submitServiceAttestation(
                reseller1.address,
                miner1.address,
                cost,
                requestId
            )).to.be.revertedWithCustomError(escrow, "InsufficientBalance");
        });
        
        it("Should reject attestation for unregistered reseller", async function () {
            const cost = ethers.parseUnits("100", 18);
            const requestId = ethers.keccak256(ethers.toUtf8Bytes("request1"));
            
            await expect(escrow.connect(operator).submitServiceAttestation(
                nonOperator.address,
                miner1.address,
                cost,
                requestId
            )).to.be.revertedWithCustomError(escrow, "NotRegisteredReseller");
        });
        
        it("Should reject attestation for unregistered miner", async function () {
            const cost = ethers.parseUnits("100", 18);
            const requestId = ethers.keccak256(ethers.toUtf8Bytes("request1"));
            
            await expect(escrow.connect(operator).submitServiceAttestation(
                reseller1.address,
                nonOperator.address,
                cost,
                requestId
            )).to.be.revertedWithCustomError(escrow, "NotRegisteredMiner");
        });
        
        it("Should reject attestation from non-operator", async function () {
            const cost = ethers.parseUnits("100", 18);
            const requestId = ethers.keccak256(ethers.toUtf8Bytes("request1"));
            
            await expect(escrow.connect(nonOperator).submitServiceAttestation(
                reseller1.address,
                miner1.address,
                cost,
                requestId
            )).to.be.revertedWithCustomError(escrow, "OnlyOperator");
        });
    });

    describe("Batch Attestations", function () {
        beforeEach(async function () {
            await escrow.connect(reseller1).deposit(ethers.parseUnits("1000", 18));
            await escrow.connect(reseller2).deposit(ethers.parseUnits("1000", 18));
        });
        
        it("Should process batch attestations", async function () {
            const costs = [ethers.parseUnits("100", 18), ethers.parseUnits("50", 18)];
            const requestIds = [
                ethers.keccak256(ethers.toUtf8Bytes("batch1")),
                ethers.keccak256(ethers.toUtf8Bytes("batch2"))
            ];
            
            await escrow.connect(operator).submitBatchAttestations(
                [reseller1.address, reseller2.address],
                [miner1.address, miner2.address],
                costs,
                requestIds
            );
            
            // Check miners received credits
            const miner1Pending = await escrow.getMinerPending(miner1.address);
            const miner2Pending = await escrow.getMinerPending(miner2.address);
            
            expect(miner1Pending).to.be.gt(0);
            expect(miner2Pending).to.be.gt(0);
        });
        
        it("Should reject batch with mismatched lengths", async function () {
            await expect(escrow.connect(operator).submitBatchAttestations(
                [reseller1.address],
                [miner1.address, miner2.address],
                [ethers.parseUnits("100", 18)],
                [ethers.keccak256(ethers.toUtf8Bytes("batch1"))]
            )).to.be.revertedWith("Length mismatch");
        });
    });

    describe("Miner Functions", function () {
        beforeEach(async function () {
            await escrow.connect(reseller1).deposit(ethers.parseUnits("1000", 18));
            
            // Submit attestation to give miner pending payments
            const cost = ethers.parseUnits("100", 18);
            const requestId = ethers.keccak256(ethers.toUtf8Bytes("request1"));
            await escrow.connect(operator).submitServiceAttestation(
                reseller1.address,
                miner1.address,
                cost,
                requestId
            );
        });
        
        it("Should allow miner to withdraw pending payments", async function () {
            const minerBefore = await mockToken.balanceOf(miner1.address);
            const pending = await escrow.getMinerPending(miner1.address);
            
            await expect(escrow.connect(miner1).withdrawMinerPayments())
                .to.emit(escrow, "MinerWithdrawal")
                .withArgs(miner1.address, pending);
            
            const minerAfter = await mockToken.balanceOf(miner1.address);
            expect(minerAfter - minerBefore).to.equal(pending);
        });
        
        it("Should clear pending after withdrawal", async function () {
            await escrow.connect(miner1).withdrawMinerPayments();
            expect(await escrow.getMinerPending(miner1.address)).to.equal(0);
        });
        
        it("Should reject withdrawal with no pending", async function () {
            await expect(escrow.connect(miner2).withdrawMinerPayments())
                .to.be.revertedWithCustomError(escrow, "NoPendingPayments");
        });
    });

    describe("View Functions", function () {
        it("Should check if attestation is processed", async function () {
            await escrow.connect(reseller1).deposit(ethers.parseUnits("1000", 18));
            
            const cost = ethers.parseUnits("100", 18);
            const requestId = ethers.keccak256(ethers.toUtf8Bytes("request1"));
            
            expect(await escrow.isAttestationProcessed(
                reseller1.address, miner1.address, cost, requestId
            )).to.be.false;
            
            await escrow.connect(operator).submitServiceAttestation(
                reseller1.address, miner1.address, cost, requestId
            );
            
            expect(await escrow.isAttestationProcessed(
                reseller1.address, miner1.address, cost, requestId
            )).to.be.true;
        });
        
        it("Should return correct statistics", async function () {
            await escrow.connect(reseller1).deposit(ethers.parseUnits("100", 18));
            
            const stats = await escrow.getStatistics();
            expect(stats._totalDeposits).to.equal(ethers.parseUnits("100", 18));
        });
    });

    describe("Upgradeability", function () {
        it("Should upgrade to V3 successfully", async function () {
            const KubeTEEEscrowV3 = await ethers.getContractFactory("KubeTEEEscrow");
            const upgraded = await upgrades.upgradeProxy(await escrow.getAddress(), KubeTEEEscrowV3);
            expect(await upgraded.getAddress()).to.equal(await escrow.getAddress());
        });
        
        it("Should preserve state after upgrade", async function () {
            await escrow.connect(reseller1).deposit(ethers.parseUnits("100", 18));
            
            const KubeTEEEscrowV3 = await ethers.getContractFactory("KubeTEEEscrow");
            const upgraded = await upgrades.upgradeProxy(await escrow.getAddress(), KubeTEEEscrowV3);
            
            expect(await upgraded.getResellerBalance(reseller1.address)).to.equal(ethers.parseUnits("100", 18));
        });
    });
});
