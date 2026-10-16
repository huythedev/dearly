import XCTest
@testable import Dearly

final class DearlyCoreTests: XCTestCase {
    @MainActor
    func testGuideReplaysAndKeepsCompletionScopedToAccountAndServer() throws {
        let suite = "dearly.guide.tests.\(UUID())"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }
        let guide = GuideProgress(defaults: defaults)
        let user = UUID()
        guide.configure(server: "https://first.example/", userID: user)
        XCTAssertEqual(guide.phase, .welcome)
        guide.start()
        XCTAssertEqual(guide.currentStep, .compose)
        guide.configure(server: "https://first.example", userID: user)
        XCTAssertEqual(guide.currentStep, .compose)
        guide.advance()
        XCTAssertEqual(guide.currentStep, .pages)
        guide.back()
        XCTAssertEqual(guide.currentStep, .compose)
        for _ in GuideStep.allCases { guide.advance() }
        XCTAssertFalse(guide.isPresented)
        guide.configure(server: nil, userID: nil)
        guide.configure(server: "https://first.example", userID: user)
        XCTAssertFalse(guide.isPresented)
        guide.start()
        XCTAssertEqual(guide.currentStep, .compose)
        guide.configure(server: "https://second.example", userID: user)
        XCTAssertEqual(guide.phase, .welcome)
        guide.dismiss()
        guide.configure(server: "https://second.example", userID: UUID())
        XCTAssertEqual(guide.phase, .welcome)
        guide.configure(server: nil, userID: nil)
        guide.start()
        XCTAssertFalse(guide.isPresented)
    }

    @MainActor
    func testGuideIgnoresStaleFramesAndClearsTargetsBetweenSteps() throws {
        let suite = "dearly.guide.frames.\(UUID())"
        let defaults = try XCTUnwrap(UserDefaults(suiteName: suite))
        defer { defaults.removePersistentDomain(forName: suite) }
        let guide = GuideProgress(defaults: defaults)
        guide.configure(server: "https://example.com", userID: UUID())
        guide.start()
        let owner = UUID(), oldOwner = UUID()
        let rect = CGRect(x: 10, y: 100, width: 200, height: 44)
        guide.record(.pages, rect: rect, owner: owner)
        XCTAssertTrue(guide.frames.isEmpty)
        guide.record(.compose, rect: rect, owner: owner)
        guide.remove(.compose, owner: oldOwner)
        XCTAssertEqual(guide.frames[.compose]?.rect, rect)
        guide.advance()
        XCTAssertTrue(guide.frames.isEmpty)
        guide.record(.pages, rect: .null, owner: owner)
        XCTAssertTrue(guide.frames.isEmpty)
        guide.record(.pages, rect: rect, owner: owner)
        guide.configure(server: nil, userID: nil)
        XCTAssertTrue(guide.frames.isEmpty)
    }

    func testGuideCardsStayWithinPortraitAndLandscapeSafeAreas() {
        for viewport in [CGRect(x: 0, y: 0, width: 320, height: 568), CGRect(x: 0, y: 0, width: 568, height: 320)] {
            let available = viewport.insetBy(dx: 16, dy: 32)
            for target in [CGRect(x: 25, y: 50, width: 200, height: 44), CGRect(x: 25, y: viewport.maxY - 90, width: 200, height: 44)] {
                let height = min(350, GuideLayout.maxHeight(target: target, available: available))
                let size = CGSize(width: min(380, available.width), height: height)
                let origin = GuideLayout.origin(target: target, card: size, available: available)
                XCTAssertTrue(available.contains(CGRect(origin: origin, size: size)))
            }
        }
        XCTAssertNil(GuideLayout.spotlight(CGRect(x: 10, y: 900, width: 100, height: 44), in: CGRect(x: 0, y: 0, width: 320, height: 568)))
    }

    @MainActor
    func testSnapshotsSerializeAndRetainInvalidationsDuringARead() async {
        let synchronizer = StateSynchronizer()
        let started = expectation(description: "Initial snapshot started")
        let joined = expectation(description: "Invalidations queued")
        joined.expectedFulfillmentCount = 2
        var release: CheckedContinuation<Void, Never>?
        var reads: [Bool] = []
        var active = 0
        var peak = 0
        let initial = Task {
            await synchronizer.refresh { force in
                active += 1; peak = max(peak, active)
                reads.append(force)
                if reads.count == 1 {
                    await withCheckedContinuation { continuation in
                        release = continuation; started.fulfill()
                    }
                }
                active -= 1
                return true
            }
        }
        await fulfillment(of: [started], timeout: 2)
        let second = Task {
            joined.fulfill()
            return await synchronizer.refresh(force: true) { _ in XCTFail("Use the active reader"); return false }
        }
        let third = Task {
            joined.fulfill()
            return await synchronizer.refresh(force: true) { _ in XCTFail("Use the active reader"); return false }
        }
        await fulfillment(of: [joined], timeout: 2)
        XCTAssertEqual(reads, [false])
        release?.resume()
        let results = await [initial.value, second.value, third.value]
        XCTAssertEqual(results, [true, true, true])
        XCTAssertEqual(reads, [false, true])
        XCTAssertEqual(peak, 1)
    }

    @MainActor
    func testSessionInvalidationCancelsOldSnapshotWithoutClearingNewWork() async {
        let synchronizer = StateSynchronizer()
        let started = expectation(description: "Old session read started")
        var release: CheckedContinuation<Void, Never>?
        let old = Task {
            await synchronizer.refresh { _ in
                await withCheckedContinuation { continuation in release = continuation; started.fulfill() }
                return !Task.isCancelled
            }
        }
        await fulfillment(of: [started], timeout: 2)
        synchronizer.invalidate()
        let fresh = await synchronizer.refresh(force: true) { force in force }
        XCTAssertTrue(fresh)
        release?.resume()
        let cancelled = await old.value
        XCTAssertFalse(cancelled)
        let next = await synchronizer.refresh { force in !force }
        XCTAssertTrue(next)
    }

    func testLocalNetworkPermissionExplainsWhyTheServerIsContacted() {
        let description = Bundle.main.object(forInfoDictionaryKey: "NSLocalNetworkUsageDescription") as? String
        XCTAssertTrue(description?.contains("server") == true)
    }

    func testNativeSocketURLUsesSameHostWithoutCredentialsInURL() throws {
        let server = try APIClient.validatedURL(APIClient.defaultServerAddress)
        XCTAssertEqual(server.absoluteString, "https://dearly.huythedev.com")
        let secure = try APIClient.chatURL(for: server)
        XCTAssertEqual(secure.absoluteString, "wss://dearly.huythedev.com/ws/chat")
        let local = try APIClient.chatURL(for: URL(string: "http://localhost:8002")!)
        XCTAssertEqual(local.absoluteString, "ws://localhost:8002/ws/chat")
        XCTAssertNil(secure.query)
    }

    func testLiveChatDTOAndDeduplicationRespectActiveConnection() throws {
        var state = try connected()
        let connection = try XCTUnwrap(state.activeConnection(for: state.currentUserID))
        let message = ChatMessage(connectionID: connection.id, senderID: connection.members[1], text: "A live hello", date: day)
        let data = try JSONSerialization.data(withJSONObject: ["type": "message", "message": JSONSerialization.jsonObject(with: JSONEncoder().encode(message))])
        let event = try JSONDecoder().decode(ChatEvent.self, from: data)
        let decoded = try XCTUnwrap(event.message)
        XCTAssertEqual(decoded.date, day)
        state.receiveLiveMessage(decoded); state.receiveLiveMessage(decoded)
        XCTAssertEqual(state.messages.filter { $0.id == message.id }.count, 1)
        state.receiveLiveMessage(ChatMessage(connectionID: UUID(), senderID: decoded.senderID, text: "Different connection", date: day))
        state.receiveLiveMessage(ChatMessage(connectionID: connection.id, senderID: UUID(), text: "Non-member", date: day))
        XCTAssertEqual(state.messages.count, 1)
        state.leave(now: day)
        state.receiveLiveMessage(ChatMessage(connectionID: connection.id, senderID: decoded.senderID, text: "Ended connection", date: day))
        XCTAssertFalse(state.messages.contains { $0.text == "Ended connection" })
    }

    @MainActor
    func testStoreStartsSignedOutWithoutSampleData() async {
        let store = DearlyStore()
        XCTAssertFalse(store.isOnline)
        XCTAssertTrue(store.state.profiles.isEmpty)
        XCTAssertTrue(store.state.journals.isEmpty)
        XCTAssertTrue(store.state.messages.isEmpty)
        XCTAssertEqual(store.me.id, store.state.currentUserID)
        XCTAssertEqual(store.me.nickname, "")
        XCTAssertFalse(store.me.ageVerified)
        XCTAssertEqual(store.calendar.identifier, .gregorian)
        XCTAssertEqual(store.calendar.timeZone.secondsFromGMT(), 0)
        let saved = await store.send("Requires a backend session", connectionID: UUID())
        XCTAssertFalse(saved)
        XCTAssertTrue(store.state.messages.isEmpty)
    }

    @MainActor
    func testEnglishSourceDefaultsAndVietnameseTranslation() {
        let defaults = UserDefaults.standard
        let previous = defaults.object(forKey: "dearly.language")
        defer {
            if let previous { defaults.set(previous, forKey: "dearly.language") }
            else { defaults.removeObject(forKey: "dearly.language") }
        }
        defaults.removeObject(forKey: "dearly.language")
        XCTAssertEqual(AppLanguage.code, "en")
        XCTAssertEqual(L("Log in"), "Log in")
        XCTAssertEqual(L("Garden"), "Garden")
        XCTAssertEqual(SupportStyle.listen.title, "Just listen")
        XCTAssertEqual(SupportStyle.listen.rawValue, "listen")
        XCTAssertEqual(LF("With %1$@", "Alex"), "With Alex")
        XCTAssertEqual(L("An untranslated future message"), "An untranslated future message")
        defaults.set("fr", forKey: "dearly.language")
        XCTAssertEqual(AppLanguage.code, "en")
        defaults.set("en", forKey: "dearly.language")
        XCTAssertEqual(L("Log in"), "Log in")
        defaults.set("vi", forKey: "dearly.language")
        XCTAssertEqual(AppLanguage.code, "vi")
        XCTAssertEqual(L("Log in"), "Đăng nhập")
        XCTAssertEqual(L("Garden"), "Khu vườn")
        XCTAssertEqual(SupportStyle.listen.title, "Chỉ cần lắng nghe")
        XCTAssertEqual(LF("With %1$@", "Mây %@"), "Cùng Mây %@")
        XCTAssertEqual(LF("%1$@ days · Best streak: %2$@", "30", "7"), "30 ngày · Chuỗi dài nhất: 7")
    }

    func testSupportStylesDecodeLegacyValuesAndEncodeCanonicalIdentifiers() throws {
        let legacy = ["Chỉ cần lắng nghe", "Chia sẻ trải nghiệm", "Cùng nghĩ cách"]
        for (style, value) in zip(SupportStyle.allCases, legacy) {
            let oldData = try JSONEncoder().encode(value)
            XCTAssertEqual(try JSONDecoder().decode(SupportStyle.self, from: oldData), style)
            let encoded = try JSONEncoder().encode(style)
            XCTAssertEqual(try JSONDecoder().decode(String.self, from: encoded), style.rawValue)
            XCTAssertEqual(try JSONDecoder().decode(SupportStyle.self, from: encoded), style)
        }
        XCTAssertThrowsError(try JSONDecoder().decode(SupportStyle.self, from: Data("\"unknown\"".utf8)))
    }

    private var calendar: Calendar {
        var value = Calendar(identifier: .gregorian)
        value.timeZone = TimeZone(secondsFromGMT: 0)!
        return value
    }
    private var day: Date { calendar.date(from: DateComponents(year: 2026, month: 10, day: 13, hour: 12))! }
    private func later(_ count: Int) -> Date { calendar.date(byAdding: .day, value: count, to: day)! }

    private func connected() throws -> AppState {
        var state = AppState.demo(now: day)
        let second = state.profiles[1].id
        try state.invite(second, now: day)
        state.currentUserID = second
        try state.accept(state.invitations[0].id, now: day)
        state.currentUserID = state.profiles[0].id
        return state
    }

    private func checkBoth(_ state: inout AppState, on date: Date) throws {
        let original = state.currentUserID
        let members = state.activeConnection(for: original)!.members
        for id in members { state.currentUserID = id; try state.checkIn(now: date, calendar: calendar) }
        state.currentUserID = original
    }

    func testPrivateJournalCannotBeReadByOtherPersona() throws {
        var state = AppState.demo(now: day)
        let privateEntry = state.myJournals[0]
        state.currentUserID = state.profiles[1].id
        XCTAssertFalse(state.canRead(privateEntry))
        XCTAssertFalse(state.feed.contains { $0.id == privateEntry.id })
    }

    func testPublishOnlyChosenExcerptAndWithdraw() throws {
        var state = AppState.demo(now: day)
        try state.saveJournal(title: "Private title", body: "Secret. Share this.", sharedText: "Share this.", audience: .community, anonymous: true, commentsEnabled: false, support: .listen, now: day)
        let entry = state.journals.last!
        XCTAssertEqual(entry.sharedText, "Share this.")
        XCTAssertTrue(entry.anonymous)
        try state.saveJournal(id: entry.id, title: entry.title, body: entry.body, sharedText: "", audience: .privateOnly, anonymous: false, commentsEnabled: false, support: .listen, now: day)
        state.currentUserID = state.profiles[1].id
        XCTAssertFalse(state.feed.contains { $0.id == entry.id })
        XCTAssertFalse(state.canRead(state.journals.first { $0.id == entry.id }!))
    }

    func testCannotShareTextOutsideOriginalJournal() {
        var state = AppState.demo(now: day)
        XCTAssertThrowsError(try state.saveJournal(title: "", body: "Original", sharedText: "Different", audience: .community, anonymous: false, commentsEnabled: true, support: .listen, now: day))
    }

    func testCannotEditAnotherUsersJournal() {
        var state = AppState.demo(now: day)
        let other = state.journals.first { $0.authorID != state.currentUserID }!
        XCTAssertThrowsError(try state.saveJournal(id: other.id, title: "", body: "Changed", sharedText: "", audience: .privateOnly, anonymous: false, commentsEnabled: true, support: .listen, now: day))
    }

    func testInvitationRequiresTwoSidesBeforeChat() throws {
        var state = AppState.demo(now: day)
        let first = state.currentUserID
        let second = state.profiles[1].id
        try state.invite(second, now: day)
        let invitation = state.invitations[0]
        XCTAssertThrowsError(try state.send("Hello", now: day))
        XCTAssertThrowsError(try state.accept(invitation.id, now: day))
        state.currentUserID = second
        try state.accept(invitation.id, now: day)
        XCTAssertNotNil(state.activeConnection(for: first))
        try state.send("Hello", now: day)
        XCTAssertEqual(state.messages.count, 1)
    }

    func testMinorCannotInviteAdultInEitherDirection() {
        var state = AppState.demo(now: day)
        let minor = state.currentUserID
        let adult = state.profiles[3].id
        XCTAssertFalse(state.canInvite(adult))
        XCTAssertThrowsError(try state.invite(adult, now: day))
        state.currentUserID = adult
        XCTAssertFalse(state.canInvite(minor))
        XCTAssertThrowsError(try state.invite(minor, now: day))
    }

    func testAgeEligibilityRecheckedWhenAccepting() throws {
        var state = AppState.demo(now: day)
        try state.invite(state.profiles[1].id, now: day)
        let invitation = state.invitations[0]
        state.profiles[1].age = 18
        state.currentUserID = state.profiles[1].id
        XCTAssertThrowsError(try state.accept(invitation.id, now: day))
        XCTAssertTrue(state.connections.isEmpty)
    }

    func testSameDayCheckInIsIdempotentAndNeedsBothPeople() throws {
        var state = try connected()
        try state.checkIn(now: day, calendar: calendar)
        try state.checkIn(now: day, calendar: calendar)
        XCTAssertEqual(state.connections[0].totalDays, 0)
        try checkBoth(&state, on: day)
        try checkBoth(&state, on: day)
        XCTAssertEqual(state.connections[0].totalDays, 1)
        XCTAssertEqual(state.connections[0].streak(on: day, calendar: calendar), 1)
    }

    func testGapResetsStreakButPreservesRewards() throws {
        var state = try connected()
        for offset in 0..<7 { try checkBoth(&state, on: later(offset)) }
        XCTAssertEqual(state.connections[0].growth, 3)
        XCTAssertEqual(state.connections[0].streak(on: later(8), calendar: calendar), 0)
        try checkBoth(&state, on: later(9))
        XCTAssertEqual(state.connections[0].streak(on: later(9), calendar: calendar), 1)
        XCTAssertEqual(state.connections[0].totalDays, 8)
        XCTAssertEqual(state.connections[0].bestStreak, 7)
        XCTAssertEqual(state.connections[0].growth, 3)
    }

    func testThirtyTotalDaysUnlocksExpansionWithoutLongStreak() throws {
        var state = try connected()
        for offset in 0..<30 { try checkBoth(&state, on: later(offset * 2)) }
        XCTAssertEqual(state.connections[0].bestStreak, 1)
        XCTAssertEqual(state.connections[0].totalDays, 30)
        XCTAssertEqual(state.connections[0].growth, 5)
    }

    func testPausePreventsCheckIn() throws {
        var state = try connected()
        state.togglePause()
        XCTAssertThrowsError(try state.checkIn(now: day, calendar: calendar))
        state.togglePause()
        try checkBoth(&state, on: day)
        XCTAssertEqual(state.connections[0].totalDays, 1)
    }

    func testLeavingArchivesGardenAndPreventsMessages() throws {
        var state = try connected()
        try checkBoth(&state, on: day)
        state.leave(now: day)
        XCTAssertNil(state.activeConnection(for: state.currentUserID))
        XCTAssertEqual(state.connections[0].growth, 1)
        XCTAssertThrowsError(try state.send("Hello", now: day))
    }

    func testCompanionJournalDoesNotLeakToNewConnection() throws {
        var state = try connected()
        let originalAuthor = state.currentUserID
        let oldPartner = state.profiles[1].id
        let newPartner = state.profiles[2].id
        try state.saveJournal(title: "", body: "For this companion", sharedText: "For this companion", audience: .companion, anonymous: false, commentsEnabled: false, support: .listen, now: day)
        let entry = state.journals.last!
        state.currentUserID = oldPartner
        XCTAssertTrue(state.canRead(entry))
        state.currentUserID = originalAuthor
        state.leave(now: day)
        try state.invite(newPartner, now: day)
        state.currentUserID = newPartner
        try state.accept(state.invitations[0].id, now: day)
        XCTAssertFalse(state.canRead(entry))
        state.currentUserID = oldPartner
        XCTAssertFalse(state.canRead(entry))
    }

    func testBlockingEndsConnectionAndHidesPostsBothWays() throws {
        var state = try connected()
        let first = state.currentUserID
        let second = state.profiles[1].id
        state.block(second, now: day)
        XCTAssertNil(state.activeConnection(for: first))
        XCTAssertFalse(state.feed.contains { $0.authorID == second })
        XCTAssertThrowsError(try state.invite(second, now: day))
        state.currentUserID = second
        XCTAssertFalse(state.canInvite(first))
    }

    func testCommentsRespectDisabledAndPrivateState() throws {
        var state = AppState.demo(now: day)
        try state.saveJournal(title: "", body: "Hello", sharedText: "Hello", audience: .community, anonymous: true, commentsEnabled: false, support: .listen, now: day)
        let id = state.journals.last!.id
        state.currentUserID = state.profiles[1].id
        XCTAssertThrowsError(try state.comment(on: id, text: "Hi", now: day))
        XCTAssertThrowsError(try state.comment(on: state.journals[0].id, text: "Hi", now: day))
    }

    func testPersistenceRoundTripPreservesConnectionAndJournal() throws {
        var state = try connected()
        try checkBoth(&state, on: day)
        try state.send("Still here", now: day)
        let data = try JSONEncoder().encode(state)
        let loaded = try JSONDecoder().decode(AppState.self, from: data)
        XCTAssertEqual(loaded.currentUserID, state.currentUserID)
        XCTAssertEqual(loaded.connections[0].totalDays, 1)
        XCTAssertEqual(loaded.messages[0].text, "Still here")
        XCTAssertEqual(loaded.journals[0].body, state.journals[0].body)
    }
    func testBackendWireContractDecodesToNativeModels() throws {
        let url = try XCTUnwrap(Bundle(for: DearlyCoreTests.self).url(forResource: "server-state", withExtension: "json"))
        let envelope = try JSONDecoder().decode(StateEnvelope.self, from: Data(contentsOf: url))
        let state = envelope.state
        XCTAssertNil(state.currentUserRole) // Legacy server: no inferred staff access.
        XCTAssertNil(state.permissions)
        XCTAssertNotNil(state.profile(state.currentUserID))
        let journal = try XCTUnwrap(state.feed.first)
        XCTAssertEqual(journal.sharedText, "Public fixture.")
        XCTAssertEqual(journal.body, "")
        XCTAssertEqual(journal.title, "")
        XCTAssertEqual(journal.authorID, journal.id)
        XCTAssertEqual(state.connections.first?.totalDays, 1)
        XCTAssertEqual(state.connections.first?.serverCurrentStreak, 1)
        XCTAssertEqual(state.messages.first?.text, "Hello fixture")
        XCTAssertEqual(envelope.serverNow.timeIntervalSince1970, 1791892800, accuracy: 1)
    }

    func testStaffAPIResponsesDecodeWithoutPrivateContent() throws {
        struct Fixture: Decodable {
            var envelope: StateEnvelope
            var reports: StaffPage<StaffReport>
            var users: StaffPage<StaffUser>
            var audit: AuditPage
        }
        let url = try XCTUnwrap(Bundle(for: DearlyCoreTests.self).url(forResource: "staff-responses", withExtension: "json"))
        let fixture = try JSONDecoder().decode(Fixture.self, from: Data(contentsOf: url))
        XCTAssertEqual(fixture.envelope.state.currentUserRole, "admin")
        XCTAssertTrue(fixture.envelope.state.permissions?.contains("roles.manage") == true)
        let report = try XCTUnwrap(fixture.reports.items.first)
        XCTAssertEqual(report.status, "reviewed")
        XCTAssertEqual(report.reviewerID, "server-cli")
        XCTAssertEqual(report.evidence, "Published fixture.")
        XCTAssertEqual(report.reviewedAt?.timeIntervalSince1970, 1791892800)
        XCTAssertTrue(report.canHide)
        XCTAssertNil(report.canRestore) // Compatible with a v0.3 server response.
        XCTAssertTrue(fixture.users.items.contains { $0.role == .admin })
        XCTAssertTrue(fixture.audit.items.contains { $0.action == "user.role" && $0.detail.to == "admin" })
        XCTAssertTrue(fixture.envelope.state.journals.allSatisfy { $0.body.isEmpty })
    }

    @MainActor
    func testAnonymousPostsCannotInviteEvenWhenLegacyServerSaysTheyCan() {
        let store = DearlyStore()
        var entry = AppState.demo(now: day).journals.last!
        entry.anonymous = true
        entry.canInviteAuthor = true
        XCTAssertFalse(store.canInvitePost(entry))
    }

    func testAccountBlocksDoNotRevealAnonymousStories() {
        var state = AppState.demo(now: day)
        let anonymous = state.journals.first { $0.anonymous }!
        state.block(anonymous.authorID, now: day)
        XCTAssertTrue(state.canRead(anonymous))
        XCTAssertTrue(state.feed.contains { $0.id == anonymous.id })
    }

    func testArchivedConnectionsDecodeWithTheirProfilesAndRewards() throws {
        let url = try XCTUnwrap(Bundle(for: DearlyCoreTests.self).url(forResource: "server-state", withExtension: "json"))
        let root = try XCTUnwrap(JSONSerialization.jsonObject(with: Data(contentsOf: url)) as? [String: Any])
        let state = try XCTUnwrap(root["state"] as? [String: Any])
        let data = try JSONSerialization.data(withJSONObject: ["items": state["connections"]!, "profiles": state["profiles"]!, "nextCursor": NSNull()])
        let page = try JSONDecoder().decode(ConnectionPage.self, from: data)
        XCTAssertEqual(page.items.first?.totalDays, 1)
        XCTAssertFalse(page.profiles.isEmpty)
        XCTAssertNil(page.nextCursor)
    }

}
