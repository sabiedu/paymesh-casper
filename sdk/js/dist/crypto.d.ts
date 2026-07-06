export declare const ED25519_PREFIX = "01";
export interface Account {
    privateKeyHex: string;
    publicAccountHex: string;
    label?: string;
}
export declare function generateAccount(label?: string): Promise<Account>;
export declare function accountFromPrivateKey(privateKeyHex: string, label?: string): Promise<Account>;
export declare function canonicalAuthorization(sender: string, recipient: string, value: string, serviceId: string, nonce: string): string;
export declare function signMessage(message: string, privateKeyHex: string): Promise<string>;
export declare function verifySignature(message: string, signatureHex: string, publicAccountHex: string): Promise<boolean>;
export declare function newNonce(): string;
