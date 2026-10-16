import Foundation

enum AccountRole: String, Codable, CaseIterable {
    case user, moderator, admin
    var title: String {
        switch self {
        case .user: return L("Member")
        case .moderator: return L("Moderator")
        case .admin: return L("Admin")
        }
    }
}

struct StaffPage<Item: Decodable>: Decodable {
    var items: [Item]
    var nextCursor: UUID?
}

struct StaffReport: Decodable, Identifiable {
    var id: UUID
    var reporterID: UUID
    var reportedID: UUID
    var reporterNickname: String
    var reportedNickname: String
    var reason: String
    var status: String
    var date: Date
    var journalID: UUID?
    var evidence: String
    var canHide: Bool
    var canRestore: Bool?
    var reviewNote: String
    var reviewerID: String?
    var reviewedAt: Date?
}

enum ReportStatus: String, CaseIterable {
    case open, reviewed, dismissed
    var title: String {
        switch self {
        case .open: return L("Open")
        case .reviewed: return L("Reviewed")
        case .dismissed: return L("Dismissed")
        }
    }
}

struct StaffUser: Decodable, Identifiable {
    var id: UUID
    var username: String
    var nickname: String
    var role: AccountRole
    var suspended: Bool
    var ageVerified: Bool
    var birthDate: String
}

struct AuditPage: Decodable {
    var items: [AuditEntry]
    var nextCursor: Int?
}

struct AuditEntry: Decodable, Identifiable {
    struct Detail: Decodable {
        var reason: String?
        var note: String?
        var from: String?
        var to: String?
        var status: String?
    }
    var id: Int
    var actorID: String
    var actorName: String
    var action: String
    var targetID: String
    var detail: Detail
    var date: Date
    var title: String {
        switch action {
        case "user.role": return L("Role changed")
        case "user.suspend": return L("Account suspended")
        case "user.restore": return L("Account restored")
        case "user.verify_age": return L("Age verified")
        case "report.review": return L("Report reviewed")
        case "report.hide": return L("Community post hidden")
        case "report.restore": return L("Sharing restriction removed")
        default: return action
        }
    }
}
