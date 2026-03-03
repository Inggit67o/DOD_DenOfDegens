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
