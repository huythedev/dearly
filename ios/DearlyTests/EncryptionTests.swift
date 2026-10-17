import XCTest
@testable import Dearly

final class EncryptionTests: XCTestCase {
    struct TestIdentity: Decodable { var bundle: EncryptionIdentity; var recoveryCode: String; var privateBytes: String }
    struct Fixture: Decodable {
        var alice: TestIdentity; var bob: TestIdentity
        var connectionID: UUID; var journalID: UUID; var messageID: UUID
        var journal: String; var passage: String; var message: String
        var journalContent: EncryptedJournalContent; var textContent: EncryptedTextContent
    }
    private func fixture() throws -> Fixture {
        let url = try XCTUnwrap(Bundle(for: Self.self).url(forResource: "encryption-v1", withExtension: "json"))
        return try JSONDecoder().decode(Fixture.self, from: Data(contentsOf: url))
    }
    func testReadsIndependentUnicodeWebCryptoContract() throws {
        let f = try fixture()
        let alice = try EndToEndCrypto.recover(f.alice.bundle, code: f.alice.recoveryCode)
        let bob = try EndToEndCrypto.recover(f.bob.bundle, code: f.bob.recoveryCode)
        XCTAssertEqual(alice.privateBytes.base64URL, f.alice.privateBytes)
        let journal: EncryptedJournalContent = try EndToEndCrypto.open(f.journal, identity: alice, purpose: "journal", id: f.journalID, sender: alice.bundle)
        XCTAssertEqual(journal.body, f.journalContent.body); XCTAssertEqual(journal.title, f.journalContent.title)
        let message: EncryptedTextContent = try EndToEndCrypto.open(f.message, identity: bob, purpose: "message", id: f.messageID, connectionID: f.connectionID, sender: alice.bundle)
        let passage: EncryptedTextContent = try EndToEndCrypto.open(f.passage, identity: bob, purpose: "passage", id: f.journalID, connectionID: f.connectionID, sender: alice.bundle)
        XCTAssertEqual(message.text, f.textContent.text); XCTAssertEqual(passage.text, f.textContent.text)
    }
    func testNewIdentitiesRecoverAndBothMembersReadCiphertext() throws {
        let alice = try EndToEndCrypto.create(userID: UUID()), bob = try EndToEndCrypto.create(userID: UUID())
        let restored = try EndToEndCrypto.recover(alice.bundle, code: alice.recoveryCode)
        XCTAssertEqual(restored.privateBytes, alice.privateBytes)
        let mid = UUID(), cid = UUID(), plaintext = EncryptedTextContent(text: "Hello 🌱")
        let wire = try EndToEndCrypto.seal(plaintext, identity: alice, purpose: "message", id: mid, connectionID: cid, recipients: [alice.bundle, bob.bundle])
        XCTAssertFalse(wire.contains(plaintext.text))
        for local in [restored, bob] {
            let value: EncryptedTextContent = try EndToEndCrypto.open(wire, identity: local, purpose: "message", id: mid, connectionID: cid, sender: alice.bundle)
            XCTAssertEqual(value.text, plaintext.text)
        }
    }
    func testRejectsWrongRecoveryCodeAndResourceContext() throws {
        let f = try fixture(), bob = try EndToEndCrypto.recover(fixture().bob.bundle, code: fixture().bob.recoveryCode)
        XCTAssertThrowsError(try EndToEndCrypto.recover(f.alice.bundle, code: f.bob.recoveryCode))
        var otherAccount = f.alice.bundle; otherAccount.userID = f.bob.bundle.userID
        XCTAssertThrowsError(try EndToEndCrypto.recover(otherAccount, code: f.alice.recoveryCode))
        XCTAssertThrowsError(try EndToEndCrypto.open(f.message, identity: bob, purpose: "message", id: UUID(), connectionID: f.connectionID, sender: f.alice.bundle) as EncryptedTextContent)
        XCTAssertThrowsError(try EndToEndCrypto.open(f.journal, identity: bob, purpose: "journal", id: f.journalID, sender: f.alice.bundle) as EncryptedJournalContent)
    }
    func testRejectsTamperedCiphertextSignatureAndRecipients() throws {
        let f = try fixture(), bob = try EndToEndCrypto.recover(fixture().bob.bundle, code: fixture().bob.recoveryCode)
        for field in ["ciphertext", "signature", "senderID", "connectionID"] {
            var value = try JSONDecoder().decode(EncryptedEnvelope.self, from: Data(f.message.dropFirst(EndToEndCrypto.prefix.count).utf8))
            switch field {
            case "ciphertext": value.ciphertext = (value.ciphertext.hasPrefix("A") ? "B" : "A") + value.ciphertext.dropFirst()
            case "signature": value.signature = (value.signature.hasPrefix("A") ? "B" : "A") + value.signature.dropFirst()
            case "senderID": value.senderID = bob.bundle.userID
            default: value.connectionID = UUID().uuidString
            }
            let wire = EndToEndCrypto.prefix + String(decoding: try JSONEncoder().encode(value), as: UTF8.self)
            XCTAssertThrowsError(try EndToEndCrypto.open(wire, identity: bob, purpose: "message", id: f.messageID, connectionID: f.connectionID, sender: f.alice.bundle) as EncryptedTextContent)
        }
        XCTAssertThrowsError(try Data(base64URL: "AB")); XCTAssertThrowsError(try Data(base64URL: "AA="))
    }
}
