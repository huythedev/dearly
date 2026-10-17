import { APIError, command, request } from './api';
import { createIdentity, open, PREFIX, recoverIdentity, recoveryCode, seal, validateIdentity, type IdentityBundle, type LocalIdentity, type PublicIdentity } from './crypto';
import { activeConnection, type Envelope, type Journal, type Message } from './types';

type VaultState = { status: 'idle' | 'loading' | 'ready' | 'locked' | 'unavailable'; needsBackup: boolean; fingerprint: string; error: string };
const idle: VaultState = { status: 'idle', needsBackup: false, fingerprint: '', error: '' };
const LOCKED = 'Encrypted content. Unlock encryption in Settings.';

// IndexedDB supports structured cloning of non-extractable CryptoKeys. Never put
// private keys or the recovery code into localStorage or server-side sessions.
async function database(): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const opening = indexedDB.open('dearly-encryption', 1);
    opening.onupgradeneeded = () => opening.result.createObjectStore('keys');
    opening.onsuccess = () => resolve(opening.result);
    opening.onerror = () => reject(new Error('Secure key storage is unavailable. Allow website storage and try again.'));
  });
}
async function stored<T>(key: string, value?: T, remove = false): Promise<T | undefined> {
  const db = await database();
  try {
    return await new Promise((resolve, reject) => {
      const transaction = db.transaction('keys', value === undefined && !remove ? 'readonly' : 'readwrite');
      const store = transaction.objectStore('keys');
      const operation = remove ? store.delete(key) : value === undefined ? store.get(key) : store.put(value, key);
      transaction.oncomplete = () => resolve(operation.result as T | undefined);
      transaction.onerror = () => reject(transaction.error ?? new Error('Could not save encryption keys.'));
      transaction.onabort = () => reject(transaction.error ?? new Error('Could not save encryption keys.'));
    });
  } finally { db.close(); }
}

async function claimIdentity(key: string, candidate: LocalIdentity): Promise<LocalIdentity> {
  const db = await database();
  try {
    return await new Promise((resolve, reject) => {
      // A read/write transaction serializes competing first logins in other tabs.
      // Every publisher must use the same persisted winner before contacting the API.
      const transaction = db.transaction('keys', 'readwrite');
      const keys = transaction.objectStore('keys');
      const read = keys.get(key);
      let winner = candidate;
      read.onsuccess = () => {
        if (read.result) winner = read.result as LocalIdentity;
        else keys.add(candidate, key);
      };
      transaction.oncomplete = () => resolve(winner);
      transaction.onerror = () => reject(transaction.error ?? new Error('Could not save encryption keys.'));
      transaction.onabort = () => reject(transaction.error ?? new Error('Could not save encryption keys.'));
    });
  } finally { db.close(); }
}

class EncryptionVault {
  private userID = '';
  private local: LocalIdentity | null = null;
  private bundle: IdentityBundle | null = null;
  private peers = new Map<string, PublicIdentity>();
  private fetchingPeers = new Map<string, Promise<PublicIdentity>>();
  private decoded = new Map<string, unknown>();
  private initializing: Promise<void> | null = null;
  private state = idle;
  private listeners = new Set<() => void>();
  subscribe = (listener: () => void) => { this.listeners.add(listener); return () => { this.listeners.delete(listener); }; };
  snapshot = () => this.state;
  private update(value: Partial<VaultState>) { this.state = { ...this.state, ...value }; this.listeners.forEach(listener => listener()); }
  private storageKey(uid = this.userID) { return `${location.origin}|${uid}`; }
  clearMemory() { this.userID = ''; this.local = null; this.bundle = null; this.peers.clear(); this.fetchingPeers.clear(); this.decoded.clear(); this.initializing = null; this.state = idle; this.listeners.forEach(listener => listener()); }
  async forget(userID: string) {
    await stored(this.storageKey(userID), undefined, true);
    await stored(`${this.storageKey(userID)}|pins`, undefined, true);
    this.clearMemory();
  }
  async initialize(userID: string, signal?: AbortSignal) {
    if (this.userID === userID && this.initializing) return this.initializing;
    if (this.userID === userID && ['ready', 'locked', 'unavailable'].includes(this.state.status)) return;
    this.clearMemory(); this.userID = userID; this.update({ status: 'loading' });
    const current = () => this.userID === userID && !signal?.aborted;
    this.initializing = (async () => {
      try {
        if (!crypto.subtle) throw new Error('Encryption needs HTTPS. Open Dearly using its secure address.');
        const headers = { 'X-Dearly-User': userID };
        let bundle: IdentityBundle | null = null;
        try { bundle = await request<IdentityBundle>('encryption/identity', { headers, signal }); }
        catch (error) { if (!(error instanceof APIError && error.status === 404)) throw error; }
        if (!current()) return;
        const saved = await stored<LocalIdentity>(this.storageKey(userID));
        let local = saved ?? null;
        if (!current()) return;
        if (bundle) {
          await validateIdentity(bundle);
          if (bundle.userID !== userID) throw new Error('Encryption identity belongs to a different account.');
          if (local && (local.bundle.fingerprint !== bundle.fingerprint || local.bundle.wrappedPrivate !== bundle.wrappedPrivate)) local = null;
        } else {
          local ??= await createIdentity(userID);
          // Persist before publishing. A failed IndexedDB write must not strand an account.
          local = await claimIdentity(this.storageKey(userID), local);
          if (!current()) return;
          const { agreementKey, signingKey, wrappedPrivate, nonce } = local.bundle;
          try {
            bundle = await request<IdentityBundle>('encryption/identity', { method: 'POST', headers, signal, body: JSON.stringify({ agreementKey, signingKey, wrappedPrivate, nonce }) });
          } catch (error) {
            if (!(error instanceof APIError && error.status === 409)) throw error;
            // Another device may have initialized the account first. Recover its
            // immutable identity; do not replace it or silently use our losing key.
            bundle = await request<IdentityBundle>('encryption/identity', { headers, signal });
          }
          await validateIdentity(bundle);
          if (bundle.userID !== userID) throw new Error('Encryption identity belongs to a different account.');
          if (bundle.fingerprint !== local.bundle.fingerprint || bundle.wrappedPrivate !== local.bundle.wrappedPrivate) local = null;
        }
        if (!current()) return;
        this.bundle = bundle; this.local = local;
        this.update({ status: local ? 'ready' : 'locked', fingerprint: bundle.fingerprint, needsBackup: Boolean(local && !local.backedUp), error: '' });
      } catch (error) {
        if (current()) this.update({ status: 'unavailable', error: error instanceof Error ? error.message : 'Encryption is unavailable.' });
      } finally { if (current()) this.initializing = null; }
    })();
    return this.initializing;
  }
  async retry(userID: string) { this.clearMemory(); await this.initialize(userID); }
  async recover(code: string) {
    if (!this.bundle || !this.userID) throw new Error('Sign in before unlocking encryption.');
    const uid = this.userID;
    let local: LocalIdentity;
    try { local = await recoverIdentity(this.bundle, code); }
    catch { throw new Error('The recovery code does not match this account.'); }
    if (uid !== this.userID) return;
    await stored(this.storageKey(uid), local);
    if (uid !== this.userID) return;
    this.local = local; this.decoded.clear(); this.update({ status: 'ready', needsBackup: false, error: '' });
  }
  async code() { return recoveryCode(this.requireLocal()); }
  async markBackedUp() {
    const local = this.requireLocal(); local.backedUp = true;
    await stored(this.storageKey(), local); this.update({ needsBackup: false });
  }
  private requireLocal(): LocalIdentity {
    if (!this.local || this.state.status !== 'ready') throw new Error(this.state.status === 'locked' ? 'Unlock encryption in Settings with your recovery code first.' : this.state.error || 'Encryption is not ready. Open Settings and try again.');
    return this.local;
  }
  async peer(userID: string): Promise<PublicIdentity> {
    if (userID === this.userID && this.bundle) return this.bundle;
    const cached = this.peers.get(userID); if (cached) return cached;
    const pending = this.fetchingPeers.get(userID); if (pending) return pending;
    const fetching = this.fetchPeer(userID);
    this.fetchingPeers.set(userID, fetching);
    try { return await fetching; } finally { if (this.fetchingPeers.get(userID) === fetching) this.fetchingPeers.delete(userID); }
  }
  private async fetchPeer(userID: string): Promise<PublicIdentity> {
    const uid = this.userID;
    const bundle = await request<PublicIdentity>(`encryption/keys/${userID}`, { headers: { 'X-Dearly-User': uid } });
    await validateIdentity(bundle);
    if (bundle.userID !== userID || uid !== this.userID) throw new Error('Encryption identity belongs to a different account.');
    const key = `${this.storageKey(uid)}|pins`;
    const pins = await stored<Record<string, string>>(key) ?? {};
    if (pins[userID] && pins[userID] !== bundle.fingerprint) throw new Error('Your companion’s encryption key changed. Stop sharing and verify their fingerprint.');
    pins[userID] = bundle.fingerprint; await stored(key, pins);
    if (uid !== this.userID) throw new Error('Your account changed.');
    this.peers.set(userID, bundle); return bundle;
  }
  async prepare(kind: string, payload: Record<string, unknown>, envelope: Envelope): Promise<Record<string, unknown>> {
    if (kind !== 'journal.save' && kind !== 'message.send') return payload;
    const local = this.requireLocal();
    if (envelope.state.currentUserID !== local.bundle.userID) throw new Error('Your account changed.');
    const id = String(payload.id || command('', {}).requestID).toUpperCase();
    const conn = activeConnection(envelope.state);
    if (kind === 'message.send') {
      const text = String(payload.text ?? '').trim();
      if (!text || [...text].length > 4000 || !conn || conn.id !== payload.connectionID) throw new Error('Enter a message for your current companion.');
      const recipients = await Promise.all(conn.members.map(member => this.peer(member)));
      return { ...payload, clientID: id, text: await seal(local, 'message', id, conn.id, { text }, recipients) };
    }
    const body = String(payload.body ?? '').trim(), title = String(payload.title ?? '').trim(), passage = String(payload.sharedText ?? '').trim();
    if (!body || [...body].length > 20000 || [...title].length > 160) throw new Error('Check your journal title and text length.');
    if (payload.audience !== 'privateOnly' && (!passage || !body.includes(passage))) throw new Error('The shared passage must be part of your journal entry.');
    let sharedText = payload.audience === 'privateOnly' ? '' : passage;
    if (payload.audience === 'companion') {
      if (!conn) throw new Error('You don’t have a connection yet.');
      const recipients = await Promise.all(conn.members.map(member => this.peer(member)));
      sharedText = await seal(local, 'passage', id, conn.id, { text: passage }, recipients);
    }
    return { ...payload, ...(payload.id ? {} : { clientID: id }), title: '', sharedText,
      body: await seal(local, 'journal', id, '', { title, body }, [local.bundle]) };
  }
  private async decode<T>(wire: string, purpose: 'journal' | 'passage' | 'message', id: string, connectionID: string, senderID: string): Promise<T> {
    const cacheKey = `${purpose}|${id}|${connectionID}|${senderID}|${wire}`;
    if (this.decoded.has(cacheKey)) return this.decoded.get(cacheKey) as T;
    const uid = this.userID;
    const result = await open<T>(this.requireLocal(), wire, purpose, id, connectionID, await this.peer(senderID));
    if (uid !== this.userID) throw new Error('Your account changed.');
    if (this.decoded.size >= 500) this.decoded.delete(this.decoded.keys().next().value!);
    this.decoded.set(cacheKey, result); return result;
  }
  async journal(row: Journal): Promise<Journal> {
    let result = { ...row };
    if (row.body.startsWith(PREFIX)) {
      try {
        const value = await this.decode<{ title: string; body: string }>(row.body, 'journal', row.id, '', row.authorID);
        if (typeof value.title !== 'string' || typeof value.body !== 'string') throw new Error();
        result = { ...result, title: value.title, body: value.body, encrypted: true, locked: false };
      } catch { result = { ...result, title: 'Locked entry', body: LOCKED, encrypted: true, locked: true }; }
    }
    if (row.sharedText.startsWith(PREFIX)) {
      try {
        const value = await this.decode<{ text: string }>(row.sharedText, 'passage', row.id, row.connectionID ?? '', row.authorID);
        if (typeof value.text !== 'string') throw new Error();
        result.sharedText = value.text;
      } catch { result.sharedText = LOCKED; result.locked = true; }
    }
    return result;
  }
  async message(row: Message): Promise<Message> {
    if (!row.text.startsWith(PREFIX)) return row;
    try {
      const value = await this.decode<{ text: string }>(row.text, 'message', row.id, row.connectionID, row.senderID);
      if (typeof value.text !== 'string') throw new Error();
      return { ...row, text: value.text, encrypted: true, locked: false };
    } catch { return { ...row, text: LOCKED, encrypted: true, locked: true }; }
  }
  async envelope(value: Envelope): Promise<Envelope> {
    return { ...value, state: { ...value.state,
      journals: await Promise.all(value.state.journals.map(row => this.journal(row))),
      messages: await Promise.all(value.state.messages.map(row => this.message(row))),
    } };
  }
  async page<T>(path: string, items: T[]): Promise<T[]> {
    if (path.startsWith('journals')) return Promise.all((items as Journal[]).map(row => this.journal(row))) as Promise<T[]>;
    if (path.startsWith('messages')) return Promise.all((items as Message[]).map(row => this.message(row))) as Promise<T[]>;
    return items;
  }
  async dataExport(data: Record<string, unknown>, decrypt: boolean) {
    if (!decrypt) return { ...data, contentEncoding: 'original; encrypted entries need your recovery code' };
    this.requireLocal();
    return { ...data, contentEncoding: 'decrypted on your device; locked records keep their encrypted originals',
      encryptedOriginal: { journals: data.journals, messages: data.messages },
      journals: await Promise.all((data.journals as Journal[]).map(row => this.journal(row))),
      messages: await Promise.all((data.messages as Message[]).map(row => this.message(row))),
    };
  }
}
export const vault = new EncryptionVault();
