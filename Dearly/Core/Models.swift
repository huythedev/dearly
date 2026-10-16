import Foundation

enum Audience: String, Codable, CaseIterable, Identifiable {
    case privateOnly, companion, community
    var id: String { rawValue }
    var title: String {
        switch self {
        case .privateOnly: return "Chỉ mình tôi"
        case .companion: return "Bạn đồng hành"
        case .community: return "Cộng đồng"
        }
    }
    var icon: String {
        switch self {
        case .privateOnly: return "lock"
        case .companion: return "person.2"
        case .community: return "globe.asia.australia"
        }
    }
}

enum SupportStyle: String, Codable, CaseIterable, Identifiable {
    case listen = "Chỉ cần lắng nghe"
    case relate = "Chia sẻ trải nghiệm"
    case brainstorm = "Cùng nghĩ cách"
    var id: String { rawValue }
}

struct Profile: Codable, Identifiable, Equatable {
    var id: UUID
    var nickname: String
    var age: Int
    var symbol: String
    var bio: String
    var interests: [String]
    var support: SupportStyle
    var pace: String
    var ageVerified: Bool = true
}

struct Journal: Codable, Identifiable {
    var id = UUID()
    var authorID: UUID
    var title: String
    var body: String
    var sharedText: String
    var audience: Audience = .privateOnly
    var connectionID: UUID?
    var anonymous = false
    var commentsEnabled = true
    var support: SupportStyle = .listen
    var date: Date
    var listeners: Set<UUID> = []
    var canInviteAuthor: Bool?
}

struct JournalComment: Codable, Identifiable {
    var id = UUID()
    var journalID: UUID
    var authorID: UUID
    var text: String
    var date: Date
}

struct Invitation: Codable, Identifiable {
    var id = UUID()
    var senderID: UUID
    var recipientID: UUID
    var date: Date
}

struct ChatMessage: Codable, Identifiable {
    var id = UUID()
    var connectionID: UUID
    var senderID: UUID
    var text: String
    var date: Date
}

struct Connection: Codable, Identifiable {
    var id = UUID()
    var members: [UUID]
    var startedAt: Date
    var endedAt: Date?
    var paused = false
    var checkIns: [String: Set<UUID>] = [:]
    var bestStreak = 0
    var serverTotalDays: Int?
    var serverCurrentStreak: Int?
    var active: Bool { endedAt == nil }
    var totalDays: Int { serverTotalDays ?? checkIns.values.filter { Set(members).isSubset(of: $0) }.count }

    static func dayKey(_ date: Date, calendar: Calendar) -> String {
        let c = calendar.dateComponents([.year, .month, .day], from: date)
        return String(format: "%04d-%02d-%02d", c.year!, c.month!, c.day!)
    }

    func checkedIn(_ userID: UUID, on date: Date, calendar: Calendar) -> Bool {
        checkIns[Self.dayKey(date, calendar: calendar)]?.contains(userID) == true
    }

    func streak(on date: Date, calendar: Calendar) -> Int {
        if let serverCurrentStreak { return serverCurrentStreak }
        var cursor = calendar.startOfDay(for: date)
        func complete(_ day: Date) -> Bool {
            Set(members).isSubset(of: checkIns[Self.dayKey(day, calendar: calendar)] ?? [])
        }
        if !complete(cursor) { cursor = calendar.date(byAdding: .day, value: -1, to: cursor)! }
        var count = 0
        while complete(cursor) {
            count += 1
            cursor = calendar.date(byAdding: .day, value: -1, to: cursor)!
        }
        return count
    }

    var growth: Int {
        if totalDays >= 30 { return 5 }
        if bestStreak >= 14 { return 4 }
        if bestStreak >= 7 { return 3 }
        if bestStreak >= 3 { return 2 }
        return totalDays > 0 ? 1 : 0
    }
}

struct UserBlock: Codable {
    var blockerID: UUID
    var blockedID: UUID
}

struct LocalReport: Codable, Identifiable {
    var id = UUID()
    var reporterID: UUID
    var reportedID: UUID
    var reason: String
    var date: Date
}

enum DearlyError: LocalizedError {
    case invalid(String)
    var errorDescription: String? {
        switch self { case .invalid(let message): return message }
    }
}

struct AppState: Codable {
    var schemaVersion = 1
    var profiles: [Profile]
    var currentUserID: UUID
    var journals: [Journal]
    var comments: [JournalComment] = []
    var invitations: [Invitation] = []
    var connections: [Connection] = []
    var messages: [ChatMessage] = []
    var blocks: [UserBlock] = []
    var reports: [LocalReport] = []
    var demoDayOffset = 0
    var suggestedUserIDs: [UUID]?
    // Optional so an older server/fixture remains readable with no staff privileges.
    var currentUserRole: String?
    var permissions: [String]?

    static func signedOut() -> AppState {
        AppState(profiles: [], currentUserID: UUID(), journals: [])
    }

    var currentUser: Profile { profiles.first { $0.id == currentUserID }! }
    func profile(_ id: UUID) -> Profile? { profiles.first { $0.id == id } }
    func activeConnection(for id: UUID) -> Connection? {
        connections.first { $0.active && $0.members.contains(id) }
    }
    func isBlocked(_ a: UUID, _ b: UUID) -> Bool {
        blocks.contains { ($0.blockerID == a && $0.blockedID == b) || ($0.blockerID == b && $0.blockedID == a) }
    }
    // Demo age declarations only; production must enforce verified eligibility server-side.
    func eligible(_ a: UUID, _ b: UUID) -> Bool {
        guard a != b, let first = profile(a), let second = profile(b), !isBlocked(a, b) else { return false }
        guard first.age >= 16, second.age >= 16 else { return false }
        guard first.ageVerified, second.ageVerified else { return false }
        if first.age < 18 || second.age < 18 {
            return first.age < 18 && second.age < 18 && abs(first.age - second.age) <= 1
        }
        return true
    }
    func canInvite(_ id: UUID) -> Bool {
        eligible(currentUserID, id) && activeConnection(for: currentUserID) == nil && activeConnection(for: id) == nil
    }
    func canRead(_ journal: Journal) -> Bool {
        if journal.authorID == currentUserID { return true }
        guard !isBlocked(currentUserID, journal.authorID) else { return false }
        if journal.audience == .community { return true }
        return journal.audience == .companion && connections.contains {
            $0.id == journal.connectionID && $0.active && $0.members.contains(currentUserID)
        }
    }
    var feed: [Journal] {
        journals.filter { $0.audience == .community && canRead($0) }.sorted { $0.date > $1.date }
    }
    var myJournals: [Journal] {
        journals.filter { $0.authorID == currentUserID }.sorted { $0.date > $1.date }
    }
    var suggestions: [Profile] {
        profiles.filter { profile in
            if let suggestedUserIDs { return suggestedUserIDs.contains(profile.id) }
            return canInvite(profile.id)
        }.sorted {
            Set($0.interests).intersection(currentUser.interests).count > Set($1.interests).intersection(currentUser.interests).count
        }
    }

    mutating func saveJournal(id: UUID? = nil, title: String, body: String, sharedText: String,
                              audience: Audience, anonymous: Bool, commentsEnabled: Bool,
                              support: SupportStyle, now: Date) throws {
        let content = body.trimmingCharacters(in: .whitespacesAndNewlines)
        let excerpt = sharedText.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !content.isEmpty else { throw DearlyError.invalid("Viết vài dòng trước khi lưu nhé.") }
        if audience != .privateOnly && (excerpt.isEmpty || !content.contains(excerpt)) {
            throw DearlyError.invalid("Phần chia sẻ cần là toàn bài hoặc một đoạn có trong journal.")
        }
        let connection = activeConnection(for: currentUserID)
        if audience == .companion && connection == nil {
            throw DearlyError.invalid("Bạn cần một kết nối trước khi chia sẻ với bạn đồng hành.")
        }
        if let id, !journals.contains(where: { $0.id == id && $0.authorID == currentUserID }) {
            throw DearlyError.invalid("Không thể sửa journal này.")
        }
        let old = journals.first { $0.id == id }
        let entry = Journal(id: id ?? UUID(), authorID: currentUserID,
                            title: title.trimmingCharacters(in: .whitespacesAndNewlines), body: content,
                            sharedText: audience == .privateOnly ? "" : excerpt, audience: audience,
                            connectionID: audience == .companion ? connection?.id : nil,
                            anonymous: anonymous, commentsEnabled: commentsEnabled,
                            support: support, date: old?.date ?? now, listeners: old?.listeners ?? [])
        journals.removeAll { $0.id == entry.id }
        journals.append(entry)
        if audience != .community { comments.removeAll { $0.journalID == entry.id } }
    }

    mutating func deleteJournal(_ id: UUID) {
        guard journals.contains(where: { $0.id == id && $0.authorID == currentUserID }) else { return }
        journals.removeAll { $0.id == id }
        comments.removeAll { $0.journalID == id }
    }

    mutating func toggleListening(_ id: UUID) {
        guard let i = journals.firstIndex(where: { $0.id == id }), journals[i].audience == .community,
              journals[i].authorID != currentUserID, canRead(journals[i]) else { return }
        if journals[i].listeners.contains(currentUserID) { journals[i].listeners.remove(currentUserID) }
        else { journals[i].listeners.insert(currentUserID) }
    }

    mutating func comment(on id: UUID, text: String, now: Date) throws {
        guard let journal = journals.first(where: { $0.id == id }), canRead(journal),
              journal.audience == .community, journal.commentsEnabled else {
            throw DearlyError.invalid("Bài viết này hiện không nhận phản hồi.")
        }
        let value = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !value.isEmpty else { return }
        comments.append(JournalComment(journalID: id, authorID: currentUserID, text: value, date: now))
    }

    mutating func invite(_ id: UUID, now: Date) throws {
        guard canInvite(id) else { throw DearlyError.invalid("Kết nối này hiện không khả dụng.") }
        guard !invitations.contains(where: {
            Set([$0.senderID, $0.recipientID]) == Set([currentUserID, id])
        }) else { throw DearlyError.invalid("Đã có lời mời giữa hai bạn. Xem mục Đồng hành nhé.") }
        invitations.append(Invitation(senderID: currentUserID, recipientID: id, date: now))
    }

    mutating func accept(_ id: UUID, now: Date) throws {
        guard let invitation = invitations.first(where: { $0.id == id && $0.recipientID == currentUserID }),
              canInvite(invitation.senderID) else { throw DearlyError.invalid("Lời mời không còn khả dụng.") }
        let members = [invitation.senderID, currentUserID]
        connections.append(Connection(members: members, startedAt: now))
        invitations.removeAll { members.contains($0.senderID) || members.contains($0.recipientID) }
    }

    mutating func dismissInvitation(_ id: UUID) {
        let viewerID = currentUserID
        invitations.removeAll { $0.id == id && ($0.recipientID == viewerID || $0.senderID == viewerID) }
    }

    mutating func send(_ text: String, now: Date) throws {
        guard let connection = activeConnection(for: currentUserID) else {
            throw DearlyError.invalid("Hai người cần đồng ý kết nối trước khi chat.")
        }
        let value = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !value.isEmpty else { return }
        guard value.count <= 4000 else { throw DearlyError.invalid("Mỗi tin nhắn tối đa 4.000 ký tự nhé.") }
        messages.append(ChatMessage(connectionID: connection.id, senderID: currentUserID, text: value, date: now))
    }

    mutating func checkIn(now: Date, calendar: Calendar = .current) throws {
        guard let index = connections.firstIndex(where: { $0.active && $0.members.contains(currentUserID) }) else {
            throw DearlyError.invalid("Kết nối với một người để gieo hạt cùng nhau.")
        }
        guard !connections[index].paused else { throw DearlyError.invalid("Khu vườn đang nghỉ. Tiếp tục khi cả hai sẵn sàng nhé.") }
        let key = Connection.dayKey(now, calendar: calendar)
        connections[index].checkIns[key, default: []].insert(currentUserID)
        let streak = connections[index].streak(on: now, calendar: calendar)
        connections[index].bestStreak = max(connections[index].bestStreak, streak)
    }

    mutating func togglePause() {
        guard let index = connections.firstIndex(where: { $0.active && $0.members.contains(currentUserID) }) else { return }
        connections[index].paused.toggle()
    }

    mutating func leave(now: Date) {
        guard let index = connections.firstIndex(where: { $0.active && $0.members.contains(currentUserID) }) else { return }
        connections[index].endedAt = now
    }

    mutating func block(_ id: UUID, now: Date) {
        guard id != currentUserID else { return }
        blocks.append(UserBlock(blockerID: currentUserID, blockedID: id))
        let pair = Set([currentUserID, id])
        invitations.removeAll { Set([$0.senderID, $0.recipientID]) == pair }
        if let connection = activeConnection(for: currentUserID), connection.members.contains(id) { leave(now: now) }
    }

    static func demo(now: Date = Date()) -> AppState {
        let me = Profile(id: UUID(), nickname: "Mây", age: 17, symbol: "cloud.fill", bio: "Chậm một chút cũng được. Mình thích những cuộc trò chuyện thật lòng.", interests: ["Âm nhạc", "Đọc sách", "Đi dạo"], support: .listen, pace: "Buổi tối")
        let fern = Profile(id: UUID(), nickname: "Dương xỉ", age: 17, symbol: "leaf.fill", bio: "Một người nghe, mê nhạc indie và những ngày trời dịu.", interests: ["Âm nhạc", "Đi dạo", "Chụp ảnh"], support: .relate, pace: "Buổi tối")
        let sun = Profile(id: UUID(), nickname: "Nắng", age: 16, symbol: "sun.max.fill", bio: "Mình đang học cách bắt đầu những điều nhỏ.", interests: ["Đọc sách", "Vẽ"], support: .brainstorm, pace: "Vài lần mỗi tuần")
        let adult = Profile(id: UUID(), nickname: "Thông", age: 22, symbol: "tree.fill", bio: "Tài khoản demo nhóm người lớn.", interests: ["Âm nhạc"], support: .listen, pace: "Buổi tối")
        return AppState(profiles: [me, fern, sun, adult], currentUserID: me.id, journals: [
            Journal(authorID: me.id, title: "Một khoảng nhỏ cho mình", body: "Hôm nay mình muốn thử viết xuống những điều chưa biết kể với ai. Có lẽ bắt đầu bằng một câu thôi cũng đủ.", sharedText: "", date: now),
            Journal(authorID: fern.id, title: "", body: "Hôm nay mình ngồi lại sau giờ học, nghe hết một bài nhạc mà không làm gì khác. Một chuyện nhỏ, nhưng thấy ngày nhẹ hơn một chút.", sharedText: "Hôm nay mình ngồi lại sau giờ học, nghe hết một bài nhạc mà không làm gì khác. Một chuyện nhỏ, nhưng thấy ngày nhẹ hơn một chút.", audience: .community, support: .listen, date: now.addingTimeInterval(-3600)),
            Journal(authorID: sun.id, title: "", body: "Có ai cũng mất khá lâu để thấy mình thuộc về một nhóm bạn không? Mình vẫn đang tìm nhịp của mình.", sharedText: "Có ai cũng mất khá lâu để thấy mình thuộc về một nhóm bạn không? Mình vẫn đang tìm nhịp của mình.", audience: .community, anonymous: true, support: .relate, date: now.addingTimeInterval(-7200))
        ])
    }
}

// UI localization stays separate from Codable values sent to the backend.
enum AppLanguage {
    static var code: String { UserDefaults.standard.string(forKey: "dearly.language") == "en" ? "en" : "vi" }
    static var bundle: Bundle {
        guard let path = Bundle.main.path(forResource: code, ofType: "lproj"),
              let bundle = Bundle(path: path) else { return .main }
        return bundle
    }
}

func L(_ key: String) -> String {
    AppLanguage.bundle.localizedString(forKey: key, value: key, table: nil)
}

// Paired templates keep interpolated user names and content verbatim.
func L(_ vietnamese: String, _ english: String) -> String {
    AppLanguage.code == "en" ? english : vietnamese
}
