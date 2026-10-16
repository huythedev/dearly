import SwiftUI

@MainActor
struct JournalView: View {
    @AppStorage("dearly.language") private var language = "vi"
    @EnvironmentObject private var store: DearlyStore
    @State private var composing = false
    @State private var editing: Journal?
    @State private var showingArchive = false
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 26) {
                PageHeading(eyebrow: L("Một khoảng cho riêng bạn"), title: L("Hôm nay, bạn thế nào?"), subtitle: L("Không cần viết thật hay. Chỉ cần là bạn."))
                VStack(alignment: .leading, spacing: 18) {
                    HStack { Tag(text: L("GỢI Ý HÔM NAY"), icon: "sparkle", color: DearlyTheme.surface.opacity(0.55)); Spacer(); Image(systemName: "sun.max").font(.title2) }
                    Text(L("Có điều gì bạn muốn nói,\nnhưng vẫn chưa nói được?"))
                        .font(.system(size: 25, design: .serif)).lineSpacing(5)
                    Button { composing = true } label: {
                        HStack { Text(L("Để vài dòng ở đây")).fontWeight(.medium); Spacer(); Image(systemName: "arrow.up.right") }
                            .font(.subheadline).padding(.top, 8)
                    }.accessibilityIdentifier("journal.compose")
                }.padding(23).foregroundStyle(DearlyTheme.forest)
                    .background(DearlyTheme.sage, in: RoundedRectangle(cornerRadius: 25))
                HStack(spacing: 8) {
                    Image(systemName: "lock").font(.caption)
                    Text(L("Chỉ bạn đọc được, cho đến khi bạn chọn chia sẻ.")).font(.caption)
                }.foregroundStyle(DearlyTheme.muted)
                SectionLabel(title: L("Những trang của bạn"), detail: L("\(store.state.myJournals.count) trang", "\(store.state.myJournals.count) pages"))
                if store.isOnline {
                    Button(L("Xem tất cả trang trên server"), systemImage: "books.vertical") { showingArchive = true }
                        .font(.subheadline)
                }
                if store.state.myJournals.isEmpty {
                    EmptyCard(icon: "book", title: L("Trang đầu đang chờ bạn"), detail: L("Một câu ngắn cũng là một khởi đầu."))
                }
                ForEach(store.state.myJournals) { entry in
                    Button { editing = entry } label: { JournalRow(entry: entry) }.buttonStyle(.plain)
                }
                Button { composing = true } label: {
                    Label(L("Viết một trang mới"), systemImage: "plus").font(.subheadline.weight(.semibold)).frame(maxWidth: .infinity).padding(16)
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
    @AppStorage("dearly.language") private var language = "vi"
    @EnvironmentObject private var store: DearlyStore
    @Environment(\.dismiss) private var dismiss
    @State private var page: JournalPage?
    @State private var cursors: [UUID?] = [nil]
    @State private var loading = false
    @State private var error: String?
    @State private var editing: Journal?
    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(spacing: 18) {
                    Text(L("Trang \(cursors.count) · Tải tối đa 40 journal mỗi lần", "Page \(cursors.count) · Up to 40 entries per page")).font(.caption).foregroundStyle(DearlyTheme.muted)
                    if let error { Text(error).foregroundStyle(.red) }
                    if loading { ProgressView() }
                    ForEach(page?.items ?? []) { entry in
                        Button { editing = entry } label: { JournalRow(entry: entry) }.buttonStyle(.plain)
                    }
                    HStack {
                        if cursors.count > 1 {
                            Button(L("Trang trước")) { cursors.removeLast(); Task { await load() } }.disabled(loading)
                        }
                        Spacer()
                        if let next = page?.nextCursor {
                            Button(L("Trang tiếp")) { cursors.append(next); Task { await load() } }.disabled(loading)
                        }
                    }
                }.padding(22)
            }.background(DearlyTheme.cream)
                .navigationTitle(L("Các trang của bạn")).navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .confirmationAction) { Button(L("Xong")) { dismiss() } } }
                .sheet(item: $editing, onDismiss: { Task { await load() } }) { JournalEditor(entry: $0) }
                .task { await load() }
                .onChange(of: store.me.id) { _, _ in dismiss() }
        }
    }
    private func load() async {
        loading = true
        defer { loading = false }
        do { page = try await store.journalPage(before: cursors.last ?? nil); error = nil }
        catch { self.error = error.localizedDescription }
    }
}

@MainActor
struct JournalRow: View {
    @AppStorage("dearly.language") private var language = "vi"
    var entry: Journal
    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Text(entry.date.formatted(.dateTime.day().month(.wide).locale(Locale(identifier: language)))).font(.caption).foregroundStyle(DearlyTheme.muted)
                Spacer()
                Image(systemName: entry.audience.icon).foregroundStyle(DearlyTheme.forest)
            }
            Text(entry.title.isEmpty ? L("Một trang của mình") : entry.title)
                .font(.system(size: 21, design: .serif)).foregroundStyle(DearlyTheme.ink)
            Text(entry.body).font(.subheadline).foregroundStyle(DearlyTheme.muted).lineSpacing(4).lineLimit(3)
            Tag(text: L(entry.audience.title), icon: entry.audience.icon)
        }.padding(21).frame(maxWidth: .infinity, alignment: .leading).dearlyCard()
    }
}

@MainActor
struct JournalEditor: View {
    @AppStorage("dearly.language") private var language = "vi"
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

    var body: some View {
        NavigationStack {
            Form {
                Section {
                    TextField(L("Đặt tên cho hôm nay (tùy chọn)"), text: $title)
                        .font(.system(.title3, design: .serif))
                    TextEditor(text: $bodyText).frame(minHeight: 220)
                        .accessibilityLabel(L("Nội dung journal")).accessibilityIdentifier("journal.body")
                } header: { Text(L("Bạn có thể bắt đầu từ bất cứ đâu")) }
                Section {
                    Picker(L("Ai được đọc?"), selection: $audience) {
                        ForEach(Audience.allCases) { option in Text(L(option.title)).tag(option) }
                    }
                    if audience != .privateOnly {
                        Toggle(L("Chỉ chia sẻ một đoạn"), isOn: $useExcerpt)
                        if useExcerpt {
                            Text(L("Dán chính xác đoạn muốn chia sẻ. Phần còn lại luôn riêng tư.")).font(.caption)
                            TextEditor(text: $excerpt).frame(minHeight: 100).accessibilityLabel(L("Đoạn được chia sẻ"))
                        }
                        Picker(L("Mình muốn"), selection: $support) {
                            ForEach(SupportStyle.allCases) { Text(L($0.rawValue)).tag($0) }
                        }
                    }
                    if audience == .community {
                        Toggle(L("Ẩn danh bài viết này"), isOn: $anonymous)
                        Toggle(L("Cho phép phản hồi"), isOn: $commentsEnabled)
                    }
                } header: { Text(L("Bạn chọn điều người khác được thấy")) } footer: {
                    Text(audience == .privateOnly ? L("Mặc định riêng tư. Bạn có thể thay đổi sau.") : L("Chỉ phần nội dung đã chọn được chia sẻ. Tiêu đề journal luôn riêng tư."))
                }
                if audience != .privateOnly {
                    Section(L("Xem trước phần chia sẻ")) {
                        Text(useExcerpt ? excerpt : bodyText).font(.body)
                        Text(anonymous && audience == .community ? L("Hiển thị: Một người bạn · không có liên kết hồ sơ") : L("Hiển thị: \(store.me.nickname)", "Shown as: \(store.me.nickname)"))
                            .font(.caption).foregroundStyle(.secondary)
                    }
                }
                if let validation { Section { Text(validation).foregroundStyle(.red) } }
                if entry != nil {
                    Section { Button(L("Xóa trang này"), role: .destructive) { confirmDelete = true } }
                }
            }
            .navigationTitle(entry == nil ? L("Một trang mới") : L("Trang của bạn")).navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button(L("Hủy")) { dismiss() } }
                ToolbarItem(placement: .confirmationAction) {
                    Button(L("Lưu")) { Task { await save() } }.disabled(store.isBusy).fontWeight(.semibold).accessibilityIdentifier("journal.save")
                }
            }
            .confirmationDialog(L("Xóa vĩnh viễn trang này và các phản hồi?"), isPresented: $confirmDelete, titleVisibility: .visible) {
                Button(L("Xóa trang"), role: .destructive) {
                    Task {
                        if let entry, await store.deleteJournal(entry.id) { dismiss() }
                    }
                }
            }
            .onAppear {
                guard let entry else { return }
                title = entry.title; bodyText = entry.body; excerpt = entry.sharedText
                useExcerpt = !entry.sharedText.isEmpty && entry.sharedText != entry.body
                audience = entry.audience; support = entry.support
                anonymous = entry.anonymous; commentsEnabled = entry.commentsEnabled
            }
        }
    }

    private func save() async {
        let success = await store.saveJournal(id: entry?.id, title: title, body: bodyText,
            sharedText: useExcerpt ? excerpt : bodyText, audience: audience,
            anonymous: anonymous, commentsEnabled: commentsEnabled, support: support)
        if success { dismiss() } else { validation = store.errorMessage }
    }
}
