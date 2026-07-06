// Casper Ed25519 account handling for x402 payment signatures.
// A Casper Ed25519 account public key = 0x01 tag + 32-byte raw pubkey, hex.
// Uses @noble/ed25519 (pure JS, no native deps, works in browser & Node).
import * as ed from "@noble/ed25519";
import { sha512 } from "@noble/hashes/sha512";
// @noble/ed25519 v2 requires a SHA-512 backend to be wired in.
const _sha512Sync = (...msgs) => sha512(ed.etc.concatBytes(...msgs));
ed.etc.sha512Sync = _sha512Sync;
ed.etc.sha512Async = async (...msgs) => _sha512Sync(...msgs);
export const ED25519_PREFIX = "01";
function toHex(bytes) {
    let s = "";
    for (const b of bytes)
        s += b.toString(16).padStart(2, "0");
    return s;
}
function fromHex(hex) {
    const out = new Uint8Array(hex.length / 2);
    for (let i = 0; i < out.length; i++)
        out[i] = parseInt(hex.substr(i * 2, 2), 16);
    return out;
}
export async function generateAccount(label) {
    const priv = ed.utils.randomPrivateKey();
    return accountFromPrivateKey(toHex(priv), label);
}
export async function accountFromPrivateKey(privateKeyHex, label) {
    const pub = await ed.getPublicKey(fromHex(privateKeyHex));
    return {
        privateKeyHex,
        publicAccountHex: ED25519_PREFIX + toHex(pub),
        label,
    };
}
export function canonicalAuthorization(sender, recipient, value, serviceId, nonce) {
    return `${sender}\n${recipient}\n${value}\n${serviceId}\n${nonce}`;
}
export async function signMessage(message, privateKeyHex) {
    const sig = await ed.signAsync(new TextEncoder().encode(message), fromHex(privateKeyHex));
    return toHex(sig);
}
export async function verifySignature(message, signatureHex, publicAccountHex) {
    try {
        const rawHex = publicAccountHex.startsWith(ED25519_PREFIX)
            ? publicAccountHex.slice(2)
            : publicAccountHex;
        return await ed.verifyAsync(fromHex(signatureHex), new TextEncoder().encode(message), fromHex(rawHex));
    }
    catch {
        return false;
    }
}
export function newNonce() {
    const bytes = new Uint8Array(16);
    crypto.getRandomValues(bytes);
    return toHex(bytes);
}
