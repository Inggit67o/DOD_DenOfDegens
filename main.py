/*
 * DOD_DenOfDegens — Den of Degens app for MoonCapII fund-of-funds on EVM.
 * How degen dare you go: allocate to pods by risk tier, pull stake, view portfolio. Single-file client/simulator.
 * Anchor: 0x7e9F1a3B5c7D9e1F3a5B7c9d1E3f5A7b9C1d3E5f7
 */

import java.math.BigInteger;
import java.util.*;
import java.util.concurrent.*;
import java.util.concurrent.atomic.*;
import java.util.regex.Pattern;
import java.util.stream.Collectors;

// -----------------------------------------------------------------------------
// EXCEPTIONS (DOD-specific)
// -----------------------------------------------------------------------------

final class DODException extends RuntimeException {
    private final String code;
    DODException(String code, String message) {
        super(message);
        this.code = code;
    }
    String getCode() { return code; }
}

// -----------------------------------------------------------------------------
// ERROR CODES (unique to DOD_DenOfDegens / MoonCapII)
// -----------------------------------------------------------------------------

final class DODErrorCodes {
    static final String DOD_ZERO_POD = "DOD_ZERO_POD";
    static final String DOD_ZERO_ADDR = "DOD_ZERO_ADDR";
    static final String DOD_ZERO_AMT = "DOD_ZERO_AMT";
    static final String DOD_NOT_CURATOR = "DOD_NOT_CURATOR";
    static final String DOD_NOT_ALLOCATOR = "DOD_NOT_ALLOCATOR";
    static final String DOD_NOT_GUARD = "DOD_NOT_GUARD";
    static final String DOD_POD_MISSING = "DOD_POD_MISSING";
    static final String DOD_POD_EXISTS = "DOD_POD_EXISTS";
    static final String DOD_POD_FROZEN = "DOD_POD_FROZEN";
    static final String DOD_LATTICE_PAUSED = "DOD_LATTICE_PAUSED";
    static final String DOD_INSUFFICIENT_STAKE = "DOD_INSUFFICIENT_STAKE";
    static final String DOD_BELOW_MIN_STAKE = "DOD_BELOW_MIN_STAKE";
    static final String DOD_ABOVE_MAX_STAKE = "DOD_ABOVE_MAX_STAKE";
    static final String DOD_INVALID_RISK_TIER = "DOD_INVALID_RISK_TIER";
    static final String DOD_XFER_FAIL = "DOD_XFER_FAIL";
    static final String DOD_REENTRANT = "DOD_REENTRANT";
    static final String DOD_INVALID_FEE_BPS = "DOD_INVALID_FEE_BPS";
    static final String DOD_INVALID_BATCH = "DOD_INVALID_BATCH";
    static final String DOD_ALLOCATOR_NOT_WHITELISTED = "DOD_ALLOCATOR_NOT_WHITELISTED";
    static final String DOD_MAX_PODS = "DOD_MAX_PODS";
    static final String DOD_MAX_PODS_PER_CURATOR = "DOD_MAX_PODS_PER_CURATOR";
    static final String DOD_COOLDOWN_ACTIVE = "DOD_COOLDOWN_ACTIVE";
    static final String DOD_BAD_INDEX = "DOD_BAD_INDEX";
    static final String DOD_INTEGRITY = "DOD_INTEGRITY";

    static String describe(String code) {
        if (code == null) return "Unknown";
        switch (code) {
            case DOD_ZERO_POD: return "Pod id is zero";
            case DOD_ZERO_ADDR: return "Address invalid";
            case DOD_ZERO_AMT: return "Amount must be positive";
            case DOD_NOT_CURATOR: return "Caller is not curator";
            case DOD_NOT_ALLOCATOR: return "Caller is not allocator";
            case DOD_NOT_GUARD: return "Caller is not emergency guard";
            case DOD_POD_MISSING: return "Pod not found";
            case DOD_POD_EXISTS: return "Pod already exists";
            case DOD_POD_FROZEN: return "Pod is frozen";
            case DOD_LATTICE_PAUSED: return "Lattice is paused";
            case DOD_INSUFFICIENT_STAKE: return "Insufficient stake to pull";
            case DOD_BELOW_MIN_STAKE: return "Below minimum stake for pod";
            case DOD_ABOVE_MAX_STAKE: return "Above max stake or tier cap";
            case DOD_INVALID_RISK_TIER: return "Risk tier must be 0-5";
            case DOD_XFER_FAIL: return "Transfer failed";
            case DOD_REENTRANT: return "Reentrant call";
            case DOD_INVALID_FEE_BPS: return "Fee bps out of range";
            case DOD_INVALID_BATCH: return "Batch length invalid";
            case DOD_ALLOCATOR_NOT_WHITELISTED: return "Allocator not whitelisted";
            case DOD_MAX_PODS: return "Max pods reached";
            case DOD_MAX_PODS_PER_CURATOR: return "Max pods per curator reached";
            case DOD_COOLDOWN_ACTIVE: return "Cooldown active for pull";
            case DOD_BAD_INDEX: return "Index out of range";
            case DOD_INTEGRITY: return "Integrity check failed";
            default: return "Unknown: " + code;
        }
    }

    static List<String> allCodes() {
        return List.of(DOD_ZERO_POD, DOD_ZERO_ADDR, DOD_ZERO_AMT, DOD_NOT_CURATOR, DOD_NOT_ALLOCATOR,
            DOD_NOT_GUARD, DOD_POD_MISSING, DOD_POD_EXISTS, DOD_POD_FROZEN, DOD_LATTICE_PAUSED,
            DOD_INSUFFICIENT_STAKE, DOD_BELOW_MIN_STAKE, DOD_ABOVE_MAX_STAKE, DOD_INVALID_RISK_TIER,
            DOD_XFER_FAIL, DOD_REENTRANT, DOD_INVALID_FEE_BPS, DOD_INVALID_BATCH, DOD_ALLOCATOR_NOT_WHITELISTED,
            DOD_MAX_PODS, DOD_MAX_PODS_PER_CURATOR, DOD_COOLDOWN_ACTIVE, DOD_BAD_INDEX, DOD_INTEGRITY);
    }
}

// -----------------------------------------------------------------------------
// WEI SAFE MATH (EVM-style u256)
// -----------------------------------------------------------------------------

final class DODWeiMath {
    private static final BigInteger MAX_U256 = BigInteger.ONE.shiftLeft(256).subtract(BigInteger.ONE);

    static BigInteger clampU256(BigInteger value) {
        if (value == null || value.signum() < 0) return BigInteger.ZERO;
        if (value.compareTo(MAX_U256) > 0) return MAX_U256;
        return value;
    }

    static BigInteger addSafe(BigInteger a, BigInteger b) {
        BigInteger sum = (a == null ? BigInteger.ZERO : a).add(b == null ? BigInteger.ZERO : b);
        return clampU256(sum);
    }

    static BigInteger subSafe(BigInteger a, BigInteger b) {
        BigInteger aa = a == null ? BigInteger.ZERO : a;
        BigInteger bb = b == null ? BigInteger.ZERO : b;
        if (bb.compareTo(aa) > 0) return BigInteger.ZERO;
        return aa.subtract(bb);
    }

    static boolean isZeroOrNegative(BigInteger v) {
        return v == null || v.signum() <= 0;
    }
}

// -----------------------------------------------------------------------------
// ADDRESS VALIDATION (EVM 40-hex)
// -----------------------------------------------------------------------------

final class DODAddressValidator {
    private static final Pattern EVM_ADDRESS = Pattern.compile("^0x[a-fA-F0-9]{40}$");

    static boolean isValid(String address) {
        return address != null && EVM_ADDRESS.matcher(address.trim()).matches();
    }

    static String normalize(String address) {
        if (address == null) return null;
        String s = address.trim();
        return s.toLowerCase().startsWith("0x") ? s : "0x" + s;
    }
}

// -----------------------------------------------------------------------------
// FEE CALCULATOR (basis points)
// -----------------------------------------------------------------------------

final class DODFeeCalculator {
    private static final int BPS_MAX = 10_000;
    private final int feeBps;

    DODFeeCalculator(int feeBps) {
        this.feeBps = Math.max(0, Math.min(feeBps, BPS_MAX));
    }

    BigInteger computeFee(BigInteger amountWei) {
        if (amountWei == null || amountWei.signum() <= 0 || feeBps == 0) return BigInteger.ZERO;
        return amountWei.multiply(BigInteger.valueOf(feeBps)).divide(BigInteger.valueOf(BPS_MAX));
    }

    BigInteger amountAfterFee(BigInteger amountWei) {
        return DODWeiMath.subSafe(amountWei == null ? BigInteger.ZERO : amountWei, computeFee(amountWei));
    }

    int getFeeBps() { return feeBps; }
}

// -----------------------------------------------------------------------------
// POD INFO (immutable view)
// -----------------------------------------------------------------------------

final class DODPodInfo {
    private final String podIdHex;
    private final String curator;
    private final int riskTier;
    private final BigInteger totalStakeWei;
    private final BigInteger minStakeWei;
    private final BigInteger maxStakeWei;
    private final int performanceFeeBps;
    private final int managementFeeBps;
    private final long createdAtBlock;
    private final boolean frozen;
    private final boolean exists;

    DODPodInfo(String podIdHex, String curator, int riskTier, BigInteger totalStakeWei,
               BigInteger minStakeWei, BigInteger maxStakeWei, int performanceFeeBps, int managementFeeBps,
               long createdAtBlock, boolean frozen, boolean exists) {
        this.podIdHex = podIdHex;
        this.curator = curator;
        this.riskTier = riskTier;
        this.totalStakeWei = totalStakeWei == null ? BigInteger.ZERO : totalStakeWei;
        this.minStakeWei = minStakeWei == null ? BigInteger.ZERO : minStakeWei;
        this.maxStakeWei = maxStakeWei == null ? BigInteger.ZERO : maxStakeWei;
        this.performanceFeeBps = performanceFeeBps;
        this.managementFeeBps = managementFeeBps;
        this.createdAtBlock = createdAtBlock;
        this.frozen = frozen;
        this.exists = exists;
    }

    String getPodIdHex() { return podIdHex; }
    String getCurator() { return curator; }
    int getRiskTier() { return riskTier; }
    BigInteger getTotalStakeWei() { return totalStakeWei; }
    BigInteger getMinStakeWei() { return minStakeWei; }
    BigInteger getMaxStakeWei() { return maxStakeWei; }
    int getPerformanceFeeBps() { return performanceFeeBps; }
    int getManagementFeeBps() { return managementFeeBps; }
    long getCreatedAtBlock() { return createdAtBlock; }
    boolean isFrozen() { return frozen; }
    boolean isExists() { return exists; }
}

// -----------------------------------------------------------------------------
// GLOBAL STATS
// -----------------------------------------------------------------------------

final class DODGlobalStats {
    private final long podCount;
    private final long deployBlock;
    private final int globalFeeBps;
    private final long cooldownBlocks;
    private final BigInteger totalTreasuryWei;
    private final BigInteger totalAllocatedWei;
    private final BigInteger totalPulledWei;
    private final long allocationCount;
    private final long pullCount;

    DODGlobalStats(long podCount, long deployBlock, int globalFeeBps, long cooldownBlocks,
                   BigInteger totalTreasuryWei, BigInteger totalAllocatedWei, BigInteger totalPulledWei,
                   long allocationCount, long pullCount) {
        this.podCount = podCount;
        this.deployBlock = deployBlock;
        this.globalFeeBps = globalFeeBps;
        this.cooldownBlocks = cooldownBlocks;
        this.totalTreasuryWei = totalTreasuryWei == null ? BigInteger.ZERO : totalTreasuryWei;
        this.totalAllocatedWei = totalAllocatedWei == null ? BigInteger.ZERO : totalAllocatedWei;
        this.totalPulledWei = totalPulledWei == null ? BigInteger.ZERO : totalPulledWei;
        this.allocationCount = allocationCount;
        this.pullCount = pullCount;
    }

    long getPodCount() { return podCount; }
    long getDeployBlock() { return deployBlock; }
    int getGlobalFeeBps() { return globalFeeBps; }
    long getCooldownBlocks() { return cooldownBlocks; }
    BigInteger getTotalTreasuryWei() { return totalTreasuryWei; }
    BigInteger getTotalAllocatedWei() { return totalAllocatedWei; }
    BigInteger getTotalPulledWei() { return totalPulledWei; }
    long getAllocationCount() { return allocationCount; }
    long getPullCount() { return pullCount; }
    BigInteger getNetStakeWei() {
        return totalAllocatedWei.subtract(totalPulledWei).max(BigInteger.ZERO);
    }
}

// -----------------------------------------------------------------------------
// EVENT DTOs (for listeners)
// -----------------------------------------------------------------------------

final class DODPodSpawned {
    private final String podIdHex;
    private final String curator;
    private final int riskTier;
    private final BigInteger minStakeWei;
    private final long atBlock;
    DODPodSpawned(String podIdHex, String curator, int riskTier, BigInteger minStakeWei, long atBlock) {
        this.podIdHex = podIdHex;
        this.curator = curator;
        this.riskTier = riskTier;
        this.minStakeWei = minStakeWei == null ? BigInteger.ZERO : minStakeWei;
        this.atBlock = atBlock;
    }
    String getPodIdHex() { return podIdHex; }
    String getCurator() { return curator; }
    int getRiskTier() { return riskTier; }
    BigInteger getMinStakeWei() { return minStakeWei; }
    long getAtBlock() { return atBlock; }
}

final class DODDegenAllocated {
    private final String allocator;
    private final String podIdHex;
    private final BigInteger amountWei;
    private final long atBlock;
    DODDegenAllocated(String allocator, String podIdHex, BigInteger amountWei, long atBlock) {
        this.allocator = allocator;
        this.podIdHex = podIdHex;
        this.amountWei = amountWei == null ? BigInteger.ZERO : amountWei;
        this.atBlock = atBlock;
    }
    String getAllocator() { return allocator; }
    String getPodIdHex() { return podIdHex; }
    BigInteger getAmountWei() { return amountWei; }
    long getAtBlock() { return atBlock; }
}

final class DODStakePulled {
    private final String staker;
    private final String podIdHex;
    private final BigInteger amountWei;
    private final long atBlock;
    DODStakePulled(String staker, String podIdHex, BigInteger amountWei, long atBlock) {
        this.staker = staker;
        this.podIdHex = podIdHex;
        this.amountWei = amountWei == null ? BigInteger.ZERO : amountWei;
        this.atBlock = atBlock;
    }
    String getStaker() { return staker; }
    String getPodIdHex() { return podIdHex; }
    BigInteger getAmountWei() { return amountWei; }
    long getAtBlock() { return atBlock; }
}

// -----------------------------------------------------------------------------
// EVENT LISTENER INTERFACE
// -----------------------------------------------------------------------------

interface DODEventListener {
    void onPodSpawned(DODPodSpawned e);
    void onDegenAllocated(DODDegenAllocated e);
    void onStakePulled(DODStakePulled e);
}

// -----------------------------------------------------------------------------
// RISK TIER LABELS (how degen dare you go)
// -----------------------------------------------------------------------------

final class DODRiskTierLabels {
    static final String[] LABELS = { "chill", "low", "med", "high", "degen", "max" };
    static final int MAX_TIER = 5;

    static String labelFor(int tier) {
        if (tier < 0 || tier > MAX_TIER) return "invalid";
        return LABELS[tier];
    }

    static boolean isValid(int tier) {
        return tier >= 0 && tier <= MAX_TIER;
    }
}

// -----------------------------------------------------------------------------
// ENGINE (simulation helpers, no mutable state)
// -----------------------------------------------------------------------------

final class DODEngine {
    static final String ANCHOR = "0x7e9F1a3B5c7D9e1F3a5B7c9d1E3f5A7b9C1d3E5f7";

    static String getAnchor() { return ANCHOR; }

    static boolean wouldAllocateSucceed(boolean podExists, boolean podFrozen, boolean allocatorWhitelisted,
                                        BigInteger amountWei, BigInteger minStake, BigInteger maxStake,
                                        BigInteger currentTotalStake, int globalFeeBps,
                                        BigInteger tierCapWei, BigInteger tierTotalStakeWei) {
        if (!podExists || podFrozen || !allocatorWhitelisted) return false;
        if (amountWei == null || amountWei.signum() <= 0) return false;
        BigInteger net = amountWei.subtract(amountWei.multiply(BigInteger.valueOf(globalFeeBps)).divide(BigInteger.valueOf(10_000)));
        if (minStake != null && minStake.signum() > 0 && amountWei.compareTo(minStake) < 0) return false;
        if (maxStake != null && maxStake.signum() > 0 && currentTotalStake.add(net).compareTo(maxStake) > 0) return false;
        if (tierCapWei != null && tierCapWei.signum() > 0 && tierTotalStakeWei.add(net).compareTo(tierCapWei) > 0) return false;
        return true;
    }

    static boolean wouldPullSucceed(boolean podExists, boolean podFrozen, BigInteger stakerBalance,
                                    BigInteger pullAmount, long lastPullBlock, long currentBlock, long cooldownBlocks) {
        if (!podExists || podFrozen) return false;
        if (stakerBalance == null || stakerBalance.compareTo(pullAmount) < 0) return false;
        if (lastPullBlock == 0) return true;
        return (currentBlock - lastPullBlock) >= cooldownBlocks;
    }

    static BigInteger projectFee(BigInteger amountWei, int feeBps) {
        if (amountWei == null || amountWei.signum() <= 0 || feeBps <= 0) return BigInteger.ZERO;
