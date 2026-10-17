import SwiftUI

@MainActor
struct CompanionView: View {
    @AppStorage("dearly.language") private var language = "en"
    @EnvironmentObject private var store: DearlyStore
    var body: some View {
        GuideScrollView {
            VStack(alignment: .leading, spacing: 24) {
                PageHeading(eyebrow: L("YOU DON’T HAVE TO GO ALONE"), title: L("Someone, alongside you."), subtitle: L("Start with something in common. Connect at a pace that feels right for both of you."))
                    .guideTarget(.companion)
                if let partner = store.partner, let connection = store.connection {
                    VStack(alignment: .leading, spacing: 20) {
                        HStack(spacing: 14) {
                            Avatar(symbol: partner.symbol, size: 62)
                            VStack(alignment: .leading, spacing: 5) {
                                Text(partner.nickname).font(.system(size: 26, design: .serif))
                                Text(LF("%1$@’s companion", String(describing: store.me.nickname))).font(.caption).foregroundStyle(DearlyTheme.muted)
                            }
                            Spacer()
                        }
                        Text(partner.bio).font(.subheadline).lineSpacing(4).foregroundStyle(DearlyTheme.muted)
                        Tag(text: LF("%1$@ days here together", String(describing: connection.totalDays)), icon: "leaf")
                        NavigationLink { ChatView(connectionID: connection.id) } label: {
                            HStack { Text(L("Come say hello")); Spacer(); Image(systemName: "arrow.right") }
                                .font(.subheadline.weight(.semibold)).padding(18).foregroundStyle(DearlyTheme.onAccent)
                                .background(DearlyTheme.forest, in: RoundedRectangle(cornerRadius: 17))
                        }.accessibilityIdentifier("companion.chat")
                    }.padding(23).dearlyCard()
                    Text(L("You don’t always need an answer. Being heard and taking a break both matter."))
                        .font(.system(size: 21, design: .serif)).lineSpacing(5).padding(20)
                    sharedJournals(connection)
                } else {
                    if store.isOnline && !store.me.ageVerified {
                        Label(L("A moderator or administrator must verify your age before you can send or receive invitations."), systemImage: "person.crop.circle.badge.exclamationmark")
                            .font(.subheadline).padding(18).dearlyCard()
                    }
                    invitations
                    SectionLabel(title: L("On a similar wavelength"), detail: L("Based on your interests"))
                    ForEach(store.state.suggestions) { profile in ProfileCard(profile: profile) }
                    if store.state.suggestions.isEmpty {
                        EmptyCard(icon: "person.2", title: L("No matches just yet"), detail: L("Age groups are kept separate. You can keep writing while you wait."))
                    }
                    Text(L("You can say no without explaining. Private journal entries are never used for matching."))
                        .font(.caption).foregroundStyle(DearlyTheme.muted).lineSpacing(4)
                }
            }.padding(22).padding(.bottom, 20)
        }
    }

    private var invitations: some View {
        let incoming = store.state.invitations.filter { $0.recipientID == store.me.id }
        let outgoing = store.state.invitations.filter { $0.senderID == store.me.id }
        return VStack(spacing: 14) {
            ForEach(incoming) { invitation in
                VStack(alignment: .leading, spacing: 14) {
                    Tag(text: L("AN INVITATION"), icon: "envelope", color: DearlyTheme.peach)
                    Text(LF("%1$@ would like to connect with you.", String(describing: store.state.profile(invitation.senderID)?.nickname ?? L("A friend"))))
                        .font(.system(size: 21, design: .serif))
                    if let profile = store.state.profile(invitation.senderID) {
                        Text(LF("Age %1$@ · %2$@\n%3$@", String(describing: profile.age), String(describing: profile.interests.joined(separator: " · ")), String(describing: profile.bio))).font(.subheadline).foregroundStyle(DearlyTheme.muted)
                    }
                    HStack {
                        Button(L("Maybe another time")) { Task { await store.dismissInvitation(invitation.id) } }.font(.subheadline)
                        Spacer()
                        Button(L("Accept connection")) {
                            Task { await store.accept(invitation.id) }
                        }.buttonStyle(.borderedProminent).foregroundStyle(DearlyTheme.onAccent).accessibilityIdentifier("companion.accept")
                    }
                }.padding(20).dearlyCard()
            }
            ForEach(outgoing) { invitation in
                HStack {
                    VStack(alignment: .leading, spacing: 5) {
                        Text(LF("Invited %1$@", String(describing: store.state.profile(invitation.recipientID)?.nickname ?? L("you")))).font(.subheadline.weight(.medium))
                        Text(L("Waiting for them to accept")).font(.caption).foregroundStyle(DearlyTheme.muted)
                    }
                    Spacer()
                    Button(L("Cancel")) { Task { await store.dismissInvitation(invitation.id) } }.font(.caption)
                }.padding(18).dearlyCard()
            }
        }
    }

    private func sharedJournals(_ connection: Connection) -> some View {
        let entries = store.state.journals.filter {
            $0.audience == .companion && $0.connectionID == connection.id && store.state.canRead($0)
        }
        return VStack(alignment: .leading, spacing: 14) {
            SectionLabel(title: L("Pages shared between you"))
            if entries.isEmpty { Text(L("When either of you shares a journal entry with your companion, the selected passage appears here.")).font(.subheadline).foregroundStyle(DearlyTheme.muted) }
            ForEach(entries) { entry in
                VStack(alignment: .leading, spacing: 10) {
                    Text(store.state.profile(entry.authorID)?.nickname ?? L("Friend")).font(.caption.weight(.semibold))
                    Text(entry.sharedText).font(.system(size: 18, design: .serif)).lineSpacing(5)
                    Tag(text: entry.support.title, icon: "ear")
                }.frame(maxWidth: .infinity, alignment: .leading).padding(20).dearlyCard()
            }
        }
    }
}

@MainActor
struct ProfileCard: View {
    @AppStorage("dearly.language") private var language = "en"
    @EnvironmentObject private var store: DearlyStore
    var profile: Profile
    private var pending: Bool {
        store.state.invitations.contains { Set([$0.senderID, $0.recipientID]) == Set([store.me.id, profile.id]) }
    }
    var body: some View {
        VStack(alignment: .leading, spacing: 17) {
            HStack(spacing: 12) {
                Avatar(symbol: profile.symbol, size: 50)
                VStack(alignment: .leading, spacing: 4) {
                    Text(profile.nickname).font(.system(size: 23, design: .serif))
                    Text(LF("Age %1$@ · %2$@", String(describing: profile.age), String(describing: profile.pace))).font(.caption).foregroundStyle(DearlyTheme.muted)
                }
                Spacer()
            }
            Text(profile.bio).font(.subheadline).lineSpacing(4).foregroundStyle(DearlyTheme.muted)
            ScrollView(.horizontal, showsIndicators: false) {
                HStack { ForEach(profile.interests, id: \.self) { Tag(text: $0, color: store.me.interests.contains($0) ? DearlyTheme.sage : DearlyTheme.cream) } }
            }
            PrimaryButton(title: pending ? L("Invitation sent") : L("Send invitation"), icon: "person.badge.plus") {
                Task { await store.invite(profile.id) }
            }.disabled(pending).opacity(pending ? 0.55 : 1)
        }.padding(22).dearlyCard()
    }
}

@MainActor
struct ChatView: View {
    @AppStorage("dearly.language") private var language = "en"
    @EnvironmentObject private var store: DearlyStore
    @Environment(\.dismiss) private var dismiss
    var connectionID: UUID
    @State private var text = ""
    @State private var reporting = false
    @State private var hasOlderMessages = true
    @State private var confirmLeave = false
    @State private var confirmBlock = false
    private var connection: Connection? { store.state.connections.first { $0.id == connectionID && $0.members.contains(store.me.id) } }
    private var partner: Profile? { connection?.members.first(where: { $0 != store.me.id }).flatMap { store.state.profile($0) } }
    private var messages: [ChatMessage] { connection == nil ? [] : store.state.messages.filter { $0.connectionID == connectionID } }
    var body: some View {
        VStack(spacing: 0) {
            HStack(spacing: 8) {
                Image(systemName: "leaf")
                Text(L("Being here is enough. You don’t have to fix everything."))
            }.font(.caption).foregroundStyle(DearlyTheme.forest).padding(16).frame(maxWidth: .infinity).background(DearlyTheme.sage.opacity(0.5))
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(spacing: 15) {
                        Text(L("Synced with the server while the app is open")).font(.caption2).foregroundStyle(DearlyTheme.muted).padding(.vertical, 16)
                        if messages.isEmpty {
                            EmptyCard(icon: "hand.wave", title: L("Start with a hello"), detail: L("You’ve both agreed to connect. Take the conversation at your own pace.")).padding(.vertical, 20)
                        }
                        if store.isOnline && hasOlderMessages && messages.count >= 100 {
                            Button(L("Load earlier messages")) {
                                Task { hasOlderMessages = await store.loadOlderMessages(connectionID: connectionID, before: messages.first?.id) }
                            }.font(.caption).disabled(store.isBusy)
                        }
                        ForEach(messages) { message in
                            messageBubble(message).id(message.id)
                        }
                        Color.clear.frame(height: 1).id("bottom")
                    }.padding(.horizontal, 18)
                }
                .onAppear { proxy.scrollTo("bottom", anchor: .bottom) }
                .onChange(of: messages.last?.id) { _, _ in withAnimation { proxy.scrollTo("bottom", anchor: .bottom) } }
            }
            if connection?.active == true {
                VStack(spacing: 10) {
                    Button(L("I’m not ready to share today, but I’m still here 🌱")) {
                        text = L("I’m not ready to share today, but I’m still here 🌱")
                    }.font(.caption).foregroundStyle(DearlyTheme.muted)
                    HStack(alignment: .bottom, spacing: 10) {
                        TextField(L("Say a little something…"), text: $text, axis: .vertical).lineLimit(1...5)
                            .padding(13).background(DearlyTheme.surface, in: RoundedRectangle(cornerRadius: 21))
                            .accessibilityIdentifier("chat.message")
                        Button { Task { await send() } } label: {
                            Image(systemName: "arrow.up").font(.headline).foregroundStyle(DearlyTheme.onAccent).frame(width: 46, height: 46)
                                .background(DearlyTheme.forest, in: Circle())
                        }.disabled(text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                            .accessibilityLabel(L("Send message")).accessibilityIdentifier("chat.send")
                    }
                }.padding(15).background(DearlyTheme.cream)
            } else {
                Text(L("This connection has ended. Your garden has been saved.")).font(.footnote).padding()
            }
        }.background(DearlyTheme.cream).navigationTitle(partner?.nickname ?? L("Companion")).navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Menu {
                        Button(L("Report"), systemImage: "flag") { reporting = true }
                        Button(L("Leave connection"), systemImage: "door.left.hand.open", role: .destructive) { confirmLeave = true }
                        Button(L("Block this person"), systemImage: "hand.raised", role: .destructive) { confirmBlock = true }
                    } label: { Image(systemName: "ellipsis.circle") }.accessibilityLabel(L("Safety options"))
                }
            }
            .sheet(isPresented: $reporting) { if let partner { ReportView(userID: partner.id) } }
            .confirmationDialog(L("Leave this connection? Your plants and rewards will stay in your saved garden."), isPresented: $confirmLeave, titleVisibility: .visible) {
                Button(L("Leave connection"), role: .destructive) { Task { if await store.leave() { dismiss() } } }
            }
            .confirmationDialog(L("Block this person and end the connection?"), isPresented: $confirmBlock, titleVisibility: .visible) {
                Button(L("Block"), role: .destructive) {
                    Task { if let partner, await store.block(partner.id) { dismiss() } }
                }
            }
    }
    private func messageBubble(_ message: ChatMessage) -> some View {
        let mine = message.senderID == store.me.id
        return HStack {
            if mine { Spacer(minLength: 44) }
            VStack(alignment: .leading, spacing: 6) {
                Text(message.text).font(.subheadline).lineSpacing(3)
                Text(message.date.formatted(Date.FormatStyle(date: .omitted, time: .shortened).locale(Locale(identifier: AppLanguage.code)))).font(.system(size: 10)).opacity(0.6)
            }.padding(15).foregroundStyle(mine ? DearlyTheme.onAccent : DearlyTheme.ink)
                .background(mine ? DearlyTheme.forest : DearlyTheme.surface, in: RoundedRectangle(cornerRadius: 20))
            if !mine { Spacer(minLength: 44) }
        }
    }
    private func send() async {
        if await store.send(text, connectionID: connectionID) { text = "" }
    }
}
