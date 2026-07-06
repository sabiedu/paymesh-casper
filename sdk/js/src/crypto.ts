// Casper Ed25519 account handling for x402 payment signatures.
// A Casper Ed25519 account public key = 0x01 tag + 32-byte raw pubkey, hex.
// Uses @noble/ed25519 (pure JS, no native deps, works in browser & Node).

import * as ed from "@noble/ed25519";
import { sha512 } from "@noble/hashes/sha512";

// @noble/ed25519 v2 requires a SHA-512 backend to be wired in.
const _sha512Sync = (...msgs: Uint8Array[]) => sha512(ed.etc.concatBytes(...msgs));
ed.etc.sha512Sync = _sha512Sync as any;
ed.etc.sha512Async = async (...msgs: Uint8Array[]) => _sha512Sync(...msgs);

export const ED25519_PREFIX = "01";

export interface Account {
  privateKeyHex: string;
  publicAccountHex: string; // "01" + 32-byte raw pubkey hex
  label?: string;
}

function toHex(bytes: Uint8Array): string {
  let s = "";
  for (const b of bytes) s += b.toString(16).padStart(2, "0");
  return s;
}

function fromHex(hex: string): Uint8Array {
  const out = new Uint8Array(hex.length / 2);
  for (let i = 0; i < out.length; i++) out[i] = parseInt(hex.substr(i * 2, 2), 16);
  return out;
}

export async function generateAccount(label?: string): Promise<Account> {
  const priv = ed.utils.randomPrivateKey();
  return accountFromPrivateKey(toHex(priv), label);
}

export async function accountFromPrivateKey(
  privateKeyHex: string,
  label?: string
): Promise<Account> {
  const pub = await ed.getPublicKey(fromHex(privateKeyHex));
  return {
    privateKeyHex,
    publicAccountHex: ED25519_PREFIX + toHex(pub),
    label,
  };
}

export function canonicalAuthorization(
  sender: string,
  recipient: string,
  value: string,
  serviceId: string,
  nonce: string
): string {
  return `${sender}\n${recipient}\n${value}\n${serviceId}\n${nonce}`;
}

export async function signMessage(
  message: string,
  privateKeyHex: string
): Promise<string> {
  const sig = await ed.signAsync(
    new TextEncoder().encode(message),
    fromHex(privateKeyHex)
  );
  return toHex(sig);
}

export async function verifySignature(
  message: string,
  signatureHex: string,
  publicAccountHex: string
): Promise<boolean> {
  try {
    const rawHex = publicAccountHex.startsWith(ED25519_PREFIX)
      ? publicAccountHex.slice(2)
      : publicAccountHex;
    return await ed.verifyAsync(
      fromHex(signatureHex),
      new TextEncoder().encode(message),
      fromHex(rawHex)
    );
  } catch {
    return false;
  }
}

export function newNonce(): string {
  const bytes = new Uint8Array(16);
  crypto.getRandomValues(bytes);
  return toHex(bytes);
}
