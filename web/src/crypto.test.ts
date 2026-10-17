import { describe, expect, it } from 'vitest';
import fixture from './fixtures/encryption-v1.json';
import { createIdentity, open, PREFIX, recoverIdentity, recoveryCode, seal, unb64 } from './crypto';

describe('interoperable end-to-end encryption', () => {
  it('restores independently generated keys and reads Unicode PyCA/CryptoKit fixtures', async () => {
    const alice = await recoverIdentity(fixture.alice.bundle, fixture.alice.recoveryCode);
    const bob = await recoverIdentity(fixture.bob.bundle, fixture.bob.recoveryCode);
    expect(await open(alice, fixture.journal, 'journal', fixture.journalID, '', alice.bundle)).toEqual(fixture.journalContent);
    expect(await open(bob, fixture.passage, 'passage', fixture.journalID, fixture.connectionID, alice.bundle)).toEqual(fixture.textContent);
    expect(await open(bob, fixture.message, 'message', fixture.messageID, fixture.connectionID, alice.bundle)).toEqual(fixture.textContent);
    expect(alice.agreement.extractable).toBe(false); expect(alice.signing.extractable).toBe(false);
  });
  it('generates recoverable identities and encrypts to both members without plaintext', async () => {
    const alice = await createIdentity(fixture.alice.bundle.userID), bob = await createIdentity(fixture.bob.bundle.userID);
    const restored = await recoverIdentity(alice.bundle, await recoveryCode(alice));
    expect(restored.bundle).toEqual(alice.bundle);
    const wire = await seal(alice, 'message', fixture.messageID, fixture.connectionID, fixture.textContent, [alice.bundle, bob.bundle]);
    expect(wire).not.toContain(fixture.textContent.text);
    expect(await open(restored, wire, 'message', fixture.messageID, fixture.connectionID, alice.bundle)).toEqual(fixture.textContent);
    expect(await open(bob, wire, 'message', fixture.messageID, fixture.connectionID, alice.bundle)).toEqual(fixture.textContent);
  });
  it('rejects ciphertext, signature, recipient and context tampering', async () => {
    const bob = await recoverIdentity(fixture.bob.bundle, fixture.bob.recoveryCode);
    for (const field of ['ciphertext', 'signature', 'senderID', 'id', 'connectionID']) {
      const value = JSON.parse(fixture.message.slice(PREFIX.length));
      value[field] = (value[field][0] === 'A' ? 'B' : 'A') + value[field].slice(1);
      await expect(open(bob, PREFIX + JSON.stringify(value), 'message', fixture.messageID, fixture.connectionID, fixture.alice.bundle)).rejects.toThrow();
    }
    const value = JSON.parse(fixture.message.slice(PREFIX.length)); value.recipients[1].userID = fixture.alice.bundle.userID;
    await expect(open(bob, PREFIX + JSON.stringify(value), 'message', fixture.messageID, fixture.connectionID, fixture.alice.bundle)).rejects.toThrow();
    await expect(open(bob, fixture.journal, 'journal', fixture.journalID, '', fixture.alice.bundle)).rejects.toThrow('not addressed');
  });
  it('rejects a wrong recovery code, another account and noncanonical base64', async () => {
    await expect(recoverIdentity(fixture.alice.bundle, fixture.bob.recoveryCode)).rejects.toThrow();
    await expect(recoverIdentity({ ...fixture.alice.bundle, userID: fixture.bob.bundle.userID }, fixture.alice.recoveryCode)).rejects.toThrow();
    expect(() => unb64('AA=')).toThrow(); expect(() => unb64('AB')).toThrow();
  });
});
