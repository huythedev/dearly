import Foundation
import Combine

@MainActor
final class DearlyStore: ObservableObject {
    @Published private(set) var state: AppState
    @Published var errorMessage: String?
    @Published var notice: String?
    @Published private(set) var isOnline = false
    @Published private(set) var isBusy = false
    @Published private(set) var isAuthenticating = false
    @Published private(set) var syncError: String?
    @Published private(set) var serverAddress = ""
    @Published private(set) var lastSync: Date?
    var foreground = true
    private var api: APIClient?
    private var generation = UUID()
    private var etag: String?
    private var refreshing = false
    private var serverClockOffset: TimeInterval = 0
    var now: Date {
        Date().addingTimeInterval(serverClockOffset)
    }
    var calendar: Calendar {
        var calendar = Calendar.current
        calendar.timeZone = TimeZone(secondsFromGMT: 0)!
        return calendar
    }
    var me: Profile { state.currentUser }
    var role: AccountRole { AccountRole(rawValue: state.currentUserRole ?? "") ?? .user }
    func hasPermission(_ permission: String) -> Bool { isOnline && (state.permissions?.contains(permission) ?? false) }
    var connection: Connection? { state.activeConnection(for: me.id) }
    var partner: Profile? { connection?.members.first(where: { $0 != me.id }).flatMap { state.profile($0) } }

    init() {
        state = .signedOut()
    }

    func authenticate(address: String, username: String, password: String, nickname: String?, birthDate: String?) async -> Bool {
        guard !isBusy, !isAuthenticating else { return false }
        isAuthenticating = true
        defer { isAuthenticating = false }
        do {
            let url = try APIClient.validatedURL(address)
            let loginAPI = APIClient(baseURL: url)
            let record = try await loginAPI.authenticate(username: username.lowercased(), password: password, nickname: nickname, birthDate: birthDate)
            let client = APIClient(baseURL: url, token: record.token)
            let (envelope, tag) = try await client.fetchState(etag: nil)
            guard let envelope, envelope.state.profile(record.userID) != nil, envelope.state.currentUserID == record.userID else {
                throw DearlyError.invalid(L("Dữ liệu đăng nhập không hợp lệ."))
            }
            try SessionKeychain.save(record)
            generation = UUID(); api = client; etag = tag
            state = envelope.state; isOnline = true; serverAddress = record.baseURL
            serverClockOffset = envelope.serverNow.timeIntervalSinceNow
            lastSync = Date(); errorMessage = nil; syncError = nil
            UserDefaults.standard.set(record.baseURL, forKey: "dearly.server.address")
            return true
        } catch { errorMessage = error.localizedDescription; return false }
    }

    func restoreSession() async {
        guard !isOnline, !isAuthenticating, let record = SessionKeychain.load() else { return }
        isAuthenticating = true
        defer { isAuthenticating = false }
        do {
            let client = APIClient(baseURL: try APIClient.validatedURL(record.baseURL), token: record.token)
            let (envelope, tag) = try await client.fetchState(etag: nil)
            guard let envelope, envelope.state.currentUserID == record.userID, envelope.state.profile(record.userID) != nil else { throw DearlyError.invalid(L("Phiên không hợp lệ.")) }
            generation = UUID(); api = client; etag = tag; state = envelope.state
            isOnline = true; serverAddress = record.baseURL; lastSync = Date()
            serverClockOffset = envelope.serverNow.timeIntervalSinceNow
        } catch {
            if (error as? APIError)?.status == 401 { SessionKeychain.clear() }
            errorMessage = L("Chưa khôi phục được phiên server. Vui lòng thử đăng nhập lại. \(error.localizedDescription)", "Couldn’t restore your session. Please log in again. \(error.localizedDescription)")
        }
    }

    func logout() async {
        guard !isBusy, !isAuthenticating else { return }
        isBusy = true
        defer { isBusy = false }
        // Require acknowledgement; do not claim server revocation while offline.
        do {
            if let api { try await api.logout() }
            disconnect()
        } catch { errorMessage = L("Chưa thu hồi được phiên trên server. \(error.localizedDescription)", "Couldn’t revoke the server session. \(error.localizedDescription)") }
    }

    private func disconnect() {
        generation = UUID(); api = nil; etag = nil; refreshing = false
        SessionKeychain.clear(); state = .signedOut(); isOnline = false
        serverAddress = ""; syncError = nil; lastSync = nil
    }

    @discardableResult
    func refresh(force: Bool = false) async -> Bool {
        guard let client = api, !refreshing else { return false }
        let expected = generation
        refreshing = true
        defer { if expected == generation { refreshing = false } }
        do {
            let (envelope, tag) = try await client.fetchState(etag: force ? nil : etag)
            guard expected == generation else { return false }
            if let envelope {
                guard envelope.state.profile(envelope.state.currentUserID) != nil else { throw DearlyError.invalid(L("Server thiếu hồ sơ tài khoản.")) }
                var updated = envelope.state
                // Preserve only already paged immutable messages in the still-active connection.
                if let connection = updated.activeConnection(for: updated.currentUserID) {
                    let newIDs = Set(updated.messages.map(\.id))
                    updated.messages.append(contentsOf: state.messages.filter { $0.connectionID == connection.id && !newIDs.contains($0.id) })
                    updated.messages.sort { $0.date == $1.date ? $0.id.uuidString < $1.id.uuidString : $0.date < $1.date }
                    if updated.messages.count > 500 { updated.messages = Array(updated.messages.suffix(500)) }
                }
                state = updated; serverClockOffset = envelope.serverNow.timeIntervalSinceNow
            }
            etag = tag; lastSync = Date(); syncError = nil
            return true
        } catch {
            guard expected == generation else { return false }
            if (error as? APIError)?.status == 401 {
                disconnect(); errorMessage = L("Phiên đã hết hạn. Đăng nhập lại để tiếp tục.")
            } else { syncError = error.localizedDescription }
            return false
        }
    }

    func syncLoop() async {
        await restoreSession()
        var delay: UInt64 = 3
        while !Task.isCancelled {
            do { try await Task.sleep(nanoseconds: delay * 1_000_000_000) } catch { return }
            if foreground && isOnline && !isBusy && !isAuthenticating {
                delay = await refresh() ? 3 : min(delay * 2, 30)
            } else { delay = 3 }
        }
    }

    @discardableResult
    private func execute(_ kind: String, _ payload: CommandPayload, local: (inout AppState) throws -> Void) async -> Bool {
        guard !isBusy, !isAuthenticating else { return false }
        guard let client = api, isOnline else {
            errorMessage = L("Vui lòng đăng nhập server để tiếp tục.")
            return false
        }
        isBusy = true
        let expected = generation
        defer { isBusy = false }
        do {
            try await client.command(kind: kind, payload: payload)
            guard expected == generation else { return false }
            errorMessage = nil
            // If a background read is already in flight, wait for it before requesting the committed state.
            while refreshing && expected == generation { try await Task.sleep(nanoseconds: 50_000_000) }
            guard expected == generation else { return false }
            let synced = await refresh(force: true)
            if !synced && isOnline { notice = L("Server đã lưu thay đổi. App sẽ đồng bộ lại khi mạng ổn định.") }
            return true
        } catch {
            if expected == generation {
                if (error as? APIError)?.status == 401 { disconnect() }
                errorMessage = error.localizedDescription
            }
            return false
        }
    }

    func saveJournal(id: UUID?, title: String, body: String, sharedText: String, audience: Audience,
                     anonymous: Bool, commentsEnabled: Bool, support: SupportStyle) async -> Bool {
        let date = now
        return await execute("journal.save", CommandPayload(id: id, title: title, body: body, sharedText: sharedText,
            audience: audience.rawValue, anonymous: anonymous, commentsEnabled: commentsEnabled, support: support.rawValue)) {
            try $0.saveJournal(id: id, title: title, body: body, sharedText: sharedText, audience: audience,
                anonymous: anonymous, commentsEnabled: commentsEnabled, support: support, now: date)
        }
    }
    func deleteJournal(_ id: UUID) async -> Bool {
        await execute("journal.delete", CommandPayload(id: id)) { $0.deleteJournal(id) }
    }
    func toggleListening(_ journal: Journal) async {
        let enabled = !journal.listeners.contains(me.id)
        _ = await execute("journal.listen", CommandPayload(id: journal.id, enabled: enabled)) { $0.toggleListening(journal.id) }
    }
    func comment(on id: UUID, text: String) async -> Bool {
        let date = now
        return await execute("journal.comment", CommandPayload(id: id, text: text)) { try $0.comment(on: id, text: text, now: date) }
    }
    func canInvitePost(_ journal: Journal) -> Bool {
        isOnline ? journal.canInviteAuthor == true : state.canInvite(journal.authorID)
    }
    func invite(_ userID: UUID, journalID: UUID? = nil) async -> Bool {
        let date = now
        return await execute("invitation.send", CommandPayload(userID: journalID == nil ? userID : nil, journalID: journalID)) { try $0.invite(userID, now: date) }
    }
    func accept(_ id: UUID) async {
        let date = now
        _ = await execute("invitation.accept", CommandPayload(id: id)) { try $0.accept(id, now: date) }
    }
    func dismissInvitation(_ id: UUID) async {
        _ = await execute("invitation.dismiss", CommandPayload(id: id)) { $0.dismissInvitation(id) }
    }
    func send(_ text: String, connectionID: UUID) async -> Bool {
        let date = now
        return await execute("message.send", CommandPayload(connectionID: connectionID, text: text)) { try $0.send(text, now: date) }
    }
    func checkIn() async {
        guard let connection else { return }
        let date = now; let cal = calendar
        _ = await execute("connection.checkin", CommandPayload(connectionID: connection.id)) { try $0.checkIn(now: date, calendar: cal) }
    }
    func togglePause() async {
        guard let connection else { return }
        _ = await execute("connection.pause", CommandPayload(connectionID: connection.id, paused: !connection.paused)) { $0.togglePause() }
    }
    func leave() async -> Bool {
        guard let connection else { return false }
        let date = now
        return await execute("connection.leave", CommandPayload(connectionID: connection.id)) { $0.leave(now: date) }
    }
    func block(_ id: UUID, journalID: UUID? = nil) async -> Bool {
        let date = now
        return await execute("user.block", CommandPayload(userID: journalID == nil ? id : nil, journalID: journalID)) { $0.block(id, now: date) }
    }
    func report(_ id: UUID, journalID: UUID? = nil, reason: String) async -> Bool {
        let date = now; let reporter = me.id
        let success = await execute("report.create", CommandPayload(userID: journalID == nil ? id : nil, journalID: journalID, reason: reason)) {
            $0.reports.append(LocalReport(reporterID: reporter, reportedID: id, reason: reason, date: date))
        }
        if success { notice = L("Đã gửi báo cáo tới server để quản trị viên xem xét.") }
        return success
    }
    func loadOlderMessages(connectionID: UUID, before: UUID?) async -> Bool {
        guard let client = api, !isBusy else { return false }
        let expected = generation
        isBusy = true
        defer { isBusy = false }
        do {
            let page = try await client.messages(connectionID: connectionID, before: before)
            guard expected == generation, connection?.id == connectionID else { return false }
            let existing = Set(state.messages.map(\.id))
            state.messages.insert(contentsOf: page.items.filter { !existing.contains($0.id) }, at: 0)
            if state.messages.count > 500 { state.messages = Array(state.messages.suffix(500)) }
            return page.nextCursor != nil && state.messages.count < 500
        } catch { errorMessage = error.localizedDescription; return true }
    }
    func updateProfile(nickname: String, bio: String, interests: [String], support: SupportStyle, pace: String) async -> Bool {
        await execute("profile.update", CommandPayload(support: support.rawValue, nickname: nickname, bio: bio, interests: interests, pace: pace)) { state in
            guard let index = state.profiles.firstIndex(where: { $0.id == state.currentUserID }) else { return }
            state.profiles[index].nickname = nickname; state.profiles[index].bio = bio
            state.profiles[index].interests = interests; state.profiles[index].support = support; state.profiles[index].pace = pace
        }
    }

    func journalPage(before: UUID?) async throws -> JournalPage {
        guard let client = api else { throw DearlyError.invalid(L("Cần kết nối server để xem các trang cũ.")) }
        let expected = generation
        let result = try await client.journals(before: before)
        guard expected == generation else { throw CancellationError() }
        return result
    }

    // Staff payloads live only in the presented screen; never in the personal snapshot/cache.
    private func staffRead<T>(_ permission: String, operation: (APIClient) async throws -> T) async throws -> T {
        guard let client = api, hasPermission(permission) else {
            throw APIError(status: 403, message: L("Không có quyền truy cập.", "Access denied."))
        }
        let expected = generation
        do {
            let result = try await operation(client)
            guard expected == generation, hasPermission(permission) else { throw CancellationError() }
            return result
        } catch {
            if expected == generation {
                if (error as? APIError)?.status == 401 { disconnect() }
                if (error as? APIError)?.status == 403 { _ = await refresh(force: true) }
            }
            throw error
        }
    }

    func staffReports(status: String, before: UUID?) async throws -> StaffPage<StaffReport> {
        try await staffRead("reports.read") { try await $0.staffReports(status: status, before: before) }
    }
    func staffUsers(query: String, before: UUID?) async throws -> StaffPage<StaffUser> {
        try await staffRead("users.read") { try await $0.staffUsers(query: query, before: before) }
    }
    func staffAudit(before: Int?) async throws -> AuditPage {
        try await staffRead("audit.read") { try await $0.staffAudit(before: before) }
    }
    func staffCommand(_ kind: String, payload: CommandPayload) async -> Bool {
        let success = await execute(kind, payload) { _ in }
        if !success, isOnline { _ = await refresh(force: true) }
        return success
    }
}
