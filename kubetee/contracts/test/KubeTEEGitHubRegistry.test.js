const { ethers, upgrades } = require("hardhat");
const { expect } = require("chai");
require("@nomicfoundation/hardhat-chai-matchers");

describe("KubeTEEGitHubRegistry", function () {
  let registry;
  let owner, validator, nonValidator, otherAccount;
  
  beforeEach(async function () {
    // Get signers
    [owner, validator, nonValidator, otherAccount] = await ethers.getSigners();
    
    // Deploy fresh proxy for each test
    const KubeTEEGitHubRegistry = await ethers.getContractFactory("KubeTEEGitHubRegistry");
    registry = await upgrades.deployProxy(KubeTEEGitHubRegistry, [], { kind: "uups" });
    await registry.waitForDeployment();
  });
  
  describe("Deployment", function () {
    it("Should deploy proxy correctly", async function () {
      const address = await registry.getAddress();
      expect(address).to.be.properAddress;
      expect(address).to.not.equal(ethers.ZeroAddress);
    });
    
    it("Should set owner correctly", async function () {
      expect(await registry.owner()).to.equal(owner.address);
    });
  });
  
  describe("Validator Management", function () {
    describe("addValidator", function () {
      it("Should add validator (owner only)", async function () {
        await registry.addValidator(validator.address);
        expect(await registry.isValidator(validator.address)).to.be.true;
      });
      
      it("Should emit ValidatorAdded event", async function () {
        await expect(registry.addValidator(validator.address))
          .to.emit(registry, "ValidatorAdded")
          .withArgs(validator.address);
      });
      
      it("Should reject non-owner", async function () {
        await expect(
          registry.connect(nonValidator).addValidator(validator.address)
        ).to.be.revertedWithCustomError(registry, "OwnableUnauthorizedAccount");
      });
      
      it("Should reject zero address", async function () {
        await expect(
          registry.addValidator(ethers.ZeroAddress)
        ).to.be.revertedWith("Invalid validator address");
      });
      
      it("Should reject adding existing validator", async function () {
        await registry.addValidator(validator.address);
        await expect(
          registry.addValidator(validator.address)
        ).to.be.revertedWith("Already a validator");
      });
    });
    
    describe("removeValidator", function () {
      beforeEach(async function () {
        // Add validator before testing removal
        await registry.addValidator(validator.address);
      });
      
      it("Should remove validator", async function () {
        await registry.removeValidator(validator.address);
        expect(await registry.isValidator(validator.address)).to.be.false;
      });
      
      it("Should emit ValidatorRemoved event", async function () {
        await expect(registry.removeValidator(validator.address))
          .to.emit(registry, "ValidatorRemoved")
          .withArgs(validator.address);
      });
      
      it("Should reject non-owner", async function () {
        await expect(
          registry.connect(nonValidator).removeValidator(validator.address)
        ).to.be.revertedWithCustomError(registry, "OwnableUnauthorizedAccount");
      });
      
      it("Should reject removing non-validator", async function () {
        await expect(
          registry.removeValidator(otherAccount.address)
        ).to.be.revertedWith("Not a validator");
      });
    });
    
    describe("isValidator", function () {
      it("Should return correct status", async function () {
        // Initially false
        expect(await registry.isValidator(validator.address)).to.be.false;
        
        // True after adding
        await registry.addValidator(validator.address);
        expect(await registry.isValidator(validator.address)).to.be.true;
        
        // False after removing
        await registry.removeValidator(validator.address);
        expect(await registry.isValidator(validator.address)).to.be.false;
      });
    });
  });
  
  describe("GitHub Linking", function () {
    const testHotkey = "5FHneW46xGXgs5mUiveU4sbTyGBzmstUspZC92UhjJM694ty";
    const testGithubUsername = "testuser";
    const testMechanismId = 0; // Bounty system
    
    beforeEach(async function () {
      // Add validator before testing GitHub linking
      await registry.addValidator(validator.address);
    });
    
    it("Should emit GitHubLinked event with correct data", async function () {
      const tx = await registry.connect(validator).linkGitHub(
        testHotkey,
        testMechanismId,
        testGithubUsername
      );
      
      const receipt = await tx.wait();
      
      // Verify event was emitted
      await expect(tx)
        .to.emit(registry, "GitHubLinked");
      
      // Get the event and verify all arguments
      const events = await registry.queryFilter(registry.filters.GitHubLinked(), receipt.blockNumber);
      expect(events.length).to.equal(1);
      
      const event = events[0];
      expect(event.args.hotkey).to.equal(testHotkey);
      expect(event.args.mechanismId).to.equal(testMechanismId);
      expect(event.args.githubUsername).to.equal(testGithubUsername);
      expect(event.args.validator).to.equal(validator.address);
      expect(event.args.timestamp).to.be.greaterThan(0);
    });
    
    it("Should reject non-validator caller", async function () {
      await expect(
        registry.connect(nonValidator).linkGitHub(
          testHotkey,
          testMechanismId,
          testGithubUsername
        )
      ).to.be.revertedWith("Only validators");
    });
    
    it("Should allow multiple links with different mechanism IDs", async function () {
      // Link with mechanism ID 0 (bounty system)
      await expect(
        registry.connect(validator).linkGitHub(testHotkey, 0, testGithubUsername)
      ).to.emit(registry, "GitHubLinked");
      
      // Link with mechanism ID 1 (open source)
      await expect(
        registry.connect(validator).linkGitHub(testHotkey, 1, testGithubUsername)
      ).to.emit(registry, "GitHubLinked");
      
      // Link with mechanism ID 2
      await expect(
        registry.connect(validator).linkGitHub(testHotkey, 2, "anotheruser")
      ).to.emit(registry, "GitHubLinked");
    });
    
    it("Should allow updating existing link (new event)", async function () {
      // Initial link
      await registry.connect(validator).linkGitHub(
        testHotkey,
        testMechanismId,
        testGithubUsername
      );
      
      // Update with new GitHub username
      const newUsername = "updateduser";
      const tx = await registry.connect(validator).linkGitHub(
        testHotkey,
        testMechanismId,
        newUsername
      );
      
      // Verify new event was emitted with updated data
      await expect(tx)
        .to.emit(registry, "GitHubLinked");
      
      const receipt = await tx.wait();
      const events = await registry.queryFilter(registry.filters.GitHubLinked(), receipt.blockNumber);
      expect(events[0].args.githubUsername).to.equal(newUsername);
    });
    
    it("Should reject empty hotkey", async function () {
      await expect(
        registry.connect(validator).linkGitHub("", testMechanismId, testGithubUsername)
      ).to.be.revertedWith("Empty hotkey");
    });
    
    it("Should reject empty GitHub username", async function () {
      await expect(
        registry.connect(validator).linkGitHub(testHotkey, testMechanismId, "")
      ).to.be.revertedWith("Empty GitHub username");
    });
  });
  
  describe("Upgradeability", function () {
    it("Should upgrade to V2 successfully", async function () {
      // Deploy initial proxy
      const proxyAddress = await registry.getAddress();
      
      // Upgrade to V2
      const KubeTEEGitHubRegistryV2 = await ethers.getContractFactory("KubeTEEGitHubRegistryV2");
      const registryV2 = await upgrades.upgradeProxy(proxyAddress, KubeTEEGitHubRegistryV2);
      await registryV2.waitForDeployment();
      
      // Verify proxy address is the same
      expect(await registryV2.getAddress()).to.equal(proxyAddress);
    });
    
    it("V2 should return version '2.0.0'", async function () {
      const proxyAddress = await registry.getAddress();
      
      const KubeTEEGitHubRegistryV2 = await ethers.getContractFactory("KubeTEEGitHubRegistryV2");
      const registryV2 = await upgrades.upgradeProxy(proxyAddress, KubeTEEGitHubRegistryV2);
      await registryV2.waitForDeployment();
      
      expect(await registryV2.version()).to.equal("2.0.0");
    });
    
    it("State should be preserved after upgrade", async function () {
      // Add validator before upgrade
      await registry.addValidator(validator.address);
      expect(await registry.isValidator(validator.address)).to.be.true;
      
      // Record owner before upgrade
      const ownerBefore = await registry.owner();
      
      // Upgrade to V2
      const proxyAddress = await registry.getAddress();
      const KubeTEEGitHubRegistryV2 = await ethers.getContractFactory("KubeTEEGitHubRegistryV2");
      const registryV2 = await upgrades.upgradeProxy(proxyAddress, KubeTEEGitHubRegistryV2);
      await registryV2.waitForDeployment();
      
      // Verify state is preserved
      expect(await registryV2.owner()).to.equal(ownerBefore);
      expect(await registryV2.isValidator(validator.address)).to.be.true;
    });
    
    it("Validators should still work after upgrade", async function () {
      // Add validator before upgrade
      await registry.addValidator(validator.address);
      
      // Upgrade to V2
      const proxyAddress = await registry.getAddress();
      const KubeTEEGitHubRegistryV2 = await ethers.getContractFactory("KubeTEEGitHubRegistryV2");
      const registryV2 = await upgrades.upgradeProxy(proxyAddress, KubeTEEGitHubRegistryV2);
      await registryV2.waitForDeployment();
      
      // Verify validator can still link GitHub accounts
      const testHotkey = "5FHneW46xGXgs5mUiveU4sbTyGBzmstUspZC92UhjJM694ty";
      await expect(
        registryV2.connect(validator).linkGitHub(testHotkey, 0, "testuser")
      ).to.emit(registryV2, "GitHubLinked");
      
      // Verify new validators can be added
      await expect(
        registryV2.addValidator(otherAccount.address)
      ).to.emit(registryV2, "ValidatorAdded");
    });
    
    it("Should reject upgrade from non-owner", async function () {
      const proxyAddress = await registry.getAddress();
      const KubeTEEGitHubRegistryV2 = await ethers.getContractFactory("KubeTEEGitHubRegistryV2", nonValidator);
      
      await expect(
        upgrades.upgradeProxy(proxyAddress, KubeTEEGitHubRegistryV2)
      ).to.be.revertedWithCustomError(registry, "OwnableUnauthorizedAccount");
    });
  });
});
