import SwiftUI

@MainActor
struct CommunityView: View {
    @AppStorage("dearly.language") private var language = "vi"
    @EnvironmentObject private var store: DearlyStore
    @State private var filter: SupportStyle?
    @State private var selected: Journal?
    private var entries: [Journal] { store.state.feed.filter { filter == nil || $0.support == filter } }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                PageHeading(eyebrow: L("Những câu chuyện ở đây"), title: L("Lắng nghe một chút."), subtitle: L("Đôi khi, có người ở đó đã là đủ."))
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 8) {
                        filterButton(L("Tất cả"), value: nil)
                        ForEach(SupportStyle.allCases) { filterButton(L($0.rawValue), value: $0) }
                    }
                }
                HStack(spacing: 10) {
                    Image(systemName: "heart.text.square")
                    Text(L("Một lời dịu dàng. Không phán xét, không vội đưa lời khuyên.")).font(.caption).lineSpacing(3)
                }.foregroundStyle(DearlyTheme.muted)
                ForEach(entries) { entry in
                    CommunityCard(entry: entry) { selected = entry }
                }
                if entries.isEmpty { EmptyCard(icon: "bubble.left", title: L("Một khoảng yên"), detail: L("Chưa có câu chuyện ở đây. Những trang bạn publish sẽ xuất hiện tại đây.")) }
                Text(L("Các bài mới nhất · Kéo xuống để đồng bộ"))
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
    @AppStorage("dearly.language") private var language = "vi"
    @EnvironmentObject private var store: DearlyStore
    var entry: Journal
    var open: () -> Void
    var body: some View {
        VStack(alignment: .leading, spacing: 17) {
            HStack(spacing: 11) {
                Avatar(symbol: entry.anonymous ? "sparkles" : store.state.profile(entry.authorID)?.symbol ?? "leaf")
                VStack(alignment: .leading, spacing: 4) {
                    Text(entry.anonymous ? L("Một người bạn") : store.state.profile(entry.authorID)?.nickname ?? L("Bạn"))
                        .font(.subheadline.weight(.semibold)).foregroundStyle(DearlyTheme.ink)
                    Text(entry.anonymous ? L("Chia sẻ ẩn danh") : entry.date.formatted(Date.FormatStyle(date: .abbreviated, time: .omitted).locale(Locale(identifier: language))))
                        .font(.caption2).foregroundStyle(DearlyTheme.muted)
                }
                Spacer()
                Image(systemName: "quote.opening").font(.title2).foregroundStyle(DearlyTheme.border)
            }
            Button(action: open) {
                Text(entry.sharedText).font(.system(size: 17, design: .serif)).lineSpacing(6)
                    .foregroundStyle(DearlyTheme.ink).frame(maxWidth: .infinity, alignment: .leading)
            }.buttonStyle(.plain)
            Tag(text: L(entry.support.rawValue), icon: "ear")
            Rectangle().fill(DearlyTheme.border).frame(height: 1)
            HStack {
                Button {
                    Task { await store.toggleListening(entry) }
                } label: {
                    Label(entry.listeners.contains(store.me.id) ? L("Đang lắng nghe") : L("T đang lắng nghe"), systemImage: entry.listeners.contains(store.me.id) ? "heart.fill" : "heart")
                        .font(.caption.weight(.medium))
                }.disabled(entry.authorID == store.me.id)
                Spacer()
                Button(action: open) { Image(systemName: "bubble.left").frame(width: 44, height: 32) }
                    .accessibilityLabel(L("Mở câu chuyện và phản hồi"))
            }
        }.padding(21).dearlyCard()
    }
}

@MainActor
struct CommunityDetail: View {
    @AppStorage("dearly.language") private var language = "vi"
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
                                PrimaryButton(title: L("Gửi lời mời đồng hành"), icon: "person.badge.plus") {
                                    Task { if await store.invite(entry.authorID, journalID: entry.id) { dismiss() } }
                                }
                                Text(L("Chỉ mở chat khi cả hai đồng ý. Người nhận lời mời sẽ thấy nickname của bạn."))
                                    .font(.caption).foregroundStyle(DearlyTheme.muted)
                            } else if entry.anonymous {
                                Text(L("Bài ẩn danh không liên kết với hồ sơ. Bạn có thể ẩn riêng bài này hoặc gửi báo cáo.", "Anonymous stories do not link to profiles. You can hide this story or report it."))
                                    .font(.caption).foregroundStyle(DearlyTheme.muted)
                            } else {
                                Text(L("Lời mời chỉ khả dụng khi cả hai chưa có kết nối và thuộc nhóm tuổi phù hợp."))
                                    .font(.caption).foregroundStyle(DearlyTheme.muted)
                            }
                            HStack {
                                Button(L("Báo cáo"), systemImage: "flag") { reportPresented = true }
                                Spacer()
                                Button(entry.anonymous ? L("Ẩn bài này", "Hide this story") : L("Chặn"), systemImage: "hand.raised", role: .destructive) { blockConfirmation = true }
                            }.font(.caption)
                        }
                        SectionLabel(title: L("Phản hồi"), detail: entry.commentsEnabled ? L("Nhẹ nhàng thôi nhé") : L("Đã tắt"))
                        ForEach(store.state.comments.filter { $0.journalID == journalID && !store.state.isBlocked(store.me.id, $0.authorID) }) { comment in
                            VStack(alignment: .leading, spacing: 8) {
                                Text(entry.anonymous && comment.authorID == entry.authorID ? L("Tác giả ẩn danh") : store.state.profile(comment.authorID)?.nickname ?? L("Bạn"))
                                    .font(.caption.weight(.semibold))
                                Text(comment.text).font(.subheadline).lineSpacing(3)
                            }.frame(maxWidth: .infinity, alignment: .leading).padding(16).dearlyCard()
                        }
                        if entry.commentsEnabled {
                            TextField(L("Một lời theo điều người viết cần…"), text: $response, axis: .vertical)
                                .lineLimit(2...5).padding(16).dearlyCard()
                            PrimaryButton(title: L("Gửi phản hồi"), icon: "arrow.up") {
                                Task { if await store.comment(on: journalID, text: response) { response = "" } }
                            }.disabled(response.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty)
                        }
                    } else {
                        EmptyCard(icon: "lock", title: L("Câu chuyện không còn hiển thị"), detail: L("Người viết có thể đã chuyển bài về riêng tư hoặc xóa bài."))
                    }
                }.padding(22)
            }.background(DearlyTheme.cream)
                .navigationTitle(L("Một câu chuyện")).navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .confirmationAction) { Button(L("Xong")) { dismiss() } } }
                .sheet(isPresented: $reportPresented) { if let entry { ReportView(userID: entry.authorID, journalID: entry.id) } }
                .confirmationDialog(entry?.anonymous == true
                    ? L("Ẩn riêng câu chuyện này? Hồ sơ và các bài khác không bị ảnh hưởng.", "Hide this story only? Profiles and other stories are unaffected.")
                    : L("Chặn người này? Bạn sẽ không thấy bài viết hay nhận lời mời từ họ."), isPresented: $blockConfirmation, titleVisibility: .visible) {
                    Button(entry?.anonymous == true ? L("Ẩn bài này", "Hide this story") : L("Chặn"), role: .destructive) {
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
    @AppStorage("dearly.language") private var language = "vi"
    @EnvironmentObject private var store: DearlyStore
    @Environment(\.dismiss) private var dismiss
    var userID: UUID
    var journalID: UUID? = nil
    @State private var reason = "Quấy rối hoặc đe dọa"
    private let reasons = ["Quấy rối hoặc đe dọa", "Nội dung tình dục không mong muốn", "Ép cung cấp ảnh hoặc thông tin cá nhân", "Khác"]
    var body: some View {
        NavigationStack {
            Form {
                Section(L("Lý do")) { Picker(L("Chọn lý do"), selection: $reason) { ForEach(reasons, id: \.self) { Text(L($0)) } }.pickerStyle(.inline).labelsHidden() }
                Section { Text(L("Báo cáo được gửi tới server để quản trị viên xem xét. Bạn có thể chặn hoặc rời kết nối ngay.")) }
                Button(L("Gửi báo cáo")) {
                    Task { if await store.report(userID, journalID: journalID, reason: reason) { dismiss() } }
                }.disabled(store.isBusy)
                if let error = store.errorMessage { Text(error).foregroundStyle(.red) }
            }.navigationTitle(L("Báo cáo")).navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .cancellationAction) { Button(L("Hủy")) { dismiss() } } }
        }
    }
}
