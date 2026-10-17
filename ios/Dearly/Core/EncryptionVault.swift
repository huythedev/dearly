import Foundation
import Combine
import Security
import CryptoKit

enum EncryptionKeychain {
    private static let service = "com.dearly.encryption.v1"
    static func read<T: Decodable>(_ key: String, as type: T.Type) throws -> T? {
        let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service,
            kSecAttrAccount as String: key, kSecReturnData as String: true, kSecMatchLimit as String: kSecMatchLimitOne]
        var result: CFTypeRef?
        let status = SecItemCopyMatching(query as CFDictionary, &result)
        if status == errSecItemNotFound { return nil }
        guard status == errSecSuccess, let data = result as? Data else { throw DearlyError.invalid("Secure key storage is unavailable. Unlock your iPhone and try again.") }
        return try JSONDecoder().decode(type, from: data)
    }
    static func save<T: Encodable>(_ value: T, key: String) throws {
        let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service, kSecAttrAccount as String: key]
        let data = try JSONEncoder().encode(value)
        let status = SecItemUpdate(query as CFDictionary, [kSecValueData as String: data] as CFDictionary)
        if status == errSecItemNotFound {
            var item = query; item[kSecValueData as String] = data; item[kSecAttrAccessible as String] = kSecAttrAccessibleWhenUnlockedThisDeviceOnly
            guard SecItemAdd(item as CFDictionary, nil) == errSecSuccess else { throw DearlyError.invalid("Could not save encryption keys.") }
        } else if status != errSecSuccess { throw DearlyError.invalid("Could not save encryption keys.") }
    }
    static func remove(_ key: String) {
        SecItemDelete([kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service, kSecAttrAccount as String: key] as CFDictionary)
    }
}

struct EncryptedJournalContent: Codable { var title: String; var body: String }
struct EncryptedTextContent: Codable { var text: String }

@MainActor
final class EncryptionVault: ObservableObject {
    @Published private(set) var status = "idle"
    @Published private(set) var needsBackup = false
    @Published private(set) var fingerprint = ""
    @Published private(set) var error = ""
    private var context = UUID()
    private var storageKey = ""
    private var userID: UUID?
    private var client: APIClient?
    private var local: LocalEncryptionIdentity?
    private var bundle: EncryptionIdentity?
    private var peers: [UUID: EncryptionIdentity] = [:]
    private var fetching: [UUID: Task<EncryptionIdentity, Error>] = [:]
    private let lockedText = "Encrypted content. Unlock encryption in Settings."

    func clearMemory() {
        context = UUID(); local = nil; bundle = nil; userID = nil; client = nil; storageKey = ""
        peers = [:]; fetching.values.forEach { $0.cancel() }; fetching = [:]
        status = "idle"; needsBackup = false; fingerprint = ""; error = ""
    }
    func forget() {
        EncryptionKeychain.remove(storageKey); EncryptionKeychain.remove(storageKey + ".pins"); clearMemory()
    }
    func configure(server: String, userID: UUID, client: APIClient) async {
        if self.userID == userID && self.client != nil && status != "idle" { return }
        clearMemory()
        self.userID = userID; self.client = client
        storageKey = SHA256.hash(data: Data("\(server.trimmingCharacters(in: CharacterSet(charactersIn: "/")))|\(userID.uuidString)".utf8)).map { String(format: "%02x", $0) }.joined()
        status = "loading"
        let expected = context
        do {
            var remote: EncryptionIdentity?
            do { remote = try await client.encryptionIdentity() }
            catch { if (error as? APIError)?.status != 404 { throw error } }
            guard expected == context else { return }
            var saved = try EncryptionKeychain.read(storageKey, as: LocalEncryptionIdentity.self)
            if let remote {
                try EndToEndCrypto.validate(remote)
                guard remote.userID == userID.uuidString else { throw EndToEndCrypto.invalid() }
                if saved?.bundle.fingerprint != remote.fingerprint || saved?.bundle.wrappedPrivate != remote.wrappedPrivate { saved = nil }
            } else {
                if saved == nil { saved = try EndToEndCrypto.create(userID: userID) }
                guard let identity = saved else { throw EndToEndCrypto.invalid() }
                try EncryptionKeychain.save(identity, key: storageKey)
                do { remote = try await client.publishEncryptionIdentity(identity.bundle) }
                catch {
                    guard (error as? APIError)?.status == 409 else { throw error }
                    remote = try await client.encryptionIdentity()
                }
                guard expected == context else { return }
                if remote?.fingerprint != identity.bundle.fingerprint || remote?.wrappedPrivate != identity.bundle.wrappedPrivate { saved = nil }
            }
            guard expected == context, let remote else { return }
            try EndToEndCrypto.validate(remote)
            guard remote.userID == userID.uuidString else { throw EndToEndCrypto.invalid() }
            bundle = remote; local = saved; fingerprint = remote.fingerprint
            needsBackup = saved.map { !$0.backedUp } ?? false; status = saved == nil ? "locked" : "ready"
        } catch {
            guard expected == context else { return }
            self.error = error.localizedDescription; status = "unavailable"
        }
    }
    func recoveryCode() throws -> String { try requireLocal().recoveryCode }
    func markBackedUp() throws {
        var value = try requireLocal(); value.backedUp = true
        try EncryptionKeychain.save(value, key: storageKey); local = value; needsBackup = false
    }
    func recover(_ code: String) throws {
        guard let bundle else { throw EndToEndCrypto.invalid() }
        let value: LocalEncryptionIdentity
        do { value = try EndToEndCrypto.recover(bundle, code: code) }
        catch { throw DearlyError.invalid("The recovery code does not match this account.") }
        try EncryptionKeychain.save(value, key: storageKey); local = value; needsBackup = false; status = "ready"; error = ""
    }
    private func requireLocal() throws -> LocalEncryptionIdentity {
        guard status == "ready", let local else { throw DearlyError.invalid(status == "locked" ? "Unlock encryption in Settings with your recovery code first." : "Encryption is not ready. Open Settings and try again.") }
        return local
    }
    func peer(_ id: UUID) async throws -> EncryptionIdentity {
        if id == userID, let bundle { return bundle }
        if let value = peers[id] { return value }
        if let pending = fetching[id] { return try await pending.value }
        let expected = context
        let task = Task { @MainActor in
            guard let client = self.client else { throw EndToEndCrypto.invalid() }
            let value = try await client.encryptionKey(id)
            try EndToEndCrypto.validate(value)
            guard expected == self.context, value.userID == id.uuidString else { throw CancellationError() }
            let key = self.storageKey + ".pins"
            var pins = try EncryptionKeychain.read(key, as: [String: String].self) ?? [:]
            if let existing = pins[id.uuidString], existing != value.fingerprint { throw DearlyError.invalid("Your companion’s encryption key changed. Stop sharing and verify their fingerprint.") }
            pins[id.uuidString] = value.fingerprint; try EncryptionKeychain.save(pins, key: key)
            self.peers[id] = value
            return value
        }
        fetching[id] = task
        defer { if expected == context { fetching[id] = nil } }
        return try await task.value
    }
    func prepare(_ kind: String, payload: CommandPayload, state: AppState) async throws -> CommandPayload {
        guard kind == "journal.save" || kind == "message.send" else { return payload }
        let identity = try requireLocal(), expected = context
        guard identity.bundle.userID == state.currentUserID.uuidString else { throw EndToEndCrypto.invalid() }
        let id = payload.id ?? UUID()
        var result = payload
        let connection = state.activeConnection(for: state.currentUserID)
        if kind == "message.send" {
            guard let connection, connection.id == payload.connectionID, let text = payload.text?.trimmingCharacters(in: .whitespacesAndNewlines),
                  !text.isEmpty, text.unicodeScalars.count <= 4000 else { throw DearlyError.invalid("Enter a message for your current companion.") }
            var recipients: [EncryptionIdentity] = []
            for member in connection.members { recipients.append(try await peer(member)) }
            guard expected == context else { throw CancellationError() }
            result.clientID = id; result.text = try EndToEndCrypto.seal(EncryptedTextContent(text: text), identity: identity, purpose: "message", id: id, connectionID: connection.id, recipients: recipients)
        } else {
            let title = (payload.title ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            let body = (payload.body ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            let passage = (payload.sharedText ?? "").trimmingCharacters(in: .whitespacesAndNewlines)
            guard !body.isEmpty, body.unicodeScalars.count <= 20000, title.unicodeScalars.count <= 160 else { throw DearlyError.invalid("Check your journal title and text length.") }
            if payload.audience != "privateOnly" && (passage.isEmpty || !body.contains(passage)) { throw DearlyError.invalid("The shared passage must be part of your journal entry.") }
            result.title = ""; result.clientID = payload.id == nil ? id : nil
            result.body = try EndToEndCrypto.seal(EncryptedJournalContent(title: title, body: body), identity: identity, purpose: "journal", id: id, recipients: [identity.bundle])
            if payload.audience == "companion" {
                guard let connection else { throw DearlyError.invalid("You don’t have a connection yet.") }
                var recipients: [EncryptionIdentity] = []
                for member in connection.members { recipients.append(try await peer(member)) }
                guard expected == context else { throw CancellationError() }
                result.sharedText = try EndToEndCrypto.seal(EncryptedTextContent(text: passage), identity: identity, purpose: "passage", id: id, connectionID: connection.id, recipients: recipients)
            }
        }
        return result
    }
    func journal(_ row: Journal) async -> Journal {
        var value = row
        if row.body.hasPrefix(EndToEndCrypto.prefix) {
            do {
                let sender = try await peer(row.authorID)
                let content: EncryptedJournalContent = try EndToEndCrypto.open(row.body, identity: requireLocal(), purpose: "journal", id: row.id, sender: sender)
                value.title = content.title; value.body = content.body; value.encrypted = true; value.locked = false
            } catch { value.title = L("Locked entry"); value.body = L(lockedText); value.encrypted = true; value.locked = true }
        }
        if row.sharedText.hasPrefix(EndToEndCrypto.prefix) {
            do {
                let sender = try await peer(row.authorID)
                let content: EncryptedTextContent = try EndToEndCrypto.open(row.sharedText, identity: requireLocal(), purpose: "passage", id: row.id, connectionID: row.connectionID, sender: sender)
                value.sharedText = content.text
            } catch { value.sharedText = L(lockedText); value.locked = true }
        }
        return value
    }
    func message(_ row: ChatMessage) async -> ChatMessage {
        guard row.text.hasPrefix(EndToEndCrypto.prefix) else { return row }
        var value = row
        do {
            let sender = try await peer(row.senderID)
            let content: EncryptedTextContent = try EndToEndCrypto.open(row.text, identity: requireLocal(), purpose: "message", id: row.id, connectionID: row.connectionID, sender: sender)
            value.text = content.text; value.encrypted = true; value.locked = false
        } catch { value.text = L(lockedText); value.encrypted = true; value.locked = true }
        return value
    }
    func decoded(_ state: AppState) async -> AppState {
        var value = state
        for index in value.journals.indices { value.journals[index] = await journal(value.journals[index]) }
        for index in value.messages.indices { value.messages[index] = await message(value.messages[index]) }
        return value
    }
    func dataExport(_ data: Data, decrypt: Bool) async throws -> Data {
        guard var value = try JSONSerialization.jsonObject(with: data) as? [String: Any] else { throw EndToEndCrypto.invalid() }
        if decrypt {
            _ = try requireLocal()
            let originalJournals = value["journals"] as? [[String: Any]] ?? [], originalMessages = value["messages"] as? [[String: Any]] ?? []
            value["encryptedOriginal"] = ["journals": originalJournals, "messages": originalMessages]
            var journals: [Journal] = try JSONDecoder().decode([Journal].self, from: JSONSerialization.data(withJSONObject: originalJournals))
            var messages: [ChatMessage] = try JSONDecoder().decode([ChatMessage].self, from: JSONSerialization.data(withJSONObject: originalMessages))
            for index in journals.indices { journals[index] = await journal(journals[index]) }
            for index in messages.indices { messages[index] = await message(messages[index]) }
            value["journals"] = try JSONSerialization.jsonObject(with: JSONEncoder().encode(journals))
            value["messages"] = try JSONSerialization.jsonObject(with: JSONEncoder().encode(messages))
            value["contentEncoding"] = "decrypted on your device; locked records keep their encrypted originals"
        } else { value["contentEncoding"] = "original; encrypted entries need your recovery code" }
        return try JSONSerialization.data(withJSONObject: value, options: [.prettyPrinted, .sortedKeys])
    }
}
