// Shared types for the PayMesh JS/TS SDK — mirror the Python SDK shapes.
export const MOTES_PER_CSPR = 1_000_000_000;
export function motesToCspr(motes) {
    return Number(motes) / MOTES_PER_CSPR;
}
export function csprToMotes(cspr) {
    return Math.floor(cspr * MOTES_PER_CSPR);
}
