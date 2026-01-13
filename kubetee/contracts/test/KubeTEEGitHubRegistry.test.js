const { ethers, upgrades } = require("hardhat");
const { expect } = require("chai");
require("@nomicfoundation/hardhat-chai-matchers");

describe("KubeTEEGitHubRegistry", function () {
  let registry;
  let admin, operator, nonOperator, otherAccount;

  beforeEach(async function () {
    // Get signers - admin is the deployer/owner
    [admin, operator, nonOperator, otherAccount] = await ethers.getSigners();

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

    it("Should set admin (owner) correctly", async function () {
      expect(await registry.owner()).to.equal(admin.address);
    });
  });

  describe("Operator Management", function () {
    describe("addOperator", function () {
      it("Should add operator (admin only)", async function () {
        await registry.addOperator(operator.address);
        expect(await registry.isOperator(operator.address)).to.be.true;
      });

      it("Should emit OperatorAdded event", async function () {
        await expect(registry.addOperator(operator.address))
          .to.emit(registry, "OperatorAdded")
          .withArgs(operator.address);
      });

      it("Should reject non-admin", async function () {
        await expect(
          registry.connect(nonOperator).addOperator(operator.address)
        ).to.be.revertedWithCustomError(registry, "OwnableUnauthorizedAccount");
      });

      it("Should reject zero address", async function () {
        await expect(
          registry.addOperator(ethers.ZeroAddress)
        ).to.be.revertedWith("Invalid operator address");
      });

      it("Should reject adding existing operator", async function () {
        await registry.addOperator(operator.address);
        await expect(
          registry.addOperator(operator.address)
        ).to.be.revertedWith("Already an operator");
      });
    });

    describe("removeOperator", function () {
      beforeEach(async function () {
        // Add operator before testing removal
        await registry.addOperator(operator.address);
      });

      it("Should remove operator", async function () {
        await registry.removeOperator(operator.address);
        expect(await registry.isOperator(operator.address)).to.be.false;
      });

      it("Should emit OperatorRemoved event", async function () {
        await expect(registry.removeOperator(operator.address))
          .to.emit(registry, "OperatorRemoved")
          .withArgs(operator.address);
      });

      it("Should reject non-admin", async function () {
        await expect(
          registry.connect(nonOperator).removeOperator(operator.address)
        ).to.be.revertedWithCustomError(registry, "OwnableUnauthorizedAccount");
      });

      it("Should reject removing non-operator", async function () {
        await expect(
          registry.removeOperator(otherAccount.address)
        ).to.be.revertedWith("Not an operator");
      });
    });

    describe("isOperator", function () {
      it("Should return correct status", async function () {
        // Initially false
        expect(await registry.isOperator(operator.address)).to.be.false;

        // True after adding
        await registry.addOperator(operator.address);
        expect(await registry.isOperator(operator.address)).to.be.true;

        // False after removing
        await registry.removeOperator(operator.address);
        expect(await registry.isOperator(operator.address)).to.be.false;
      });
    });
  });

  describe("GitHub Linking", function () {
    const testHotkey = "5FHneW46xGXgs5mUiveU4sbTyGBzmstUspZC92UhjJM694ty";
    const testGithubUsername = "testuser";
    const testMechanismId = 0; // Bounty system

    beforeEach(async function () {
      // Add operator before testing GitHub linking
      await registry.addOperator(operator.address);
    });

    it("Should emit GitHubLinked event with correct data", async function () {
      const tx = await registry.connect(operator).linkGitHub(
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
      expect(event.args.operator).to.equal(operator.address);
      expect(event.args.timestamp).to.be.greaterThan(0);
    });

    it("Should reject non-operator caller", async function () {
      await expect(
        registry.connect(nonOperator).linkGitHub(
          testHotkey,
          testMechanismId,
          testGithubUsername
        )
      ).to.be.revertedWith("Only operators");
    });

    it("Should allow multiple links with different mechanism IDs", async function () {
      // Link with mechanism ID 0 (bounty system)
      await expect(
        registry.connect(operator).linkGitHub(testHotkey, 0, testGithubUsername)
      ).to.emit(registry, "GitHubLinked");

      // Link with mechanism ID 1 (open source)
      await expect(
        registry.connect(operator).linkGitHub(testHotkey, 1, testGithubUsername)
      ).to.emit(registry, "GitHubLinked");

      // Link with mechanism ID 2
      await expect(
        registry.connect(operator).linkGitHub(testHotkey, 2, "anotheruser")
      ).to.emit(registry, "GitHubLinked");
    });

    it("Should allow updating existing link (new event)", async function () {
      // Initial link
      await registry.connect(operator).linkGitHub(
        testHotkey,
        testMechanismId,
        testGithubUsername
      );

      // Update with new GitHub username
      const newUsername = "updateduser";
      const tx = await registry.connect(operator).linkGitHub(
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
        registry.connect(operator).linkGitHub("", testMechanismId, testGithubUsername)
      ).to.be.revertedWith("Empty hotkey");
    });

    it("Should reject empty GitHub username", async function () {
      await expect(
        registry.connect(operator).linkGitHub(testHotkey, testMechanismId, "")
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
      // Add operator before upgrade
      await registry.addOperator(operator.address);
      expect(await registry.isOperator(operator.address)).to.be.true;

      // Record admin before upgrade
      const adminBefore = await registry.owner();

      // Upgrade to V2
      const proxyAddress = await registry.getAddress();
      const KubeTEEGitHubRegistryV2 = await ethers.getContractFactory("KubeTEEGitHubRegistryV2");
      const registryV2 = await upgrades.upgradeProxy(proxyAddress, KubeTEEGitHubRegistryV2);
      await registryV2.waitForDeployment();

      // Verify state is preserved
      expect(await registryV2.owner()).to.equal(adminBefore);
      expect(await registryV2.isOperator(operator.address)).to.be.true;
    });

    it("Operators should still work after upgrade", async function () {
      // Add operator before upgrade
      await registry.addOperator(operator.address);

      // Upgrade to V2
      const proxyAddress = await registry.getAddress();
      const KubeTEEGitHubRegistryV2 = await ethers.getContractFactory("KubeTEEGitHubRegistryV2");
      const registryV2 = await upgrades.upgradeProxy(proxyAddress, KubeTEEGitHubRegistryV2);
      await registryV2.waitForDeployment();

      // Verify operator can still link GitHub accounts
      const testHotkey = "5FHneW46xGXgs5mUiveU4sbTyGBzmstUspZC92UhjJM694ty";
      await expect(
        registryV2.connect(operator).linkGitHub(testHotkey, 0, "testuser")
      ).to.emit(registryV2, "GitHubLinked");

      // Verify new operators can be added
      await expect(
        registryV2.addOperator(otherAccount.address)
      ).to.emit(registryV2, "OperatorAdded");
    });

    it("Should reject upgrade from non-admin", async function () {
      const proxyAddress = await registry.getAddress();
      const KubeTEEGitHubRegistryV2 = await ethers.getContractFactory("KubeTEEGitHubRegistryV2", nonOperator);

      await expect(
        upgrades.upgradeProxy(proxyAddress, KubeTEEGitHubRegistryV2)
      ).to.be.revertedWithCustomError(registry, "OwnableUnauthorizedAccount");
    });
  });
});
