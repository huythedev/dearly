import Foundation
import CryptoKit

// Same versioned format as web/src/crypto.ts; see docs/ENCRYPTION.md.
struct EncryptionIdentity: Codable, Equatable {
    var userID: String
    var agreementKey: String
    var signingKey: String
    var fingerprint: String
    var wrappedPrivate: String?
    var nonce: String?
}

struct LocalEncryptionIdentity: Codable {
    var bundle: EncryptionIdentity
    var privateBytes: Data // Two separate 32-byte P-256 private scalars.
    var recoveryBytes: Data
    var backedUp = false
    func agreement() throws -> P256.KeyAgreement.PrivateKey { try .init(rawRepresentation: privateBytes.prefix(32)) }
    func signing() throws -> P256.Signing.PrivateKey { try .init(rawRepresentation: privateBytes.suffix(32)) }
    var recoveryCode: String { "DEARLY1-" + recoveryBytes.base64URL }
}

struct EncryptedRecipient: Codable {
    var userID: String
    var keyID: String
    var nonce: String
    var wrappedKey: String
}

struct EncryptedEnvelope: Codable {
    var v = 1
    var purpose: String
    var id: String
    var senderID: String
    var connectionID: String
    var senderKeyID: String
    var nonce: String
    var ciphertext: String
    var ephemeralKey: String
    var salt: String
    var recipients: [EncryptedRecipient]
    var signature: String
    var context: String { "dearly.e2ee.v1|\(purpose)|\(id)|\(senderID)|\(connectionID)" }
    var signatureInput: Data {
        let fields = ["dearly.e2ee.v1", purpose, id, senderID, connectionID, senderKeyID, nonce, ciphertext, ephemeralKey, salt]
        let recipientFields = recipients.sorted { $0.userID < $1.userID }.map { "\($0.userID)|\($0.keyID)|\($0.nonce)|\($0.wrappedKey)" }
        return Data((fields + recipientFields).joined(separator: "\n").utf8)
    }
}

extension Data {
    var base64URL: String { base64EncodedString().replacingOccurrences(of: "+", with: "-").replacingOccurrences(of: "/", with: "_").replacingOccurrences(of: "=", with: "") }
    init(base64URL: String, count: Int? = nil) throws {
        guard !base64URL.isEmpty, base64URL.count <= 180000,
              base64URL.range(of: "^[A-Za-z0-9_-]+$", options: .regularExpression) != nil else { throw EndToEndCrypto.invalid() }
        let padded = base64URL.replacingOccurrences(of: "-", with: "+").replacingOccurrences(of: "_", with: "/") + String(repeating: "=", count: (4 - base64URL.count % 4) % 4)
        guard let data = Data(base64Encoded: padded), data.base64URL == base64URL,
              count == nil || data.count == count else { throw EndToEndCrypto.invalid() }
        self = data
    }
}

enum EndToEndCrypto {
    static let prefix = "dearly:e2ee:1:"
    static func invalid() -> DearlyError { .invalid("Encrypted content could not be verified.") }
    static func random(_ count: Int) -> Data {
        // CryptoKit supplies cryptographically secure random bytes.
        var data = Data()
        while data.count < count { data.append(SymmetricKey(size: .bits256).withUnsafeBytes { Data($0) }) }
        return Data(data.prefix(count))
    }
    static func fingerprint(_ agreement: Data, _ signing: Data) -> String {
        SHA256.hash(data: agreement + signing).map { String(format: "%02x", $0) }.joined()
    }
    static func validate(_ identity: EncryptionIdentity) throws {
        let agreement = try Data(base64URL: identity.agreementKey, count: 65)
        let signing = try Data(base64URL: identity.signingKey, count: 65)
        guard UUID(uuidString: identity.userID)?.uuidString == identity.userID,
              fingerprint(agreement, signing) == identity.fingerprint else { throw invalid() }
        _ = try P256.KeyAgreement.PublicKey(x963Representation: agreement)
        _ = try P256.Signing.PublicKey(x963Representation: signing)
    }
    static func encrypt(_ plaintext: Data, key: SymmetricKey, nonce: Data, aad: String) throws -> Data {
        let sealed = try AES.GCM.seal(plaintext, using: key, nonce: AES.GCM.Nonce(data: nonce), authenticating: Data(aad.utf8))
        return sealed.ciphertext + sealed.tag
    }
    static func decrypt(_ ciphertext: Data, key: SymmetricKey, nonce: Data, aad: String) throws -> Data {
        guard ciphertext.count >= 16 else { throw invalid() }
        let box = try AES.GCM.SealedBox(nonce: AES.GCM.Nonce(data: nonce), ciphertext: ciphertext.dropLast(16), tag: ciphertext.suffix(16))
        return try AES.GCM.open(box, using: key, authenticating: Data(aad.utf8))
    }
    static func create(userID: UUID) throws -> LocalEncryptionIdentity {
        let agreement = P256.KeyAgreement.PrivateKey(), signing = P256.Signing.PrivateKey()
        let privateBytes = agreement.rawRepresentation + signing.rawRepresentation
        let recovery = random(32), nonce = random(12)
        let wrapped = try encrypt(privateBytes, key: SymmetricKey(data: recovery), nonce: nonce, aad: "dearly.identity.v1:\(userID.uuidString)")
        let bundle = EncryptionIdentity(userID: userID.uuidString,
            agreementKey: agreement.publicKey.x963Representation.base64URL, signingKey: signing.publicKey.x963Representation.base64URL,
            fingerprint: fingerprint(agreement.publicKey.x963Representation, signing.publicKey.x963Representation), wrappedPrivate: wrapped.base64URL, nonce: nonce.base64URL)
        return LocalEncryptionIdentity(bundle: bundle, privateBytes: privateBytes, recoveryBytes: recovery)
    }
    static func recover(_ bundle: EncryptionIdentity, code: String) throws -> LocalEncryptionIdentity {
        try validate(bundle)
        let clean = code.components(separatedBy: .whitespacesAndNewlines).joined()
        guard clean.hasPrefix("DEARLY1-"), let nonce = bundle.nonce, let wrapped = bundle.wrappedPrivate else { throw invalid() }
        let recovery = try Data(base64URL: String(clean.dropFirst(8)), count: 32)
        let raw = try decrypt(Data(base64URL: wrapped, count: 80), key: SymmetricKey(data: recovery), nonce: Data(base64URL: nonce, count: 12), aad: "dearly.identity.v1:\(bundle.userID)")
        let local = LocalEncryptionIdentity(bundle: bundle, privateBytes: raw, recoveryBytes: recovery, backedUp: true)
        guard try local.agreement().publicKey.x963Representation.base64URL == bundle.agreementKey,
              try local.signing().publicKey.x963Representation.base64URL == bundle.signingKey else { throw invalid() }
        return local
    }
    static func wrappingKey(privateKey: P256.KeyAgreement.PrivateKey, publicKey: String, salt: String, aad: String) throws -> SymmetricKey {
        let shared = try privateKey.sharedSecretFromKeyAgreement(with: P256.KeyAgreement.PublicKey(x963Representation: Data(base64URL: publicKey, count: 65)))
        return try shared.hkdfDerivedSymmetricKey(using: SHA256.self, salt: Data(base64URL: salt, count: 32), sharedInfo: Data("dearly.wrap.v1|\(aad)".utf8), outputByteCount: 32)
    }
    static func seal<T: Encodable>(_ value: T, identity: LocalEncryptionIdentity, purpose: String, id: UUID, connectionID: UUID? = nil, recipients: [EncryptionIdentity]) throws -> String {
        for recipient in recipients { try validate(recipient) }
        guard recipients.contains(where: { $0.userID == identity.bundle.userID }),
              Set(recipients.map(\.userID)).count == recipients.count else { throw invalid() }
        let ephemeral = P256.KeyAgreement.PrivateKey(), keyBytes = random(32), nonce = random(12)
        var envelope = EncryptedEnvelope(purpose: purpose, id: id.uuidString, senderID: identity.bundle.userID, connectionID: connectionID?.uuidString ?? "", senderKeyID: identity.bundle.fingerprint,
            nonce: nonce.base64URL, ciphertext: "", ephemeralKey: ephemeral.publicKey.x963Representation.base64URL, salt: random(32).base64URL, recipients: [], signature: "")
        envelope.ciphertext = try encrypt(JSONEncoder().encode(value), key: SymmetricKey(data: keyBytes), nonce: nonce, aad: envelope.context).base64URL
        for recipient in recipients {
            let nonce = random(12)
            let aad = "\(envelope.context)|\(recipient.userID)|\(recipient.fingerprint)"
            let key = try wrappingKey(privateKey: ephemeral, publicKey: recipient.agreementKey, salt: envelope.salt, aad: aad)
            let wrapped = try encrypt(keyBytes, key: key, nonce: nonce, aad: aad)
            envelope.recipients.append(EncryptedRecipient(userID: recipient.userID, keyID: recipient.fingerprint, nonce: nonce.base64URL, wrappedKey: wrapped.base64URL))
        }
        envelope.signature = try identity.signing().signature(for: envelope.signatureInput).rawRepresentation.base64URL
        return prefix + String(decoding: try JSONEncoder().encode(envelope), as: UTF8.self)
    }
    static func open<T: Decodable>(_ wire: String, identity: LocalEncryptionIdentity, purpose: String, id: UUID, connectionID: UUID? = nil, sender: EncryptionIdentity) throws -> T {
        guard wire.hasPrefix(prefix), wire.utf8.count <= 180000 else { throw invalid() }
        try validate(sender)
        let envelope = try JSONDecoder().decode(EncryptedEnvelope.self, from: Data(wire.dropFirst(prefix.count).utf8))
        guard envelope.v == 1, envelope.purpose == purpose, envelope.id == id.uuidString,
              envelope.connectionID == (connectionID?.uuidString ?? ""), envelope.senderID == sender.userID, envelope.senderKeyID == sender.fingerprint,
              envelope.recipients.count <= 2 else { throw invalid() }
        let signing = try P256.Signing.PublicKey(x963Representation: Data(base64URL: sender.signingKey, count: 65))
        guard try signing.isValidSignature(P256.Signing.ECDSASignature(rawRepresentation: Data(base64URL: envelope.signature, count: 64)), for: envelope.signatureInput),
              let recipient = envelope.recipients.first(where: { $0.userID == identity.bundle.userID && $0.keyID == identity.bundle.fingerprint }) else { throw invalid() }
        let aad = "\(envelope.context)|\(recipient.userID)|\(recipient.keyID)"
        let wrapping = try wrappingKey(privateKey: identity.agreement(), publicKey: envelope.ephemeralKey, salt: envelope.salt, aad: aad)
        let rawKey = try decrypt(Data(base64URL: recipient.wrappedKey, count: 48), key: wrapping, nonce: Data(base64URL: recipient.nonce, count: 12), aad: aad)
        let plaintext = try decrypt(Data(base64URL: envelope.ciphertext), key: SymmetricKey(data: rawKey), nonce: Data(base64URL: envelope.nonce, count: 12), aad: envelope.context)
        return try JSONDecoder().decode(T.self, from: plaintext)
    }
}
