import SwiftUI

@MainActor
struct JournalView: View {
    @AppStorage("dearly.language") private var language = "en"
    @EnvironmentObject private var store: DearlyStore
    @State private var composing = false
    @State private var editing: Journal?
    @State private var showingArchive = false
    var body: some View {
        GuideScrollView {
            VStack(alignment: .leading, spacing: 26) {
                PageHeading(eyebrow: L("A LITTLE SPACE OF YOUR OWN"), title: L("How are you today?"), subtitle: L("You don’t need the perfect words. Just be you."))
                VStack(alignment: .leading, spacing: 18) {
                    HStack { Tag(text: L("TODAY’S PROMPT"), icon: "sparkle", color: DearlyTheme.surface.opacity(0.55)); Spacer(); Image(systemName: "sun.max").font(.title2) }
                    Text(L("Is there something you want to say,\nbut haven’t found the words for?"))
                        .font(.system(size: 25, design: .serif)).lineSpacing(5)
                    Button { composing = true } label: {
                        HStack { Text(L("Leave a few words here")).fontWeight(.medium); Spacer(); Image(systemName: "arrow.up.right") }
                            .font(.subheadline).padding(.top, 8)
                    }.guideTarget(.compose).accessibilityIdentifier("journal.compose")
                }.padding(23).foregroundStyle(DearlyTheme.forest)
                    .background(DearlyTheme.sage, in: RoundedRectangle(cornerRadius: 25))
                HStack(spacing: 8) {
                    Image(systemName: "lock").font(.caption)
                    Text(L("Only you can read it, until you choose to share.")).font(.caption)
                }.foregroundStyle(DearlyTheme.muted)
                SectionLabel(title: L("Your pages"), detail: LF("%1$@ pages", String(describing: store.state.myJournals.count)))
                if store.isOnline {
                    Button(L("Browse all your pages"), systemImage: "books.vertical") { showingArchive = true }
                        .font(.subheadline).guideTarget(.pages)
                }
                if store.state.myJournals.isEmpty {
                    EmptyCard(icon: "book", title: L("Your first page is waiting"), detail: L("Even one sentence is a beginning."))
                }
                ForEach(store.state.myJournals) { entry in
                    Button { editing = entry } label: { JournalRow(entry: entry) }.buttonStyle(.plain).disabled(entry.locked == true)
                }
                Button { composing = true } label: {
                    Label(L("Write a new page"), systemImage: "plus").font(.subheadline.weight(.semibold)).frame(maxWidth: .infinity).padding(16)
                }.dearlyCard()
            }.padding(22).padding(.bottom, 20)
        }
        .sheet(isPresented: $composing) { JournalEditor() }
        .sheet(item: $editing) { JournalEditor(entry: $0) }
        .sheet(isPresented: $showingArchive) { JournalArchiveView() }
    }
}

@MainActor
struct JournalArchiveView: View {
    @AppStorage("dearly.language") private var language = "en"
    @EnvironmentObject private var store: DearlyStore
    @Environment(\.dismiss) private var dismiss
    @State private var page: JournalPage?
    @State private var cursors: [UUID?] = [nil]
    @State private var requestID = UUID()
    @State private var loading = false
    @State private var error: String?
    @State private var editing: Journal?
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 18) {
                    Text(LF("Page %1$@ · Up to 40 entries per page", String(describing: cursors.count))).font(.caption).foregroundStyle(DearlyTheme.muted)
                    if let error { Text(error).foregroundStyle(.red) }
                    if loading { ProgressView() }
                    ForEach(page?.items ?? []) { entry in
                        Button { editing = entry } label: { JournalRow(entry: entry) }.buttonStyle(.plain).disabled(entry.locked == true)
                    }
                    HStack {
                        if cursors.count > 1 {
                            Button(L("Previous page")) { cursors.removeLast(); Task { await load() } }.disabled(loading)
                        }
                        Spacer()
                        if let next = page?.nextCursor {
                            Button(L("Next page")) { cursors.append(next); Task { await load() } }.disabled(loading)
                        }
                    }
                }.padding(22)
            }.background(DearlyTheme.cream)
                .navigationTitle(L("Your pages")).navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .confirmationAction) { Button(L("Done")) { dismiss() } } }
                .sheet(item: $editing, onDismiss: { Task { await load() } }) { JournalEditor(entry: $0) }
                .task { await load() }
                .onChange(of: store.state.currentUserID) { _, _ in requestID = UUID(); page = nil; editing = nil; dismiss() }
                .onDisappear { requestID = UUID(); page = nil }
        }
    }
    private func load() async {
        let expected = UUID()
        requestID = expected; loading = true; page = nil; error = nil
        defer { if requestID == expected { loading = false } }
        do {
            let result = try await store.journalPage(before: cursors.last ?? nil)
            guard requestID == expected, !Task.isCancelled else { return }
            page = result
        } catch {
            guard requestID == expected, !Task.isCancelled, !(error is CancellationError) else { return }
            self.error = error.localizedDescription
        }
    }
}

@MainActor
struct JournalRow: View {
    @AppStorage("dearly.language") private var language = "en"
    var entry: Journal
    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Text(entry.date.formatted(.dateTime.day().month(.wide).locale(Locale(identifier: AppLanguage.code)))).font(.caption).foregroundStyle(DearlyTheme.muted)
                Spacer()
                Image(systemName: entry.audience.icon).foregroundStyle(DearlyTheme.forest)
            }
            Text(entry.title.isEmpty ? L("A page of my own") : entry.title)
                .font(.system(size: 21, design: .serif)).foregroundStyle(DearlyTheme.ink)
            Text(entry.body).font(.subheadline).foregroundStyle(DearlyTheme.muted).lineSpacing(4).lineLimit(3)
            Tag(text: L(entry.audience.title), icon: entry.audience.icon)
        }.padding(21).frame(maxWidth: .infinity, alignment: .leading).dearlyCard()
    }
}

@MainActor
struct JournalEditor: View {
    @AppStorage("dearly.language") private var language = "en"
    @EnvironmentObject private var store: DearlyStore
    @Environment(\.dismiss) private var dismiss
    var entry: Journal?
    @State private var title = ""
    @State private var bodyText = ""
    @State private var excerpt = ""
    @State private var useExcerpt = false
    @State private var audience: Audience = .privateOnly
    @State private var support: SupportStyle = .listen
    @State private var anonymous = false
    @State private var commentsEnabled = true
    @State private var confirmDelete = false
    @State private var validation: String?
    private var sharingRestricted: Bool {
        guard let entry else { return false }
        return (store.state.journals.first { $0.id == entry.id } ?? entry).moderationHidden == true
    }

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField(L("Give today a title (optional)"), text: $title)
                        .font(.system(.title3, design: .serif))
                    TextEditor(text: $bodyText).frame(minHeight: 220)
                        .accessibilityLabel(L("Journal text")).accessibilityIdentifier("journal.body")
                } header: { Text(L("You can start anywhere")) }
                Section {
                    Picker(L("Who can read this?"), selection: $audience) {
                        ForEach(Audience.allCases) { option in Text(L(option.title)).tag(option) }
                    }.disabled(sharingRestricted)
                    if sharingRestricted {
                        Text(L("Staff have restricted sharing for this entry. You can still edit and save it privately."))
                            .font(.caption).foregroundStyle(.secondary)
                    }
                    if audience != .privateOnly {
                        Toggle(L("Share just a passage"), isOn: $useExcerpt)
                        if useExcerpt {
                            Text(L("Paste the exact passage you want to share. The rest stays private.")).font(.caption)
                            TextEditor(text: $excerpt).frame(minHeight: 100).accessibilityLabel(L("Shared passage"))
                        }
                        Picker(L("What I need"), selection: $support) {
                            ForEach(SupportStyle.allCases) { Text($0.title).tag($0) }
                        }
                    }
                    if audience == .community {
                        Toggle(L("Share anonymously"), isOn: $anonymous)
                        Toggle(L("Allow responses"), isOn: $commentsEnabled)
                    }
                } header: { Text(L("You choose what others see")) } footer: {
                    Text(audience == .privateOnly ? L("Private by default. You can change this later.") : L("Only the selected text is shared. Your journal title always stays private."))
                }
                if audience != .privateOnly {
                    Section(L("Preview what you’re sharing")) {
                        Text(useExcerpt ? excerpt : bodyText).font(.body)
                        Text(anonymous && audience == .community ? L("Shown as: A friend · no profile link") : LF("Shown as: %1$@", String(describing: store.me.nickname)))
                            .font(.caption).foregroundStyle(.secondary)
                    }
                }
                if let validation { Section { Text(validation).foregroundStyle(.red) } }
                if entry != nil {
                    Section { Button(L("Delete this page"), role: .destructive) { confirmDelete = true } }
                }
            }
            .navigationTitle(entry == nil ? L("A new page") : L("Your page")).navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button(L("Cancel")) { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button(L("Save")) { Task { await save() } }.disabled(store.isBusy).fontWeight(.semibold).accessibilityIdentifier("journal.save")
                }
            }
            .confirmationDialog(L("Permanently delete this page and its responses?"), isPresented: $confirmDelete, titleVisibility: .visible) {
                Button(L("Delete page"), role: .destructive) {
                    Task {
                        if let entry, await store.deleteJournal(entry.id) { dismiss() }
                    }
                }
            }
            .onAppear {
                guard let entry else { return }
                title = entry.title; bodyText = entry.body; excerpt = entry.sharedText
                useExcerpt = !entry.sharedText.isEmpty && entry.sharedText != entry.body
                audience = sharingRestricted ? .privateOnly : entry.audience; support = entry.support
                anonymous = entry.anonymous; commentsEnabled = entry.commentsEnabled
            }
            .onChange(of: sharingRestricted) { _, restricted in if restricted { audience = .privateOnly } }
        }
    }

    private func save() async {
        let success = await store.saveJournal(id: entry?.id, title: title, body: bodyText,
            sharedText: useExcerpt ? excerpt : bodyText, audience: audience,
            anonymous: anonymous, commentsEnabled: commentsEnabled, support: support)
        if success { dismiss() } else { validation = store.errorMessage }
    }
}
