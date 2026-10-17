// Native Web Crypto primitives only. Keep this wire format in sync with
// ios/Dearly/Core/EndToEndCrypto.swift and docs/ENCRYPTION.md.
export const PREFIX = 'dearly:e2ee:1:';
export type Purpose = 'journal' | 'passage' | 'message';
export interface PublicIdentity { userID: string; agreementKey: string; signingKey: string; fingerprint: string }
export interface IdentityBundle extends PublicIdentity { wrappedPrivate: string; nonce: string }
export interface LocalIdentity { bundle: IdentityBundle; agreement: CryptoKey; signing: CryptoKey; recovery: CryptoKey; backedUp: boolean }
interface Recipient { userID: string; keyID: string; nonce: string; wrappedKey: string }
export interface CipherEnvelope {
  v: number; purpose: Purpose; id: string; senderID: string; connectionID: string; senderKeyID: string;
  nonce: string; ciphertext: string; ephemeralKey: string; salt: string; recipients: Recipient[]; signature: string;
}
const utf8 = new TextEncoder();
const text = new TextDecoder('utf-8', { fatal: true });
const bytes = (size: number) => crypto.getRandomValues(new Uint8Array(size));
export function b64(data: ArrayBuffer | Uint8Array): string {
  return btoa(Array.from(new Uint8Array(data), n => String.fromCharCode(n)).join('')).replaceAll('+', '-').replaceAll('/', '_').replace(/=+$/, '');
}
export function unb64(value: string, size?: number): Uint8Array<ArrayBuffer> {
  if (typeof value !== 'string' || !/^[A-Za-z0-9_-]+$/.test(value) || value.length > 180000) throw new Error('Invalid encrypted data.');
  const result = Uint8Array.from(atob(value.replaceAll('-', '+').replaceAll('_', '/') + '='.repeat((4 - value.length % 4) % 4)), x => x.charCodeAt(0));
  if ((size !== undefined && result.length !== size) || b64(result) !== value) throw new Error('Invalid encrypted data.');
  return result;
}
const aes = (key: Uint8Array<ArrayBuffer>, extractable = false) => crypto.subtle.importKey('raw', key, 'AES-GCM', extractable, ['encrypt', 'decrypt']);
const publicKey = (raw: string, signing = false) => crypto.subtle.importKey('raw', unb64(raw, 65), { name: signing ? 'ECDSA' : 'ECDH', namedCurve: 'P-256' }, true, signing ? ['verify'] : []);
const fingerprint = async (agreement: string, signing: string) => {
  const joined = new Uint8Array([...unb64(agreement, 65), ...unb64(signing, 65)]);
  return Array.from(new Uint8Array(await crypto.subtle.digest('SHA-256', joined)), n => n.toString(16).padStart(2, '0')).join('');
};
export async function validateIdentity(bundle: PublicIdentity): Promise<void> {
  if (!bundle || typeof bundle.userID !== 'string' || bundle.userID !== bundle.userID.toUpperCase() ||
      !/^[0-9A-F-]{36}$/.test(bundle.userID) || await fingerprint(bundle.agreementKey, bundle.signingKey) !== bundle.fingerprint) throw new Error('Invalid encryption identity.');
  await publicKey(bundle.agreementKey); await publicKey(bundle.signingKey, true);
}
async function privateKey(raw: Uint8Array<ArrayBuffer>, pub: string, signing: boolean) {
  const point = unb64(pub, 65);
  return crypto.subtle.importKey('jwk', { kty: 'EC', crv: 'P-256', x: b64(point.slice(1, 33)), y: b64(point.slice(33)), d: b64(raw), ext: false },
    { name: signing ? 'ECDSA' : 'ECDH', namedCurve: 'P-256' }, false, signing ? ['sign'] : ['deriveBits']);
}
export async function createIdentity(userID: string): Promise<LocalIdentity> {
  if (!crypto.subtle) throw new Error('Encryption needs HTTPS. Open Dearly using its secure address.');
  const agreement = await crypto.subtle.generateKey({ name: 'ECDH', namedCurve: 'P-256' }, true, ['deriveBits']);
  const signing = await crypto.subtle.generateKey({ name: 'ECDSA', namedCurve: 'P-256' }, true, ['sign', 'verify']);
  const agreementKey = b64(await crypto.subtle.exportKey('raw', agreement.publicKey));
  const signingKey = b64(await crypto.subtle.exportKey('raw', signing.publicKey));
  const first = unb64((await crypto.subtle.exportKey('jwk', agreement.privateKey)).d!, 32);
  const second = unb64((await crypto.subtle.exportKey('jwk', signing.privateKey)).d!, 32);
  const recovery = await aes(bytes(32), true);
  const nonce = bytes(12);
  const raw = new Uint8Array([...first, ...second]);
  try {
    const wrappedPrivate = b64(await crypto.subtle.encrypt({ name: 'AES-GCM', iv: nonce, additionalData: utf8.encode(`dearly.identity.v1:${userID}`) }, recovery, raw));
    return { bundle: { userID, agreementKey, signingKey, fingerprint: await fingerprint(agreementKey, signingKey), nonce: b64(nonce), wrappedPrivate },
      agreement: await privateKey(first, agreementKey, false), signing: await privateKey(second, signingKey, true), recovery, backedUp: false };
  } finally { raw.fill(0); first.fill(0); second.fill(0); }
}
export async function recoveryCode(identity: LocalIdentity): Promise<string> {
  return `DEARLY1-${b64(await crypto.subtle.exportKey('raw', identity.recovery))}`;
}
export async function recoverIdentity(bundle: IdentityBundle, code: string): Promise<LocalIdentity> {
  await validateIdentity(bundle);
  const clean = code.replace(/\s/g, '');
  if (!clean.startsWith('DEARLY1-')) throw new Error('Enter your Dearly recovery code.');
  const recovery = await aes(unb64(clean.slice(8), 32), true);
  const raw = new Uint8Array(await crypto.subtle.decrypt({ name: 'AES-GCM', iv: unb64(bundle.nonce, 12), additionalData: utf8.encode(`dearly.identity.v1:${bundle.userID}`) }, recovery, unb64(bundle.wrappedPrivate, 80)));
  try {
    const agreement = await privateKey(raw.slice(0, 32), bundle.agreementKey, false);
    const signing = await privateKey(raw.slice(32), bundle.signingKey, true);
    // Confirm that the restored private keys match the published public keys.
    const probe = utf8.encode('dearly.identity.check.v1');
    const signature = await crypto.subtle.sign({ name: 'ECDSA', hash: 'SHA-256' }, signing, probe);
    if (!await crypto.subtle.verify({ name: 'ECDSA', hash: 'SHA-256' }, await publicKey(bundle.signingKey, true), signature, probe)) throw new Error('Invalid recovery identity.');
    const generator = 'BGsX0fLhLEJH-Lzm5WOkQPJ3A32BLeszoPShOUXYmMKW T-NC4v4af5uO5-tKfA-eFivOM1drMV7Oy7ZAaDe_UfU'.replaceAll(' ', '');
    const x = new Uint8Array(await crypto.subtle.deriveBits({ name: 'ECDH', public: await publicKey(generator) }, agreement, 256));
    if (b64(x) !== b64(unb64(bundle.agreementKey, 65).slice(1, 33))) throw new Error('Invalid recovery identity.');
    return { bundle, agreement, signing, recovery, backedUp: true };
  } finally { raw.fill(0); }
}
export const context = (e: Pick<CipherEnvelope, 'purpose' | 'id' | 'senderID' | 'connectionID'>) => `dearly.e2ee.v1|${e.purpose}|${e.id}|${e.senderID}|${e.connectionID}`;
export const signatureInput = (e: CipherEnvelope) => utf8.encode(['dearly.e2ee.v1', e.purpose, e.id, e.senderID, e.connectionID, e.senderKeyID,
  e.nonce, e.ciphertext, e.ephemeralKey, e.salt, ...[...e.recipients].sort((a, b) => a.userID.localeCompare(b.userID))
    .map(r => `${r.userID}|${r.keyID}|${r.nonce}|${r.wrappedKey}`)].join('\n'));
async function wrappingKey(privatePart: CryptoKey, publicPart: string, salt: string, aad: string) {
  const secret = await crypto.subtle.deriveBits({ name: 'ECDH', public: await publicKey(publicPart) }, privatePart, 256);
  const material = await crypto.subtle.importKey('raw', secret, 'HKDF', false, ['deriveKey']);
  return crypto.subtle.deriveKey({ name: 'HKDF', hash: 'SHA-256', salt: unb64(salt, 32), info: utf8.encode(`dearly.wrap.v1|${aad}`) },
    material, { name: 'AES-GCM', length: 256 }, false, ['encrypt', 'decrypt']);
}
export async function seal(identity: LocalIdentity, purpose: Purpose, id: string, connectionID: string, value: unknown, recipients: PublicIdentity[]): Promise<string> {
  for (const recipient of recipients) await validateIdentity(recipient);
  if (!recipients.some(r => r.userID === identity.bundle.userID) || new Set(recipients.map(r => r.userID)).size !== recipients.length) throw new Error('Invalid encrypted recipients.');
  const ephemeral = await crypto.subtle.generateKey({ name: 'ECDH', namedCurve: 'P-256' }, false, ['deriveBits']);
  const key = bytes(32);
  const nonce = bytes(12);
  const e: CipherEnvelope = { v: 1, purpose, id, senderID: identity.bundle.userID, connectionID, senderKeyID: identity.bundle.fingerprint,
    nonce: b64(nonce), ciphertext: '', ephemeralKey: b64(await crypto.subtle.exportKey('raw', ephemeral.publicKey)), salt: b64(bytes(32)), recipients: [], signature: '' };
  try {
    e.ciphertext = b64(await crypto.subtle.encrypt({ name: 'AES-GCM', iv: nonce, additionalData: utf8.encode(context(e)) }, await aes(key), utf8.encode(JSON.stringify(value))));
    for (const recipient of recipients) {
      const r = { userID: recipient.userID, keyID: recipient.fingerprint, nonce: b64(bytes(12)), wrappedKey: '' };
      const aad = `${context(e)}|${r.userID}|${r.keyID}`;
      r.wrappedKey = b64(await crypto.subtle.encrypt({ name: 'AES-GCM', iv: unb64(r.nonce, 12), additionalData: utf8.encode(aad) },
        await wrappingKey(ephemeral.privateKey, recipient.agreementKey, e.salt, aad), key));
      e.recipients.push(r);
    }
    e.signature = b64(await crypto.subtle.sign({ name: 'ECDSA', hash: 'SHA-256' }, identity.signing, signatureInput(e)));
    return PREFIX + JSON.stringify(e);
  } finally { key.fill(0); }
}
export async function open<T>(identity: LocalIdentity, wire: string, purpose: Purpose, id: string, connectionID: string, sender: PublicIdentity): Promise<T> {
  if (!wire.startsWith(PREFIX) || wire.length > 180000) throw new Error('Invalid encrypted data.');
  const e = JSON.parse(wire.slice(PREFIX.length)) as CipherEnvelope;
  await validateIdentity(sender);
  if (e.v !== 1 || e.purpose !== purpose || e.id !== id || e.connectionID !== connectionID || e.senderID !== sender.userID || e.senderKeyID !== sender.fingerprint ||
      !Array.isArray(e.recipients) || e.recipients.length > 2 || !await crypto.subtle.verify({ name: 'ECDSA', hash: 'SHA-256' }, await publicKey(sender.signingKey, true), unb64(e.signature, 64), signatureInput(e))) throw new Error('Encrypted content could not be verified.');
  const r = e.recipients.find(recipient => recipient.userID === identity.bundle.userID && recipient.keyID === identity.bundle.fingerprint);
  if (!r) throw new Error('This encrypted content is not addressed to you.');
  const aad = `${context(e)}|${r.userID}|${r.keyID}`;
  const raw = new Uint8Array(await crypto.subtle.decrypt({ name: 'AES-GCM', iv: unb64(r.nonce, 12), additionalData: utf8.encode(aad) },
    await wrappingKey(identity.agreement, e.ephemeralKey, e.salt, aad), unb64(r.wrappedKey, 48)));
  try {
    return JSON.parse(text.decode(await crypto.subtle.decrypt({ name: 'AES-GCM', iv: unb64(e.nonce, 12), additionalData: utf8.encode(context(e)) }, await aes(raw), unb64(e.ciphertext)))) as T;
  } finally { raw.fill(0); }
}
