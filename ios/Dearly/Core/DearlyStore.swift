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
    @Published private(set) var isChatConnected = false
    var foreground = true {
        didSet {
            guard foreground != oldValue else { return }
            if foreground { startChat() } else { stopChat() }
        }
    }
    private var api: APIClient?
    private var generation = UUID()
    private var etag: String?
    private let synchronizer = StateSynchronizer()
    private var chatGeneration = UUID()
    private var chatTask: Task<Void, Never>?
    private var serverClockOffset: TimeInterval = 0
    var now: Date {
        Date().addingTimeInterval(serverClockOffset)
    }
    var calendar: Calendar {
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = TimeZone(secondsFromGMT: 0)!
        return calendar
    }
    var me: Profile { state.currentUser }
    var role: AccountRole { AccountRole(rawValue: state.currentUserRole ?? "") ?? .user }
    func hasPermission(_ permission: String) -> Bool { isOnline && role.allows(permission, granted: state.permissions) }
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
                throw DearlyError.invalid(L("The sign-in data is invalid."))
            }
            try SessionKeychain.save(record)
            synchronizer.invalidate()
            generation = UUID(); api = client; etag = tag
            state = envelope.state; isOnline = true; serverAddress = record.baseURL
            serverClockOffset = envelope.serverNow.timeIntervalSinceNow
            lastSync = Date(); errorMessage = nil; syncError = nil
            UserDefaults.standard.set(record.baseURL, forKey: "dearly.server.address")
            startChat()
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
            guard let envelope, envelope.state.currentUserID == record.userID, envelope.state.profile(record.userID) != nil else { throw DearlyError.invalid(L("This session is invalid.")) }
            synchronizer.invalidate()
            generation = UUID(); api = client; etag = tag; state = envelope.state
            isOnline = true; serverAddress = record.baseURL; lastSync = Date()
            serverClockOffset = envelope.serverNow.timeIntervalSinceNow
            startChat()
        } catch {
            if (error as? APIError)?.status == 401 { SessionKeychain.clear() }
            errorMessage = LF("Couldn’t restore your session. Please log in again. %1$@", String(describing: error.localizedDescription))
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
        } catch {
            if (error as? APIError)?.status == 401 { disconnect() }
            else { errorMessage = LF("Couldn’t revoke the server session. %1$@", String(describing: error.localizedDescription)) }
        }
    }

    private func disconnect() {
        stopChat()
        generation = UUID(); api = nil; etag = nil; synchronizer.invalidate()
        SessionKeychain.clear(); state = .signedOut(); isOnline = false; isBusy = false
        serverAddress = ""; syncError = nil; lastSync = nil; serverClockOffset = 0
    }

    @discardableResult
    func refresh(force: Bool = false) async -> Bool {
        await synchronizer.refresh(force: force) { [weak self] force in
            guard let self else { return false }
            return await self.readSnapshot(force: force)
        }
    }

    private func readSnapshot(force: Bool) async -> Bool {
        guard let client = api else { return false }
        let expected = generation
        do {
            let (envelope, tag) = try await client.fetchState(etag: force ? nil : etag)
            guard expected == generation else { return false }
            if let envelope {
                guard envelope.state.currentUserID == state.currentUserID,
                      envelope.state.profile(envelope.state.currentUserID) != nil else {
                    throw DearlyError.invalid(L("The server returned an invalid account profile."))
                }
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
                disconnect(); errorMessage = L("Your session has expired. Log in to continue.")
            } else { syncError = error.localizedDescription }
            return false
        }
    }

    func syncLoop() async {
        await restoreSession()
        if chatTask == nil { startChat() }
        defer { stopChat() }
        var delay: UInt64 = 3
        while !Task.isCancelled {
            do { try await Task.sleep(nanoseconds: delay * 1_000_000_000) } catch { return }
            if foreground && isOnline && !isBusy && !isAuthenticating {
                delay = await refresh() ? (isChatConnected ? 15 : 3) : min(delay * 2, 30)
            } else { delay = 3 }
        }
    }

    private func stopChat() {
        chatGeneration = UUID()
        chatTask?.cancel(); chatTask = nil; isChatConnected = false
    }

    private func startChat() {
        stopChat()
        guard foreground, isOnline, let client = api else { return }
        let expected = generation
        let socketID = chatGeneration
        chatTask = Task { [weak self] in
            var delay: UInt64 = 1
            while !Task.isCancelled, self?.generation == expected, self?.chatGeneration == socketID, self?.foreground == true {
                do {
                    try await client.listenForChat { [weak self] event in
                        await self?.receiveChat(event, generation: expected, socketID: socketID)
                    }
                } catch {
                    guard !Task.isCancelled, let self, self.generation == expected, self.chatGeneration == socketID else { return }
                    if self.isChatConnected { delay = 1 }
                    self.isChatConnected = false
                    // REST checks expiry/suspension and remains the compatibility fallback.
                    _ = await self.refresh(force: true)
                }
                guard !Task.isCancelled, self?.generation == expected, self?.chatGeneration == socketID else { return }
                do { try await Task.sleep(nanoseconds: delay * 1_000_000_000) } catch { return }
                delay = min(delay * 2, 30)
            }
        }
    }

    private func receiveChat(_ event: ChatEvent, generation expected: UUID, socketID: UUID) async {
        guard generation == expected, chatGeneration == socketID, !Task.isCancelled, isOnline, foreground else { return }
        switch event.type {
        case "ready":
            isChatConnected = true
            _ = await refresh(force: true) // Reconcile anything missed while disconnected.
        case "message":
            if let message = event.message { state.receiveLiveMessage(message) }
        case "state.changed":
            _ = await refresh(force: true)
        default: break
        }
    }

    @discardableResult
    private func execute(_ kind: String, _ payload: CommandPayload, staff: Bool = false) async -> Bool {
        guard !isBusy, !isAuthenticating else { return false }
        guard let client = api, isOnline else {
            errorMessage = L("Please log in to continue.")
            return false
        }
        isBusy = true
        let expected = generation
        defer { if expected == generation { isBusy = false } }
        do {
            try await client.command(kind: kind, payload: payload)
            guard expected == generation else { return false }
            errorMessage = nil
            let synced = await refresh(force: true)
            guard expected == generation else { return false }
            if !synced && isOnline { notice = L("Your changes are saved on the server. The app will sync when the connection improves.") }
            return true
        } catch {
            if expected == generation {
                if staff && (error as? APIError)?.status == 403 { state.permissions = [] }
                if (error as? APIError)?.status == 401 { disconnect() }
                errorMessage = error.localizedDescription
            }
            return false
        }
    }

    func saveJournal(id: UUID?, title: String, body: String, sharedText: String, audience: Audience,
                     anonymous: Bool, commentsEnabled: Bool, support: SupportStyle) async -> Bool {
        await execute("journal.save", CommandPayload(id: id, title: title, body: body, sharedText: sharedText,
            audience: audience.rawValue, anonymous: anonymous, commentsEnabled: commentsEnabled, support: support.rawValue))
    }
    func deleteJournal(_ id: UUID) async -> Bool {
        await execute("journal.delete", CommandPayload(id: id))
    }
    func toggleListening(_ journal: Journal) async {
        _ = await execute("journal.listen", CommandPayload(id: journal.id, enabled: !journal.listeners.contains(me.id)))
    }
    func comment(on id: UUID, text: String) async -> Bool {
        await execute("journal.comment", CommandPayload(id: id, text: text))
    }
    func canInvitePost(_ journal: Journal) -> Bool {
        !journal.anonymous && (isOnline ? journal.canInviteAuthor == true : state.canInvite(journal.authorID))
    }
    func invite(_ userID: UUID, journalID: UUID? = nil) async -> Bool {
        await execute("invitation.send", CommandPayload(userID: journalID == nil ? userID : nil, journalID: journalID))
    }
    func accept(_ id: UUID) async {
        _ = await execute("invitation.accept", CommandPayload(id: id))
    }
    func dismissInvitation(_ id: UUID) async {
        _ = await execute("invitation.dismiss", CommandPayload(id: id))
    }
    func send(_ text: String, connectionID: UUID) async -> Bool {
        await execute("message.send", CommandPayload(connectionID: connectionID, text: text))
    }
    func checkIn() async {
        guard let connection else { return }
        _ = await execute("connection.checkin", CommandPayload(connectionID: connection.id))
    }
    func togglePause() async {
        guard let connection else { return }
        _ = await execute("connection.pause", CommandPayload(connectionID: connection.id, paused: !connection.paused))
    }
    func leave() async -> Bool {
        guard let connection else { return false }
        return await execute("connection.leave", CommandPayload(connectionID: connection.id))
    }
    func block(_ id: UUID, journalID: UUID? = nil) async -> Bool {
        await execute("user.block", CommandPayload(userID: journalID == nil ? id : nil, journalID: journalID))
    }
    func hidePost(_ id: UUID) async -> Bool {
        await execute("journal.hide", CommandPayload(id: id))
    }
    func report(_ id: UUID, journalID: UUID? = nil, reason: String) async -> Bool {
        let success = await execute("report.create", CommandPayload(userID: journalID == nil ? id : nil, journalID: journalID, reason: reason))
        if success { notice = L("Your report has been sent for an administrator to review.") }
        return success
    }
    func loadOlderMessages(connectionID: UUID, before: UUID?) async -> Bool {
        guard api != nil, !isBusy else { return false }
        let expected = generation
        isBusy = true
        defer { if expected == generation { isBusy = false } }
        do {
            let page = try await accountRead { try await $0.messages(connectionID: connectionID, before: before) }
            guard expected == generation, connection?.id == connectionID else { return false }
            let existing = Set(state.messages.map(\.id))
            state.messages.insert(contentsOf: page.items.filter { !existing.contains($0.id) }, at: 0)
            if state.messages.count > 500 { state.messages = Array(state.messages.suffix(500)) }
            return page.nextCursor != nil && state.messages.count < 500
        } catch {
            guard expected == generation, connection?.id == connectionID else { return false }
            errorMessage = error.localizedDescription
            return true
        }
    }
    func updateProfile(nickname: String, bio: String, interests: [String], support: SupportStyle, pace: String) async -> Bool {
        await execute("profile.update", CommandPayload(support: support.rawValue, nickname: nickname, bio: bio, interests: interests, pace: pace))
    }

    private func accountRead<T>(_ operation: (APIClient) async throws -> T) async throws -> T {
        guard let client = api, isOnline else { throw APIError(status: 401, message: L("Please log in.")) }
        let expected = generation
        do {
            let page = try await operation(client)
            guard expected == generation else { throw CancellationError() }
            return page
        } catch {
            guard expected == generation else { throw CancellationError() }
            if (error as? APIError)?.status == 401 { disconnect() }
            throw error
        }
    }

    func journalPage(before: UUID?) async throws -> JournalPage {
        try await accountRead { try await $0.journals(before: before) }
    }

    func connectionPage(before: UUID?) async throws -> ConnectionPage {
        try await accountRead { try await $0.archivedConnections(before: before) }
    }

    // Staff payloads live only in the presented screen; never in the personal snapshot/cache.
    private func staffRead<T>(_ permission: String, operation: (APIClient) async throws -> T) async throws -> T {
        guard let client = api, hasPermission(permission) else {
            throw APIError(status: 403, message: L("Access denied."))
        }
        let expected = generation
        do {
            let result = try await operation(client)
            guard expected == generation, hasPermission(permission) else { throw CancellationError() }
            return result
        } catch {
            if expected == generation {
                if (error as? APIError)?.status == 401 { disconnect() }
                if (error as? APIError)?.status == 403 { state.permissions = []; _ = await refresh(force: true) }
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
        let permissions = ["staff.report.review": "reports.review", "staff.report.hide": "reports.hide",
                           "staff.report.restore": "reports.hide", "staff.user.role": "roles.manage",
                           "staff.user.suspend": "users.suspend", "staff.user.verify_age": "users.verify_age"]
        guard let permission = permissions[kind], hasPermission(permission) else {
            errorMessage = L("Access denied.")
            return false
        }
        let success = await execute(kind, payload, staff: true)
        if !success, isOnline { _ = await refresh(force: true) }
        return success
    }
}
