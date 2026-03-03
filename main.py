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
        int bps = Math.max(0, Math.min(feeBps, 10_000));
        return amountWei.multiply(BigInteger.valueOf(bps)).divide(BigInteger.valueOf(10_000));
    }

    static BigInteger projectNetAfterFee(BigInteger amountWei, int feeBps) {
        return DODWeiMath.subSafe(amountWei == null ? BigInteger.ZERO : amountWei, projectFee(amountWei, feeBps));
    }

    static String derivePodIdHex(String curator, String seedHex, long salt) {
        if (curator == null) curator = "0x0000000000000000000000000000000000000000";
        if (seedHex == null) seedHex = "0x0000000000000000000000000000000000000000000000000000000000000000";
        String payload = curator + seedHex + salt;
        return "0x" + Integer.toHexString(payload.hashCode() & 0x7FFF_FFFF) + Long.toHexString(salt);
    }
}

// -----------------------------------------------------------------------------
// ENCODING UTILS (hex / bytes)
// -----------------------------------------------------------------------------

final class DODEncodingUtils {
    private static final String HEX = "0123456789abcdef";

    static String toHex(byte[] bytes) {
        if (bytes == null) return "";
        StringBuilder sb = new StringBuilder(bytes.length * 2);
        for (byte b : bytes) {
            sb.append(HEX.charAt((b >> 4) & 0x0f)).append(HEX.charAt(b & 0x0f));
        }
        return "0x" + sb.toString();
    }

    static String padPodId(String podId) {
        if (podId == null) return "0x" + "0".repeat(64);
        String s = podId.trim().toLowerCase();
        if (s.startsWith("0x")) s = s.substring(2);
        if (s.length() >= 64) return "0x" + s.substring(s.length() - 64);
        return "0x" + "0".repeat(64 - s.length()) + s;
    }

    static String padAddressTo40(String address) {
        if (address == null) return "0x0000000000000000000000000000000000000000";
        String s = address.trim().toLowerCase();
        if (s.startsWith("0x")) s = s.substring(2);
        if (s.length() >= 40) return "0x" + s.substring(s.length() - 40);
        return "0x" + "0".repeat(40 - s.length()) + s;
    }
}

// -----------------------------------------------------------------------------
// GAS ESTIMATOR (off-chain)
// -----------------------------------------------------------------------------

final class DODGasEstimator {
    static final long BASE_SPAWN_POD = 180_000L;
    static final long BASE_ALLOCATE = 80_000L;
    static final long BASE_PULL_STAKE = 65_000L;
    static final long BASE_BATCH_ALLOCATE = 120_000L;
    static final long BASE_SET_FEE_BPS = 45_000L;
    static final long BASE_SET_COOLDOWN = 40_000L;
    static final long PER_POD_SLOT = 25_000L;
    static final long PER_ALLOCATOR_SLOT = 20_000L;

    static long estimateSpawnPod() {
        return BASE_SPAWN_POD + PER_POD_SLOT * 8;
    }

    static long estimateAllocate() {
        return BASE_ALLOCATE + PER_POD_SLOT * 2;
    }

    static long estimatePullStake() {
        return BASE_PULL_STAKE + PER_POD_SLOT * 2;
    }

    static long estimateBatchAllocate(int podCount) {
        return BASE_BATCH_ALLOCATE + (long) podCount * (PER_POD_SLOT + PER_ALLOCATOR_SLOT);
    }

    static Map<String, Long> estimateAll() {
        Map<String, Long> m = new HashMap<>();
        m.put("spawnPod", estimateSpawnPod());
        m.put("allocate", estimateAllocate());
        m.put("pullStake", estimatePullStake());
        m.put("batchAllocate_4", estimateBatchAllocate(4));
        m.put("setGlobalFeeBps", BASE_SET_FEE_BPS);
        m.put("setCooldownBlocks", BASE_SET_COOLDOWN);
        return m;
    }
}

// -----------------------------------------------------------------------------
// RUNBOOK (procedures)
// -----------------------------------------------------------------------------

final class DODRunbook {
    static final int STEP_SPAWN_POD = 1;
    static final int STEP_WHITELIST_ALLOCATOR = 2;
    static final int STEP_ALLOCATE = 3;
    static final int STEP_PULL_STAKE = 4;
    static final int STEP_SET_FEE = 5;
    static final int STEP_PAUSE_LATTICE = 6;

    static String describeStep(int step) {
        switch (step) {
            case STEP_SPAWN_POD: return "Spawn pod (curator only)";
            case STEP_WHITELIST_ALLOCATOR: return "Whitelist allocator (curator only)";
            case STEP_ALLOCATE: return "Allocate wei to pod (whitelisted allocator or curator)";
            case STEP_PULL_STAKE: return "Pull stake from pod (after cooldown)";
            case STEP_SET_FEE: return "Set global fee bps (curator only)";
            case STEP_PAUSE_LATTICE: return "Pause/unpause lattice (curator only)";
            default: return "Unknown step";
        }
    }

    static String runbookSummary() {
        return "DOD Runbook: 1=SpawnPod 2=WhitelistAllocator 3=Allocate 4=PullStake 5=SetFee 6=PauseLattice.";
    }
}

// -----------------------------------------------------------------------------
// REPORT (CSV / text)
// -----------------------------------------------------------------------------

final class DODReport {
    static String toCsvLine(String... cells) {
        StringBuilder sb = new StringBuilder();
        for (int i = 0; i < cells.length; i++) {
            if (i > 0) sb.append(",");
            String c = cells[i] != null ? cells[i] : "";
            if (c.contains(",") || c.contains("\"") || c.contains("\n")) {
                sb.append("\"").append(c.replace("\"", "\"\"")).append("\"");
            } else sb.append(c);
        }
        return sb.toString();
    }

    static List<String> buildPodCsv(List<DODPodInfo> pods) {
        List<String> lines = new ArrayList<>();
        lines.add(toCsvLine("podIdHex", "curator", "riskTier", "totalStakeWei", "minStakeWei", "maxStakeWei", "frozen", "exists"));
        for (DODPodInfo p : pods) {
            lines.add(toCsvLine(p.getPodIdHex(), p.getCurator(), String.valueOf(p.getRiskTier()),
                p.getTotalStakeWei().toString(), p.getMinStakeWei().toString(), p.getMaxStakeWei().toString(),
                String.valueOf(p.isFrozen()), String.valueOf(p.isExists())));
        }
        return lines;
    }

    static String buildSummaryText(DODGlobalStats stats) {
        return String.format("DOD_DenOfDegens | pods=%d feeBps=%d cooldown=%d allocated=%s pulled=%s net=%s",
            stats.getPodCount(), stats.getGlobalFeeBps(), stats.getCooldownBlocks(),
            stats.getTotalAllocatedWei(), stats.getTotalPulledWei(), stats.getNetStakeWei());
    }
}

// -----------------------------------------------------------------------------
// MAIN: DEN OF DEGENS (MoonCapII simulator / client state)
// -----------------------------------------------------------------------------

/**
 * DOD_DenOfDegens — Client and simulator for MoonCapII fund-of-funds.
 * Top degens run pods; allocators route capital; risk tiers 0–5 set how degen you go.
 * All state in one process for simulation; can be wired to EVM RPC for live use.
 */
public final class DOD_DenOfDegens {

    public static final String DOD_VERSION = "1.0.0";
    public static final int MAX_RISK_TIER = 5;
    public static final int MAX_PODS = 200_000;
    public static final int MAX_PODS_PER_CURATOR = 50;
    public static final int MAX_BATCH_ALLOC = 32;
    public static final int DENOM_BPS = 10_000;
    public static final int PERFORMANCE_FEE_BPS_CAP = 2_000;
    public static final int MANAGEMENT_FEE_BPS_CAP = 500;

    private final String topCurator;
    private final String feeCollector;
    private final String emergencyGuard;
    private final String treasury;
    private final long deployBlock;

    private final Map<String, DODPodInfo> pods = new ConcurrentHashMap<>();
    private final List<String> podIdOrder = Collections.synchronizedList(new ArrayList<>());
    private final AtomicLong podCount = new AtomicLong(0);
    private final Map<String, Map<String, BigInteger>> stakeInPod = new ConcurrentHashMap<>();
    private final Map<String, List<String>> stakersInPod = new ConcurrentHashMap<>();
    private final Map<String, BigInteger> totalStakeByAllocator = new ConcurrentHashMap<>();
    private final Map<String, Long> allocatorAllocationCount = new ConcurrentHashMap<>();
    private final Set<String> allocatorWhitelist = ConcurrentHashMap.newKeySet();
    private final AtomicBoolean latticePaused = new AtomicBoolean(false);
    private final AtomicInteger globalFeeBps = new AtomicInteger(25);
    private final AtomicLong cooldownBlocks = new AtomicLong(12);
    private final AtomicReference<BigInteger> totalTreasuryWei = new AtomicReference<>(BigInteger.ZERO);
    private final AtomicReference<BigInteger> totalAllocatedWei = new AtomicReference<>(BigInteger.ZERO);
    private final AtomicReference<BigInteger> totalPulledWei = new AtomicReference<>(BigInteger.ZERO);
    private final AtomicLong allocationCount = new AtomicLong(0);
    private final AtomicLong pullCount = new AtomicLong(0);
    private final Map<String, Map<String, Long>> lastPullBlock = new ConcurrentHashMap<>();
    private final List<DODEventListener> listeners = Collections.synchronizedList(new ArrayList<>());
    private final Object reentrancyLock = new Object();
    private final DODFeeCalculator feeCalculator = new DODFeeCalculator(25);

    public DOD_DenOfDegens() {
        this.topCurator = "0x8B7C9d2E4f6A1b3c5D7e9F0a2B4c6d8E0f1A3B5";
        this.feeCollector = "0x3F1A5b9c2D4e6f8A0b2C4d6E8f0a1B3c5D7e9F1";
        this.emergencyGuard = "0xE4D6f8A0B2c4e6F8a1B3c5d7E9f0A2b4C6d8E0f2";
        this.treasury = "0xA1b3C5d7E9f0A2b4C6d8E0f1A3b5C7d9E1f3A5b7";
        this.deployBlock = System.currentTimeMillis() / 1000L;
        if (!DODAddressValidator.isValid(topCurator)) {
            throw new DODException("DOD_ZERO_ADDR", "Curator address invalid");
        }
    }

    public String getTopCurator() { return topCurator; }
    public String getFeeCollector() { return feeCollector; }
    public String getEmergencyGuard() { return emergencyGuard; }
    public String getTreasury() { return treasury; }
    public long getDeployBlock() { return deployBlock; }
    public int getGlobalFeeBps() { return globalFeeBps.get(); }
    public long getCooldownBlocks() { return cooldownBlocks.get(); }
    public boolean isLatticePaused() { return latticePaused.get(); }
    public BigInteger getTotalTreasuryWei() { return totalTreasuryWei.get(); }
    public BigInteger getTotalAllocatedWei() { return totalAllocatedWei.get(); }
    public BigInteger getTotalPulledWei() { return totalPulledWei.get(); }
    public long getAllocationCount() { return allocationCount.get(); }
    public long getPullCount() { return pullCount.get(); }
    public long getPodCount() { return podCount.get(); }

    private long currentBlock() {
        return System.currentTimeMillis() / 1000L;
    }

    private void requireCurator(String sender) {
        if (sender == null || !DODAddressValidator.normalize(sender).equalsIgnoreCase(DODAddressValidator.normalize(topCurator))) {
            throw new DODException("DOD_NOT_CURATOR", "Caller is not curator");
        }
    }

    private void requireNotPaused() {
        if (latticePaused.get()) throw new DODException("DOD_LATTICE_PAUSED", "Lattice is paused");
    }

    private void requireAllocator(String sender) {
        if (sender == null) throw new DODException("DOD_ZERO_ADDR", "Sender null");
        if (!allocatorWhitelist.contains(DODAddressValidator.normalize(sender)) && !DODAddressValidator.normalize(sender).equalsIgnoreCase(DODAddressValidator.normalize(topCurator))) {
            throw new DODException("DOD_ALLOCATOR_NOT_WHITELISTED", "Allocator not whitelisted");
        }
    }

    public void spawnPod(String sender, String podIdHex, int riskTier, BigInteger minStakeWei, BigInteger maxStakeWei,
                         int performanceFeeBps, int managementFeeBps) {
        requireCurator(sender);
        requireNotPaused();
        synchronized (reentrancyLock) {
            if (podIdHex == null || podIdHex.trim().isEmpty()) throw new DODException("DOD_ZERO_POD", "Pod id zero");
            String id = DODEncodingUtils.padPodId(podIdHex);
            if (pods.containsKey(id)) throw new DODException("DOD_POD_EXISTS", "Pod already exists");
            if (podCount.get() >= MAX_PODS) throw new DODException("DOD_MAX_PODS", "Max pods reached");
            if (riskTier < 0 || riskTier > MAX_RISK_TIER) throw new DODException("DOD_INVALID_RISK_TIER", "Risk tier 0-5");
            if (performanceFeeBps > PERFORMANCE_FEE_BPS_CAP || managementFeeBps > MANAGEMENT_FEE_BPS_CAP) {
                throw new DODException("DOD_INVALID_FEE_BPS", "Fee bps out of range");
            }
            DODPodInfo info = new DODPodInfo(id, topCurator, riskTier, BigInteger.ZERO,
                minStakeWei != null ? minStakeWei : BigInteger.ZERO,
                maxStakeWei != null ? maxStakeWei : BigInteger.ZERO,
                performanceFeeBps, managementFeeBps, currentBlock(), false, true);
            pods.put(id, info);
            podIdOrder.add(id);
            podCount.incrementAndGet();
            long block = currentBlock();
            for (DODEventListener L : listeners) L.onPodSpawned(new DODPodSpawned(id, topCurator, riskTier, minStakeWei, block));
        }
    }

    public void allocate(String sender, String podIdHex, BigInteger amountWei) {
        requireNotPaused();
        requireAllocator(sender);
        if (amountWei == null || amountWei.signum() <= 0) throw new DODException("DOD_ZERO_AMT", "Amount must be positive");
        String id = DODEncodingUtils.padPodId(podIdHex);
        synchronized (reentrancyLock) {
            DODPodInfo info = pods.get(id);
            if (info == null || !info.isExists()) throw new DODException("DOD_POD_MISSING", "Pod not found");
            if (info.isFrozen()) throw new DODException("DOD_POD_FROZEN", "Pod frozen");
            if (info.getMinStakeWei().signum() > 0 && amountWei.compareTo(info.getMinStakeWei()) < 0) {
                throw new DODException("DOD_BELOW_MIN_STAKE", "Below min stake");
            }
            BigInteger fee = feeCalculator.computeFee(amountWei);
            BigInteger toPod = feeCalculator.amountAfterFee(amountWei);
            if (info.getMaxStakeWei().signum() > 0) {
                BigInteger newTotal = info.getTotalStakeWei().add(toPod);
                if (newTotal.compareTo(info.getMaxStakeWei()) > 0) throw new DODException("DOD_ABOVE_MAX_STAKE", "Above max stake");
            }
            stakeInPod.computeIfAbsent(id, k -> new ConcurrentHashMap<>()).merge(sender, toPod, DODWeiMath::addSafe);
            stakersInPod.computeIfAbsent(id, k -> Collections.synchronizedList(new ArrayList<>()));
            if (!stakersInPod.get(id).contains(sender)) stakersInPod.get(id).add(sender);
            totalStakeByAllocator.merge(sender, toPod, DODWeiMath::addSafe);
            allocatorAllocationCount.merge(sender, 1L, Long::sum);
            totalAllocatedWei.updateAndGet(v -> v.add(toPod));
            allocationCount.incrementAndGet();
            DODPodInfo updated = new DODPodInfo(id, info.getCurator(), info.getRiskTier(), info.getTotalStakeWei().add(toPod),
                info.getMinStakeWei(), info.getMaxStakeWei(), info.getPerformanceFeeBps(), info.getManagementFeeBps(),
                info.getCreatedAtBlock(), info.isFrozen(), true);
            pods.put(id, updated);
            long block = currentBlock();
            for (DODEventListener L : listeners) L.onDegenAllocated(new DODDegenAllocated(sender, id, toPod, block));
        }
    }

    public void pullStake(String sender, String podIdHex, BigInteger amountWei) {
        requireNotPaused();
        if (amountWei == null || amountWei.signum() <= 0) throw new DODException("DOD_ZERO_AMT", "Amount must be positive");
        String id = DODEncodingUtils.padPodId(podIdHex);
        synchronized (reentrancyLock) {
            DODPodInfo info = pods.get(id);
            if (info == null || !info.isExists()) throw new DODException("DOD_POD_MISSING", "Pod not found");
            if (info.isFrozen()) throw new DODException("DOD_POD_FROZEN", "Pod frozen");
            BigInteger staked = stakeInPod.getOrDefault(id, Collections.emptyMap()).getOrDefault(sender, BigInteger.ZERO);
            if (staked.compareTo(amountWei) < 0) throw new DODException("DOD_INSUFFICIENT_STAKE", "Insufficient stake");
            Long last = lastPullBlock.getOrDefault(id, Collections.emptyMap()).get(sender);
            if (last != null && last != 0L && (currentBlock() - last) < cooldownBlocks.get()) {
                throw new DODException("DOD_COOLDOWN_ACTIVE", "Cooldown active");
            }
            lastPullBlock.computeIfAbsent(id, k -> new ConcurrentHashMap<>()).put(sender, currentBlock());
            BigInteger newStake = staked.subtract(amountWei);
            stakeInPod.get(id).put(sender, newStake);
            if (newStake.signum() == 0) stakeInPod.get(id).remove(sender);
            totalStakeByAllocator.merge(sender, amountWei.negate(), (a, b) -> a.add(b).max(BigInteger.ZERO));
            totalPulledWei.updateAndGet(v -> v.add(amountWei));
            pullCount.incrementAndGet();
            DODPodInfo updated = new DODPodInfo(id, info.getCurator(), info.getRiskTier(), info.getTotalStakeWei().subtract(amountWei),
                info.getMinStakeWei(), info.getMaxStakeWei(), info.getPerformanceFeeBps(), info.getManagementFeeBps(),
                info.getCreatedAtBlock(), info.isFrozen(), true);
            pods.put(id, updated);
            long block = currentBlock();
            for (DODEventListener L : listeners) L.onStakePulled(new DODStakePulled(sender, id, amountWei, block));
        }
    }

    public void setAllocatorWhitelist(String sender, String allocator, boolean allowed) {
        requireCurator(sender);
        if (allocator == null) throw new DODException("DOD_ZERO_ADDR", "Allocator address null");
        if (allowed) allocatorWhitelist.add(DODAddressValidator.normalize(allocator));
        else allocatorWhitelist.remove(DODAddressValidator.normalize(allocator));
    }

    public void setGlobalFeeBps(String sender, int feeBps) {
        requireCurator(sender);
        if (feeBps < 0 || feeBps > MANAGEMENT_FEE_BPS_CAP) throw new DODException("DOD_INVALID_FEE_BPS", "Fee bps out of range");
        globalFeeBps.set(feeBps);
    }

    public void setCooldownBlocks(String sender, long blocks) {
        requireCurator(sender);
        if (blocks < 0 || blocks > 1_000_000) throw new DODException("DOD_BAD_INDEX", "Cooldown blocks out of range");
        cooldownBlocks.set(blocks);
    }

    public void setLatticePaused(String sender, boolean paused) {
        requireCurator(sender);
        latticePaused.set(paused);
    }

    public boolean podExists(String podIdHex) {
        String id = DODEncodingUtils.padPodId(podIdHex);
        return pods.containsKey(id) && pods.get(id).isExists();
    }

    public DODPodInfo getPodInfo(String podIdHex) {
        String id = DODEncodingUtils.padPodId(podIdHex);
        DODPodInfo info = pods.get(id);
        if (info == null) throw new DODException("DOD_POD_MISSING", "Pod not found");
        return info;
    }

    public BigInteger getStakeInPod(String podIdHex, String allocator) {
        String id = DODEncodingUtils.padPodId(podIdHex);
        return stakeInPod.getOrDefault(id, Collections.emptyMap()).getOrDefault(allocator, BigInteger.ZERO);
    }

    public boolean isAllocatorWhitelisted(String address) {
        if (address == null) return false;
        return allocatorWhitelist.contains(DODAddressValidator.normalize(address)) || DODAddressValidator.normalize(address).equalsIgnoreCase(DODAddressValidator.normalize(topCurator));
    }

    public DODGlobalStats getGlobalStats() {
        return new DODGlobalStats(podCount.get(), deployBlock, globalFeeBps.get(), cooldownBlocks.get(),
            totalTreasuryWei.get(), totalAllocatedWei.get(), totalPulledWei.get(), allocationCount.get(), pullCount.get());
    }

    public List<String> getPodIds() {
        synchronized (podIdOrder) {
            return new ArrayList<>(podIdOrder);
        }
    }

    public List<DODPodInfo> getAllPodInfos() {
        List<DODPodInfo> out = new ArrayList<>();
        for (String id : getPodIds()) {
            if (pods.containsKey(id)) out.add(pods.get(id));
        }
        return out;
    }

    public BigInteger getTotalStakeByAllocator(String allocator) {
        return totalStakeByAllocator.getOrDefault(allocator, BigInteger.ZERO);
    }

    public long getLastPullBlock(String podIdHex, String staker) {
        String id = DODEncodingUtils.padPodId(podIdHex);
        return lastPullBlock.getOrDefault(id, Collections.emptyMap()).getOrDefault(staker, 0L);
    }

    public List<String> getStakersInPod(String podIdHex) {
        String id = DODEncodingUtils.padPodId(podIdHex);
        List<String> list = stakersInPod.get(id);
        return list != null ? new ArrayList<>(list) : List.of();
    }

    public List<String> getPodIdsInRange(int fromIndex, int toIndex) {
        synchronized (podIdOrder) {
            int size = podIdOrder.size();
            if (fromIndex < 0 || toIndex >= size || fromIndex > toIndex) return List.of();
            List<String> out = new ArrayList<>(toIndex - fromIndex + 1);
            for (int i = fromIndex; i <= toIndex; i++) out.add(podIdOrder.get(i));
            return out;
        }
    }

    public Set<String> getAllAllocators() {
        Set<String> out = new HashSet<>(allocatorWhitelist);
        out.add(DODAddressValidator.normalize(topCurator));
        return out;
    }

    public DODPortfolioView getPortfolioView(String staker) {
        List<String> ids = getPodIds();
        List<BigInteger> stakes = getStakerPortfolio(staker, ids);
        BigInteger total = getStakerTotalAcrossPods(staker, ids);
        return new DODPortfolioView(staker, ids, stakes, total);
    }

    public boolean canPull(String podIdHex, String staker) {
        if (getStakeInPod(podIdHex, staker).signum() <= 0) return false;
        DODPodInfo info = pods.get(DODEncodingUtils.padPodId(podIdHex));
        if (info == null || info.isFrozen()) return false;
        long last = getLastPullBlock(podIdHex, staker);
        if (last == 0) return true;
        return (currentBlock() - last) >= cooldownBlocks.get();
    }

