import SwiftUI

@MainActor
struct CommunityView: View {
    @AppStorage("dearly.language") private var language = "en"
    @EnvironmentObject private var store: DearlyStore
    @State private var filter: SupportStyle?
    @State private var selected: Journal?
    private var entries: [Journal] { store.state.feed.filter { filter == nil || $0.support == filter } }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                PageHeading(eyebrow: L("STORIES SHARED HERE"), title: L("Stay and listen."), subtitle: L("Sometimes, someone being there is enough."))
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 8) {
                        filterButton(L("All"), value: nil)
                        ForEach(SupportStyle.allCases) { filterButton($0.title, value: $0) }
                    }
                }
                HStack(spacing: 10) {
                    Image(systemName: "heart.text.square")
                    Text(L("A gentle word. No judgment, no rush to give advice.")).font(.caption).lineSpacing(3)
                }.foregroundStyle(DearlyTheme.muted)
                ForEach(entries) { entry in
                    CommunityCard(entry: entry) { selected = entry }
                }
                if entries.isEmpty { EmptyCard(icon: "bubble.left", title: L("A quiet moment"), detail: L("No stories yet. Pages shared with the community will appear here.")) }
                Text(L("Latest stories · Pull to refresh"))
                    .font(.caption2).foregroundStyle(DearlyTheme.muted).frame(maxWidth: .infinity)
            }.padding(22).padding(.bottom, 20)
        }.refreshable { await store.refresh(force: true) }.sheet(item: $selected) { CommunityDetail(journalID: $0.id) }
    }
    private func filterButton(_ label: String, value: SupportStyle?) -> some View {
        Button { filter = value } label: {
            Text(label).font(.caption.weight(.medium)).padding(.horizontal, 15).padding(.vertical, 11)
                .foregroundStyle(filter == value ? DearlyTheme.onAccent : DearlyTheme.forest)
                .background(filter == value ? DearlyTheme.forest : DearlyTheme.surface, in: Capsule())
        }.buttonStyle(.plain)
    }
}

@MainActor
struct CommunityCard: View {
    @AppStorage("dearly.language") private var language = "en"
    @EnvironmentObject private var store: DearlyStore
    var entry: Journal
    var open: () -> Void
    var body: some View {
        VStack(alignment: .leading, spacing: 17) {
            HStack(spacing: 11) {
                Avatar(symbol: entry.anonymous ? "sparkles" : store.state.profile(entry.authorID)?.symbol ?? "leaf")
                VStack(alignment: .leading, spacing: 4) {
                    Text(entry.anonymous ? L("A friend") : store.state.profile(entry.authorID)?.nickname ?? L("Friend"))
                        .font(.subheadline.weight(.semibold)).foregroundStyle(DearlyTheme.ink)
                    Text(entry.anonymous ? L("Shared anonymously") : entry.date.formatted(Date.FormatStyle(date: .abbreviated, time: .omitted).locale(Locale(identifier: language))))
                        .font(.caption2).foregroundStyle(DearlyTheme.muted)
                }
                Spacer()
                Image(systemName: "quote.opening").font(.title2).foregroundStyle(DearlyTheme.border)
            }
            Button(action: open) {
                Text(entry.sharedText).font(.system(size: 17, design: .serif)).lineSpacing(6)
                    .foregroundStyle(DearlyTheme.ink).frame(maxWidth: .infinity, alignment: .leading)
            }.buttonStyle(.plain)
            Tag(text: entry.support.title, icon: "ear")
            Rectangle().fill(DearlyTheme.border).frame(height: 1)
            HStack {
                Button {
                    Task { await store.toggleListening(entry) }
                } label: {
                    Label(entry.listeners.contains(store.me.id) ? L("Listening") : L("I’m listening"), systemImage: entry.listeners.contains(store.me.id) ? "heart.fill" : "heart")
                        .font(.caption.weight(.medium))
                }.disabled(entry.authorID == store.me.id)
                Spacer()
                Button(action: open) { Image(systemName: "bubble.left").frame(width: 44, height: 32) }
                    .accessibilityLabel(L("Open story and responses"))
            }
        }.padding(21).dearlyCard()
    }
}

@MainActor
struct CommunityDetail: View {
    @AppStorage("dearly.language") private var language = "en"
    @EnvironmentObject private var store: DearlyStore
    @Environment(\.dismiss) private var dismiss
    var journalID: UUID
    @State private var response = ""
    @State private var reportPresented = false
    @State private var blockConfirmation = false
    private var entry: Journal? { store.state.feed.first { $0.id == journalID } }
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 22) {
                    if let entry {
                        CommunityCard(entry: entry, open: {})
                        if entry.authorID != store.me.id {
                            if store.canInvitePost(entry) {
                                PrimaryButton(title: L("Invite them to connect"), icon: "person.badge.plus") {
                                    Task { if await store.invite(entry.authorID, journalID: entry.id) { dismiss() } }
                                }
                                Text(L("Chat opens only when you both agree. The person you invite will see your nickname."))
                                    .font(.caption).foregroundStyle(DearlyTheme.muted)
                            } else if entry.anonymous {
                                Text(L("Anonymous stories do not link to profiles. You can hide this story or report it."))
                                    .font(.caption).foregroundStyle(DearlyTheme.muted)
                            } else {
                                Text(L("Invitations are available when neither person has a connection and both are in compatible age groups."))
                                    .font(.caption).foregroundStyle(DearlyTheme.muted)
                            }
                            HStack {
                                Button(L("Report"), systemImage: "flag") { reportPresented = true }
                                Spacer()
                                Button(entry.anonymous ? L("Hide this story") : L("Block"), systemImage: "hand.raised", role: .destructive) { blockConfirmation = true }
                            }.font(.caption)
                        }
                        SectionLabel(title: L("Responses"), detail: entry.commentsEnabled ? L("Keep it gentle") : L("Turned off"))
                        ForEach(store.state.comments.filter { $0.journalID == journalID && !store.state.isBlocked(store.me.id, $0.authorID) }) { comment in
                            VStack(alignment: .leading, spacing: 8) {
                                Text(entry.anonymous && comment.authorID == entry.authorID ? L("Anonymous author") : store.state.profile(comment.authorID)?.nickname ?? L("Friend"))
                                    .font(.caption.weight(.semibold))
                                Text(comment.text).font(.subheadline).lineSpacing(3)
                            }.frame(maxWidth: .infinity, alignment: .leading).padding(16).dearlyCard()
                        }
                        if entry.commentsEnabled {
                            TextField(L("A response that meets the writer’s needs…"), text: $response, axis: .vertical)
                                .lineLimit(2...5).padding(16).dearlyCard()
                            PrimaryButton(title: L("Send response"), icon: "arrow.up") {
                                Task { if await store.comment(on: journalID, text: response) { response = "" } }
                            }.disabled(response.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                        }
                    } else {
                        EmptyCard(icon: "lock", title: L("This story is no longer available"), detail: L("The writer may have made it private or deleted it."))
                    }
                }.padding(22)
            }.background(DearlyTheme.cream)
                .navigationTitle(L("A story")).navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .confirmationAction) { Button(L("Done")) { dismiss() } } }
                .sheet(isPresented: $reportPresented) { if let entry { ReportView(userID: entry.authorID, journalID: entry.id) } }
                .confirmationDialog(entry?.anonymous == true
                    ? L("Hide this story only? Profiles and other stories are unaffected.")
                    : L("Block this person? You won’t see their posts or receive invitations from them."), isPresented: $blockConfirmation, titleVisibility: .visible) {
                    Button(entry?.anonymous == true ? L("Hide this story") : L("Block"), role: .destructive) {
                        Task {
                            guard let entry else { return }
                            let success: Bool
                            if entry.anonymous { success = await store.hidePost(entry.id) }
                            else { success = await store.block(entry.authorID, journalID: entry.id) }
                            if success { dismiss() }
                        }
                    }
                }
        }
    }
}

@MainActor
struct ReportView: View {
    @AppStorage("dearly.language") private var language = "en"
    @EnvironmentObject private var store: DearlyStore
    @Environment(\.dismiss) private var dismiss
    var userID: UUID
    var journalID: UUID? = nil
    @State private var reason = "Harassment or threats"
    private let reasons = ["Harassment or threats", "Unwanted sexual content", "Pressure to share photos or personal information", "Other"]
    var body: some View {
        NavigationStack {
            Form {
                Section(L("Reason")) { Picker(L("Choose a reason"), selection: $reason) { ForEach(reasons, id: \.self) { Text(L($0)) } }.pickerStyle(.inline).labelsHidden() }
                Section { Text(L("Your report is sent to the server for an administrator to review. You can block or leave the connection now.")) }
                Button(L("Send report")) {
                    Task { if await store.report(userID, journalID: journalID, reason: reason) { dismiss() } }
                }.disabled(store.isBusy)
                if let error = store.errorMessage { Text(error).foregroundStyle(.red) }
            }.navigationTitle(L("Report")).navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .cancellationAction) { Button(L("Cancel")) { dismiss() } } }
        }
    }
}
