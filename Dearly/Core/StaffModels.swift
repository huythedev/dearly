import Foundation

enum AccountRole: String, Codable, CaseIterable {
    case user, moderator, admin
    var title: String {
        switch self {
        case .user: return L("Thành viên", "Member")
        case .moderator: return L("Kiểm duyệt viên", "Moderator")
        case .admin: return L("Quản trị viên", "Admin")
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
    var reviewNote: String
    var reviewerID: String?
    var reviewedAt: Date?
}

enum ReportStatus: String, CaseIterable {
    case open, reviewed, dismissed
    var title: String {
        switch self {
        case .open: return L("Chờ xử lý", "Open")
        case .reviewed: return L("Đã xem xét", "Reviewed")
        case .dismissed: return L("Đã bác bỏ", "Dismissed")
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
        case "user.role": return L("Đổi vai trò", "Role changed")
        case "user.suspend": return L("Khóa tài khoản", "Account suspended")
        case "user.restore": return L("Mở lại tài khoản", "Account restored")
        case "user.verify_age": return L("Xác minh tuổi", "Age verified")
        case "report.review": return L("Xem xét báo cáo", "Report reviewed")
        case "report.hide": return L("Ẩn bài cộng đồng", "Community post hidden")
        default: return action
        }
    }
}
