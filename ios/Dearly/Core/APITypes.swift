import Foundation

struct CommandPayload: Encodable {
    var id: UUID? = nil
    var title: String? = nil
    var body: String? = nil
    var sharedText: String? = nil
    var audience: String? = nil
    var anonymous: Bool? = nil
    var commentsEnabled: Bool? = nil
    var support: String? = nil
    var userID: UUID? = nil
    var journalID: UUID? = nil
    var connectionID: UUID? = nil
    var text: String? = nil
    var enabled: Bool? = nil
    var paused: Bool? = nil
    var reason: String? = nil
    var nickname: String? = nil
    var bio: String? = nil
    var interests: [String]? = nil
    var pace: String? = nil
    var status: String? = nil
    var suspended: Bool? = nil
    var birthDate: String? = nil
    var role: String? = nil
}

struct StateEnvelope: Decodable {
    var state: AppState
    var serverNow: Date
}

struct ChatEvent: Decodable, Sendable {
    var type: String
    var message: ChatMessage?
}

struct MessagePage: Decodable {
    var items: [ChatMessage]
    var nextCursor: UUID?
}

struct JournalPage: Decodable {
    var items: [Journal]
    var nextCursor: UUID?
}

struct ConnectionPage: Decodable {
    var items: [Connection]
    var profiles: [Profile]
    var nextCursor: UUID?
}

struct APIError: LocalizedError {
    var status: Int
    var message: String
    var errorDescription: String? { L(message) }
}

