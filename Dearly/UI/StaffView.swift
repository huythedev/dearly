import SwiftUI

@MainActor
struct StaffConsoleView: View {
    @AppStorage("dearly.language") private var language = "en"
    @EnvironmentObject private var store: DearlyStore
    @State private var section = "reports"
    @State private var status: ReportStatus = .open
    @State private var query = ""
    @State private var reports: [StaffReport] = []
    @State private var users: [StaffUser] = []
    @State private var audit: [AuditEntry] = []
    @State private var nextID: UUID?
    @State private var nextAuditID: Int?
    @State private var loading = false
    @State private var failure: String?
    @State private var requestID = UUID()

    var body: some View {
        Group {
            if store.hasPermission("reports.read") {
                List {
                    Section {
                        Text(store.role.title).font(.headline).foregroundStyle(DearlyTheme.forest)
                        Picker(L("Section"), selection: $section) {
                            Text(L("Reports")).tag("reports")
                            if store.hasPermission("users.read") { Text(L("Accounts")).tag("users") }
                            if store.hasPermission("audit.read") { Text(L("Audit log")).tag("audit") }
                        }.pickerStyle(.segmented)
                    }
                    if section == "reports" {
                        Section {
                            Picker(L("Status"), selection: $status) {
                                ForEach(ReportStatus.allCases, id: \.self) { Text($0.title).tag($0) }
                            }
                        }
                        Section(L("Reports")) {
                            ForEach(reports) { report in
                                NavigationLink {
                                    StaffReportView(report: report)
                                } label: {
                                    VStack(alignment: .leading, spacing: 6) {
                                        Text(report.reportedNickname).font(.headline)
                                        Text(report.reason).font(.subheadline).lineLimit(2)
                                        Text(report.date, style: .date).font(.caption).foregroundStyle(DearlyTheme.muted)
                                    }
                                }
                            }
                            if reports.isEmpty && !loading { Text(L("No reports.")) }
                        }
                    } else if section == "users" && store.hasPermission("users.read") {
                        Section {
                            TextField(L("Search name or username"), text: $query)
                                .textInputAutocapitalization(.never).autocorrectionDisabled().submitLabel(.search)
                                .onSubmit { Task { await load() } }
                            Button(L("Search")) { Task { await load() } }.disabled(loading)
                        }
                        Section(L("Accounts")) {
                            ForEach(users) { user in
                                NavigationLink {
                                    StaffUserView(user: user)
                                } label: {
                                    VStack(alignment: .leading, spacing: 5) {
                                        Text(user.nickname).font(.headline)
                                        Text("@\(user.username) · \(user.role.title)").font(.caption)
                                        if user.suspended { Label(L("Suspended"), systemImage: "lock.fill").font(.caption).foregroundStyle(.red) }
                                    }
                                }
                            }
                            if users.isEmpty && !loading { Text(L("No matching accounts.")) }
                        }
                    } else if section == "audit" && store.hasPermission("audit.read") {
                        Section(L("Administration log")) {
                            ForEach(audit) { entry in
                                VStack(alignment: .leading, spacing: 7) {
                                    Text(entry.title).font(.headline)
                                    Text(entry.actorName).font(.subheadline)
                                    Text(entry.detail.reason ?? entry.detail.note ?? "").font(.subheadline)
                                    if let role = entry.detail.to.flatMap(AccountRole.init(rawValue:)) {
                                        Text(role.title).font(.caption)
                                    }
                                    if let value = entry.detail.status.flatMap(ReportStatus.init(rawValue:)) {
                                        Text(value.title).font(.caption)
                                    }
                                    Text(LF("Target: %1$@", String(describing: entry.targetID)))
                                        .font(.caption2).textSelection(.enabled)
                                    Text(entry.date, format: .dateTime).font(.caption).foregroundStyle(DearlyTheme.muted)
                                }
                            }
                            if audit.isEmpty && !loading { Text(L("No actions yet.")) }
                        }
                    }
                    Section {
                        if loading { ProgressView() }
                        if let failure { Text(failure).font(.footnote).foregroundStyle(.red) }
                        if nextID != nil || nextAuditID != nil {
                            Button(L("Next page")) { Task { await load(next: true) } }.disabled(loading)
                        }
                        Button(L("First page / Refresh")) { Task { await load() } }.disabled(loading)
                    }
                }.scrollContentBackground(.hidden).background(DearlyTheme.cream)
            } else {
                ContentUnavailableView(L("Access denied"), systemImage: "lock.shield")
            }
        }
        .navigationTitle(L("Dearly management")).navigationBarTitleDisplayMode(.inline)
        .onAppear { Task { await load() } }
        .onDisappear { requestID = UUID() }
        .onChange(of: section) { _, _ in Task { await load() } }
        .onChange(of: status) { _, _ in Task { await load() } }
        .onChange(of: query) { _, _ in
            // A cursor belongs to the search that produced it.
            requestID = UUID(); users = []; nextID = nil; loading = false; failure = nil
        }
        .onChange(of: store.state.permissions) { _, _ in
            reports = []; users = []; audit = []; section = "reports"
            Task { await load() }
        }
        .refreshable { await load() }
    }

    private func load(next: Bool = false) async {
        let expected = UUID(); requestID = expected
        let before = next ? nextID : nil
        let auditBefore = next ? nextAuditID : nil
        loading = true; failure = nil
        reports = []; users = []; audit = []; nextID = nil; nextAuditID = nil
        defer { if requestID == expected { loading = false } }
        guard store.hasPermission("reports.read") else { return }
        do {
            switch section {
            case "users":
                let page = try await store.staffUsers(query: query, before: before)
                guard requestID == expected else { return }
                users = page.items; nextID = page.nextCursor
            case "audit":
                let page = try await store.staffAudit(before: auditBefore)
                guard requestID == expected else { return }
                audit = page.items; nextAuditID = page.nextCursor
            default:
                let page = try await store.staffReports(status: status.rawValue, before: before)
                guard requestID == expected else { return }
                reports = page.items; nextID = page.nextCursor
            }
        } catch {
            if requestID == expected { failure = error.localizedDescription }
        }
    }
}

@MainActor
private struct StaffReportView: View {
    @AppStorage("dearly.language") private var language = "en"
    @EnvironmentObject private var store: DearlyStore
    @Environment(\.dismiss) private var dismiss
    let report: StaffReport
    @State private var reason = ""
    @State private var confirmHide = false
    @State private var confirmRestore = false

    var body: some View {
        Group {
            if store.hasPermission("reports.read") {
                Form {
                    Section(L("Report")) {
                        LabeledContent(L("Reporter"), value: report.reporterNickname)
                        LabeledContent(L("Reported account"), value: report.reportedNickname)
                        LabeledContent(L("Status"), value: ReportStatus(rawValue: report.status)?.title ?? report.status)
                        Text(report.reason).textSelection(.enabled)
                        Text(report.date, format: .dateTime).font(.caption)
                    }
                    if !report.evidence.isEmpty {
                        Section(L("Reported public excerpt")) { Text(report.evidence).textSelection(.enabled) }
                    }
                    if !report.reviewNote.isEmpty {
                        Section(L("Previous review note")) { Text(report.reviewNote) }
                    }
                    if store.hasPermission("reports.review") {
                        Section(L("Review")) {
                            TextField(L("Required reason / review note"), text: $reason, axis: .vertical).lineLimit(3...6)
                            ForEach(ReportStatus.allCases, id: \.self) { status in
                                Button(status.title) { Task { await review(status) } }.disabled(!canSubmit)
                            }
                            if report.canHide && store.hasPermission("reports.hide") {
                                Button(L("Hide community post"), role: .destructive) { confirmHide = true }.disabled(!canSubmit)
                            }
                            if report.canRestore == true && store.hasPermission("reports.hide") {
                                Button(L("Allow the author to share again")) { confirmRestore = true }.disabled(!canSubmit)
                            }
                        }
                    }
                    if let error = store.errorMessage { Text(error).foregroundStyle(.red) }
                }
            } else { ContentUnavailableView(L("Access denied"), systemImage: "lock.shield") }
        }
        .navigationTitle(L("Report details"))
        .confirmationDialog(L("Hide this community post?"), isPresented: $confirmHide, titleVisibility: .visible) {
            Button(L("Hide post"), role: .destructive) {
                Task {
                    if await store.staffCommand("staff.report.hide", payload: CommandPayload(id: report.id, reason: reason)) { dismiss() }
                }
            }
        } message: { Text(L("The post becomes private and sharing stays restricted until staff restore it. The author's journal is preserved.")) }
        .confirmationDialog(L("Allow sharing again?"), isPresented: $confirmRestore, titleVisibility: .visible) {
            Button(L("Allow")) {
                Task {
                    if await store.staffCommand("staff.report.restore", payload: CommandPayload(id: report.id, reason: reason)) { dismiss() }
                }
            }
        } message: { Text(L("The entry stays private. Its author can choose whether to share it again.")) }
    }
    private var canSubmit: Bool { !store.isBusy && (1...1000).contains(reason.trimmingCharacters(in: .whitespacesAndNewlines).count) }
    private func review(_ status: ReportStatus) async {
        if await store.staffCommand("staff.report.review", payload: CommandPayload(id: report.id, reason: reason, status: status.rawValue)) { dismiss() }
    }
}

@MainActor
private struct StaffUserView: View {
    @AppStorage("dearly.language") private var language = "en"
    @EnvironmentObject private var store: DearlyStore
    @Environment(\.dismiss) private var dismiss
    let user: StaffUser
    @State private var reason = ""
    @State private var birthDate = ""
    @State private var role: AccountRole = .user
    @State private var pending: String?

    var body: some View {
        Group {
            if store.hasPermission("users.read") {
                Form {
                    Section {
                        LabeledContent(L("Nickname"), value: user.nickname)
                        LabeledContent("Username", value: user.username)
                        LabeledContent(L("Role"), value: user.role.title)
                        LabeledContent(L("Status"), value: user.suspended ? L("Suspended") : L("Active"))
                        LabeledContent(L("Age"), value: user.ageVerified ? L("Verified") : L("Unverified"))
                    }
                    if user.role == .admin || user.id == store.state.currentUserID {
                        Text(L("Admin accounts are managed with commands on the backend server."))
                    } else {
                        Section {
                            TextField(L("Required reason"), text: $reason, axis: .vertical).lineLimit(2...5)
                        }
                        if store.hasPermission("roles.manage") {
                            Section(L("Role")) {
                                Picker(L("Role"), selection: $role) {
                                    Text(AccountRole.user.title).tag(AccountRole.user)
                                    Text(AccountRole.moderator.title).tag(AccountRole.moderator)
                                }
                                Button(L("Save role")) { pending = "role" }.disabled(!canSubmit || role == user.role)
                            }
                        }
                        if store.hasPermission("users.verify_age") {
                            Section(L("Age verification")) {
                                TextField("YYYY-MM-DD", text: $birthDate).keyboardType(.numbersAndPunctuation)
                                Text(L("Confirm only after reviewing age outside the app. Correcting the date ends current connections.")).font(.caption)
                                Button(L("Confirm reviewed age")) { pending = "age" }.disabled(!canSubmit || birthDate.count != 10)
                            }
                        }
                        if store.hasPermission("users.suspend") {
                            Section {
                                Button(user.suspended ? L("Restore account") : L("Suspend account"), role: user.suspended ? nil : .destructive) { pending = "suspend" }.disabled(!canSubmit)
                                Text(L("Suspension revokes sessions and ends connections. Restored accounts need a new login; archived gardens remain.")).font(.caption)
                            }
                        }
                    }
                    if let error = store.errorMessage { Text(error).foregroundStyle(.red) }
                }
            } else { ContentUnavailableView(L("Access denied"), systemImage: "lock.shield") }
        }
        .navigationTitle(L("Manage account"))
        .onAppear { birthDate = user.birthDate; role = user.role }
        .confirmationDialog(L("Confirm change"), isPresented: Binding(get: { pending != nil }, set: { if !$0 { pending = nil } }), titleVisibility: .visible) {
            let operation = pending ?? ""
            Button(L("Confirm"), role: operation == "suspend" && !user.suspended ? .destructive : nil) {
                Task { await apply(operation) }
            }
        } message: { Text(confirmationText) }
    }
    private var canSubmit: Bool { !store.isBusy && (1...1000).contains(reason.trimmingCharacters(in: .whitespacesAndNewlines).count) }
    private var confirmationText: String {
        switch pending {
        case "role": return LF("Change @%1$@ to %2$@?", String(describing: user.username), String(describing: role.title))
        case "age": return LF("Confirm reviewed birth date: %1$@?", String(describing: birthDate))
        default: return user.suspended ? LF("Restore @%1$@?", String(describing: user.username)) : LF("Suspend @%1$@ and end their connection?", String(describing: user.username))
        }
    }
    private func apply(_ operation: String) async {
        let kind: String
        var payload = CommandPayload(userID: user.id, reason: reason)
        switch operation {
        case "role": kind = "staff.user.role"; payload.role = role.rawValue
        case "age": kind = "staff.user.verify_age"; payload.birthDate = birthDate
        case "suspend": kind = "staff.user.suspend"; payload.suspended = !user.suspended
        default: return
        }
        if await store.staffCommand(kind, payload: payload) { dismiss() }
    }
}
