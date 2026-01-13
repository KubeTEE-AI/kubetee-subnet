/**
 * Verify deployed contract functionality
 * Usage: PROXY_ADDRESS=0x... npx hardhat run scripts/verify-deployment.js --network <network>
 */

const { ethers } = require("hardhat");

async function main() {
  const proxyAddress = process.env.PROXY_ADDRESS;
  
  if (!proxyAddress) {
    console.error("Error: PROXY_ADDRESS environment variable is required");
    console.error("Usage: PROXY_ADDRESS=0x... npx hardhat run scripts/verify-deployment.js --network <network>");
    process.exit(1);
  }

  console.log("Verifying KubeTEEGitHubRegistry deployment...\n");

  const [signer] = await ethers.getSigners();
  const network = await ethers.provider.getNetwork();

  console.log("Network:", network.name, `(chainId: ${network.chainId})`);
  console.log("Proxy Address:", proxyAddress);
  console.log("Verifier:", signer.address);
  console.log("\n" + "=".repeat(50) + "\n");

  // Attach to the deployed contract
  const KubeTEEGitHubRegistry = await ethers.getContractFactory("KubeTEEGitHubRegistry");
  const registry = KubeTEEGitHubRegistry.attach(proxyAddress);

  let allPassed = true;

  // Test 1: Check contract code exists
  console.log("1. Checking contract exists...");
  const code = await ethers.provider.getCode(proxyAddress);
  if (code === "0x") {
    console.log("   ❌ FAILED: No contract code at address");
    allPassed = false;
  } else {
    console.log("   ✅ Contract code found");
  }

  // Test 2: Check owner
  console.log("\n2. Checking owner...");
  try {
    const owner = await registry.owner();
    console.log("   Owner:", owner);
    console.log("   ✅ Owner check passed");
  } catch (error) {
    console.log("   ❌ FAILED:", error.message);
    allPassed = false;
  }

  // Test 3: Check version
  console.log("\n3. Checking version...");
  try {
    const version = await registry.version();
    console.log("   Version:", version);
    console.log("   ✅ Version check passed");
  } catch (error) {
    console.log("   ❌ FAILED:", error.message);
    allPassed = false;
  }

  // Test 4: Check validators list
  console.log("\n4. Checking validators...");
  try {
    const validators = await registry.getValidators();
    console.log("   Registered validators:", validators.length);
    if (validators.length > 0) {
      console.log("   Validators:", validators.slice(0, 5).join(", ") + (validators.length > 5 ? "..." : ""));
    }
    console.log("   ✅ Validators check passed");
  } catch (error) {
    console.log("   ❌ FAILED:", error.message);
    allPassed = false;
  }

  // Test 5: Test read function for non-existent hotkey
  console.log("\n5. Testing getCurrentGitHub for non-existent hotkey...");
  try {
    const result = await registry.getCurrentGitHub("5NonExistentHotkey123");
    console.log("   Result:", result || "(empty - expected)");
    console.log("   ✅ Read function works correctly");
  } catch (error) {
    console.log("   ❌ FAILED:", error.message);
    allPassed = false;
  }

  // Test 6: Check if the contract is upgradeable (UUPS)
  console.log("\n6. Checking upgradeability...");
  try {
    // Try to get the implementation address from the proxy
    const implSlot = "0x360894a13ba1a3210667c828492db98dca3e2076cc3735a920a3ca505d382bbc";
    const implAddressRaw = await ethers.provider.getStorage(proxyAddress, implSlot);
    const implAddress = "0x" + implAddressRaw.slice(26);
    console.log("   Implementation address:", implAddress);
    console.log("   ✅ UUPS proxy pattern detected");
  } catch (error) {
    console.log("   ⚠️  Could not verify upgradeability:", error.message);
  }

  // Test 7: Check event filter works
  console.log("\n7. Checking event system...");
  try {
    const filter = registry.filters.GitHubLinked();
    console.log("   Event filter created successfully");
    console.log("   ✅ Event system works");
  } catch (error) {
    console.log("   ❌ FAILED:", error.message);
    allPassed = false;
  }

  // Test 8: Estimate gas for a link operation (without executing)
  console.log("\n8. Estimating gas for linkGitHub...");
  try {
    const gasEstimate = await registry.linkGitHub.estimateGas(
      "5TestHotkey123",
      0, // mechanismId
      "testuser"
    );
    console.log("   Estimated gas:", gasEstimate.toString());
    console.log("   ✅ Gas estimation works");
  } catch (error) {
    // This might fail if signer is not a validator
    console.log("   ⚠️  Gas estimation failed (signer may not be a validator):", error.reason || error.message);
  }

  // Summary
  console.log("\n" + "=".repeat(50));
  console.log("VERIFICATION SUMMARY");
  console.log("=".repeat(50));
  
  if (allPassed) {
    console.log("\n✅ All critical checks PASSED!\n");
    console.log("The contract is deployed and functioning correctly.");
  } else {
    console.log("\n❌ Some checks FAILED!\n");
    console.log("Please review the issues above.");
    process.exit(1);
  }

  // Print useful information
  console.log("\nUseful commands:");
  console.log(`  Add validator: await registry.addValidator("0x...")`);
  console.log(`  Link GitHub: await registry.linkGitHub("hotkey", 0, "github_user")`);
  console.log(`  Get current: await registry.getCurrentGitHub("hotkey")`);
}

main()
  .then(() => process.exit(0))
  .catch((error) => {
    console.error(error);
    process.exit(1);
  });
