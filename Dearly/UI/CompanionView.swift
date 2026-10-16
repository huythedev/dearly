import SwiftUI

@MainActor
struct CompanionView: View {
    @AppStorage("dearly.language") private var language = "vi"
    @EnvironmentObject private var store: DearlyStore
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                PageHeading(eyebrow: L("Không cần đi một mình"), title: L("Một người, cùng bạn."), subtitle: L("Bắt đầu từ một điểm chung. Kết nối theo nhịp của hai người."))
                if let partner = store.partner, let connection = store.connection {
                    VStack(alignment: .leading, spacing: 20) {
                        HStack(spacing: 14) {
                            Avatar(symbol: partner.symbol, size: 62)
                            VStack(alignment: .leading, spacing: 5) {
                                Text(partner.nickname).font(.system(size: 26, design: .serif))
                                Text(L("Bạn đồng hành của \(store.me.nickname)", "\(store.me.nickname)’s companion")).font(.caption).foregroundStyle(DearlyTheme.muted)
                            }
                            Spacer()
                        }
                        Text(partner.bio).font(.subheadline).lineSpacing(4).foregroundStyle(DearlyTheme.muted)
                        Tag(text: L("\(connection.totalDays) ngày cùng ở đây", "\(connection.totalDays) days here together"), icon: "leaf")
                        NavigationLink { ChatView(connectionID: connection.id) } label: {
                            HStack { Text(L("Ghé trò chuyện")); Spacer(); Image(systemName: "arrow.right") }
                                .font(.subheadline.weight(.semibold)).padding(18).foregroundStyle(DearlyTheme.onAccent)
                                .background(DearlyTheme.forest, in: RoundedRectangle(cornerRadius: 17))
                        }.accessibilityIdentifier("companion.chat")
                    }.padding(23).dearlyCard()
                    Text(L("Bạn không cần luôn có câu trả lời. Được lắng nghe và được nghỉ đều quan trọng."))
                        .font(.system(size: 21, design: .serif)).lineSpacing(5).padding(20)
                    sharedJournals(connection)
                } else {
                    if store.isOnline && !store.me.ageVerified {
                        Label(L("Tài khoản cần quản trị viên xác minh tuổi trước khi gửi hoặc nhận lời mời."), systemImage: "person.crop.circle.badge.exclamationmark")
                            .font(.subheadline).padding(18).dearlyCard()
                    }
                    invitations
                    SectionLabel(title: L("Có thể cùng nhịp"), detail: L("Từ sở thích bạn chọn"))
                    ForEach(store.state.suggestions) { profile in ProfileCard(profile: profile) }
                    if store.state.suggestions.isEmpty {
                        EmptyCard(icon: "person.2", title: L("Chưa có gợi ý phù hợp"), detail: L("Các nhóm tuổi được tách riêng. Bạn có thể tiếp tục viết journal trong lúc chờ."))
                    }
                    Text(L("Bạn có quyền từ chối mà không cần giải thích. Journal riêng tư không được dùng để ghép bạn."))
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
                    Tag(text: L("MỘT LỜI MỜI"), icon: "envelope", color: DearlyTheme.peach)
                    Text(L("\(store.state.profile(invitation.senderID)?.nickname ?? "Một người bạn") muốn đồng hành cùng bạn.", "\(store.state.profile(invitation.senderID)?.nickname ?? L("Một người bạn")) would like to connect with you."))
                        .font(.system(size: 21, design: .serif))
                    if let profile = store.state.profile(invitation.senderID) {
                        Text(L("\(profile.age) tuổi · \(profile.interests.joined(separator: " · "))\n\(profile.bio)", "Age \(profile.age) · \(profile.interests.joined(separator: " · "))\n\(profile.bio)")).font(.subheadline).foregroundStyle(DearlyTheme.muted)
                    }
                    HStack {
                        Button(L("Để lần khác")) { Task { await store.dismissInvitation(invitation.id) } }.font(.subheadline)
                        Spacer()
                        Button(L("Đồng ý kết nối")) {
                            Task { await store.accept(invitation.id) }
                        }.buttonStyle(.borderedProminent).foregroundStyle(DearlyTheme.onAccent).accessibilityIdentifier("companion.accept")
                    }
                }.padding(20).dearlyCard()
            }
            ForEach(outgoing) { invitation in
                HStack {
                    VStack(alignment: .leading, spacing: 5) {
                        Text(L("Đã mời \(store.state.profile(invitation.recipientID)?.nickname ?? "bạn")", "Invited \(store.state.profile(invitation.recipientID)?.nickname ?? L("bạn"))")).font(.subheadline.weight(.medium))
                        Text(L("Chờ người kia đồng ý")).font(.caption).foregroundStyle(DearlyTheme.muted)
                    }
                    Spacer()
                    Button(L("Hủy")) { Task { await store.dismissInvitation(invitation.id) } }.font(.caption)
                }.padding(18).dearlyCard()
            }
        }
    }

    private func sharedJournals(_ connection: Connection) -> some View {
        let entries = store.state.journals.filter {
            $0.audience == .companion && $0.connectionID == connection.id && store.state.canRead($0)
        }
        return VStack(alignment: .leading, spacing: 14) {
            SectionLabel(title: L("Những trang chia sẻ riêng"))
            if entries.isEmpty { Text(L("Khi một trong hai chia sẻ journal với bạn đồng hành, phần được chọn sẽ hiện ở đây.")).font(.subheadline).foregroundStyle(DearlyTheme.muted) }
            ForEach(entries) { entry in
                VStack(alignment: .leading, spacing: 10) {
                    Text(store.state.profile(entry.authorID)?.nickname ?? L("Bạn")).font(.caption.weight(.semibold))
                    Text(entry.sharedText).font(.system(size: 18, design: .serif)).lineSpacing(5)
                    Tag(text: L(entry.support.rawValue), icon: "ear")
                }.frame(maxWidth: .infinity, alignment: .leading).padding(20).dearlyCard()
            }
        }
    }
}

@MainActor
struct ProfileCard: View {
    @AppStorage("dearly.language") private var language = "vi"
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
                    Text(L("\(profile.age) tuổi · \(profile.pace)", "Age \(profile.age) · \(profile.pace)")).font(.caption).foregroundStyle(DearlyTheme.muted)
                }
                Spacer()
            }
            Text(profile.bio).font(.subheadline).lineSpacing(4).foregroundStyle(DearlyTheme.muted)
            ScrollView(.horizontal, showsIndicators: false) {
                HStack { ForEach(profile.interests, id: \.self) { Tag(text: $0, color: store.me.interests.contains($0) ? DearlyTheme.sage : DearlyTheme.cream) } }
            }
            PrimaryButton(title: pending ? L("Đã có lời mời") : L("Gửi lời mời"), icon: "person.badge.plus") {
                Task { await store.invite(profile.id) }
            }.disabled(pending).opacity(pending ? 0.55 : 1)
        }.padding(22).dearlyCard()
    }
}

@MainActor
struct ChatView: View {
    @AppStorage("dearly.language") private var language = "vi"
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
                Text(L("Có mặt là đủ. Bạn không cần phải giải quyết mọi chuyện."))
            }.font(.caption).foregroundStyle(DearlyTheme.forest).padding(16).frame(maxWidth: .infinity).background(DearlyTheme.sage.opacity(0.5))
            ScrollViewReader { proxy in
                ScrollView {
                    LazyVStack(spacing: 15) {
                        Text(L("Đồng bộ qua server · Làm mới khi app đang mở")).font(.caption2).foregroundStyle(DearlyTheme.muted).padding(.vertical, 16)
                        if messages.isEmpty {
                            EmptyCard(icon: "hand.wave", title: L("Bắt đầu bằng một lời chào"), detail: L("Hai người đã đồng ý kết nối. Cứ trò chuyện theo nhịp của bạn.")).padding(.vertical, 20)
                        }
                        if store.isOnline && hasOlderMessages && messages.count >= 100 {
                            Button(L("Tải tin nhắn trước đó")) {
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
                    Button(L("Hôm nay mình chưa muốn kể, nhưng vẫn ở đây 🌱")) {
                        text = L("Hôm nay mình chưa muốn kể, nhưng vẫn ở đây 🌱")
                    }.font(.caption).foregroundStyle(DearlyTheme.muted)
                    HStack(alignment: .bottom, spacing: 10) {
                        TextField(L("Nhắn một lời…"), text: $text, axis: .vertical).lineLimit(1...5)
                            .padding(13).background(DearlyTheme.surface, in: RoundedRectangle(cornerRadius: 21))
                            .accessibilityIdentifier("chat.message")
                        Button { Task { await send() } } label: {
                            Image(systemName: "arrow.up").font(.headline).foregroundStyle(DearlyTheme.onAccent).frame(width: 46, height: 46)
                                .background(DearlyTheme.forest, in: Circle())
                        }.disabled(text.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                            .accessibilityLabel(L("Gửi tin nhắn")).accessibilityIdentifier("chat.send")
                    }
                }.padding(15).background(DearlyTheme.cream)
            } else {
                Text(L("Kết nối đã kết thúc. Khu vườn được lưu lại.")).font(.footnote).padding()
            }
        }.background(DearlyTheme.cream).navigationTitle(partner?.nickname ?? L("Đồng hành")).navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .topBarTrailing) {
                    Menu {
                        Button(L("Báo cáo"), systemImage: "flag") { reporting = true }
                        Button(L("Rời kết nối"), systemImage: "door.left.hand.open", role: .destructive) { confirmLeave = true }
                        Button(L("Chặn người này"), systemImage: "hand.raised", role: .destructive) { confirmBlock = true }
                    } label: { Image(systemName: "ellipsis.circle") }.accessibilityLabel(L("Tùy chọn an toàn"))
                }
            }
            .sheet(isPresented: $reporting) { if let partner { ReportView(userID: partner.id) } }
            .confirmationDialog(L("Rời kết nối? Cây và phần thưởng sẽ được giữ trong vườn lưu trữ."), isPresented: $confirmLeave, titleVisibility: .visible) {
                Button(L("Rời kết nối"), role: .destructive) { Task { if await store.leave() { dismiss() } } }
            }
            .confirmationDialog(L("Chặn và kết thúc kết nối này?"), isPresented: $confirmBlock, titleVisibility: .visible) {
                Button(L("Chặn"), role: .destructive) {
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
                Text(message.date.formatted(Date.FormatStyle(date: .omitted, time: .shortened).locale(Locale(identifier: language)))).font(.system(size: 10)).opacity(0.6)
            }.padding(15).foregroundStyle(mine ? DearlyTheme.onAccent : DearlyTheme.ink)
                .background(mine ? DearlyTheme.forest : DearlyTheme.surface, in: RoundedRectangle(cornerRadius: 20))
            if !mine { Spacer(minLength: 44) }
        }
    }
    private func send() async {
        if await store.send(text, connectionID: connectionID) { text = "" }
    }
}
