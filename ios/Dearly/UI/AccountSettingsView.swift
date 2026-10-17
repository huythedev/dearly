import SwiftUI

@MainActor
struct AccountSettingsView: View {
    var onStartGuide: () -> Void
    @AppStorage("dearly.language") private var language = "en"
    @EnvironmentObject private var store: DearlyStore
    @Environment(\.dismiss) private var dismiss
    @State private var editingProfile = false
    var body: some View {
        NavigationStack {
            Form {
                Section(L("Language")) {
                    LanguagePicker()
                }
                Section(L("Appearance")) {
                    AppearancePicker()
                }
                Section(L("A little help getting started")) {
                    Button(L("Take a guided tour"), systemImage: "book.closed") { onStartGuide() }
                    Text(L("Revisit the main features with a step-by-step guide."))
                        .font(.caption).foregroundStyle(DearlyTheme.muted)
                }
                if store.isOnline {
                    Section {
                        NavigationLink { PrivacySettingsView(vault: store.encryption) } label: {
                            Label(L("Privacy & data"), systemImage: "lock.shield")
                        }
                    }
                    Section(L("Your account")) {
                        LabeledContent(L("Nickname"), value: store.me.nickname)
                        LabeledContent(L("Role"), value: store.role.title)
                        LabeledContent(L("Server"), value: store.serverAddress)
                        LabeledContent(L("Age"), value: store.me.ageVerified ? L("Verified") : L("Awaiting age verification"))
                        if let date = store.lastSync { LabeledContent(L("Last synced"), value: date.formatted(Date.FormatStyle(date: .omitted, time: .shortened).locale(Locale(identifier: AppLanguage.code)))) }
                        if let error = store.syncError { Text(error).font(.caption).foregroundStyle(.red) }
                        Button(L("Edit profile"), systemImage: "person.crop.circle") { editingProfile = true }
                        Button(L("Sync now"), systemImage: "arrow.clockwise") { Task { await store.refresh(force: true) } }
                        Button(L("Log out"), role: .destructive) { Task { await store.logout() } }.disabled(store.isBusy)
                    }
                    if store.hasPermission("reports.read") {
                        Section(L("Management")) {
                            NavigationLink {
                                StaffConsoleView()
                            } label: {
                                Label(L("Dearly management"), systemImage: "checkmark.shield")
                            }
                        }
                    }
                    Section {
                        Text(L("Chat updates live while the app is open. If the connection drops, automatic sync keeps your messages up to date. Daily check-ins use UTC. Your data is saved on the server.")).font(.caption)
                    }
                }
            }.navigationTitle(L("Dearly settings")).navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .confirmationAction) { Button(L("Done")) { dismiss() } } }
                .sheet(isPresented: $editingProfile) { ProfileEditorView() }
        }
    }
}


@MainActor
struct ProfileEditorView: View {
    @AppStorage("dearly.language") private var language = "en"
    @EnvironmentObject private var store: DearlyStore
    @Environment(\.dismiss) private var dismiss
    @State private var nickname = ""
    @State private var bio = ""
    @State private var interests = ""
    @State private var support: SupportStyle = .listen
    @State private var pace = "Evenings"
    var body: some View {
        NavigationStack {
            Form {
                TextField(L("Nickname"), text: $nickname)
                TextField(L("A little about you"), text: $bio, axis: .vertical).lineLimit(2...5)
                TextField(L("Interests, separated by commas"), text: $interests)
                Picker(L("What I need"), selection: $support) { ForEach(SupportStyle.allCases) { Text($0.title).tag($0) } }
                TextField(L("Conversation pace"), text: $pace)
                if let error = store.errorMessage { Text(error).foregroundStyle(.red) }
            }.navigationTitle(L("Your profile")).navigationBarTitleDisplayMode(.inline)
                .toolbar {
                    ToolbarItem(placement: .cancellationAction) { Button(L("Cancel")) { dismiss() } }
                    ToolbarItem(placement: .confirmationAction) {
                        Button(L("Save")) {
                            Task {
                                let values = interests.split(separator: ",").map { $0.trimmingCharacters(in: .whitespacesAndNewlines) }.filter { !$0.isEmpty }
                                if await store.updateProfile(nickname: nickname, bio: bio, interests: values, support: support, pace: pace) { dismiss() }
                            }
                        }.disabled(store.isBusy)
                    }
                }
                .onAppear {
                    nickname = store.me.nickname; bio = store.me.bio; interests = store.me.interests.joined(separator: ", ")
                    support = store.me.support; pace = store.me.pace
                }
        }
    }
}
