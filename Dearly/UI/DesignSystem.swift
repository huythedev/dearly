import SwiftUI

enum DearlyTheme {
    static let cream = Color(red: 0.975, green: 0.966, blue: 0.943)
    static let forest = Color(red: 0.24, green: 0.36, blue: 0.29)
    static let ink = Color(red: 0.20, green: 0.25, blue: 0.22)
    static let muted = Color(red: 0.43, green: 0.47, blue: 0.43)
    static let sage = Color(red: 0.88, green: 0.92, blue: 0.84)
    static let peach = Color(red: 0.96, green: 0.87, blue: 0.81)
    static let border = Color(red: 0.88, green: 0.88, blue: 0.83)
}

@MainActor
struct PrimaryButton: View {
    @AppStorage("dearly.language") private var language = "vi"
    var title: String
    var icon: String = "arrow.right"
    var action: () -> Void
    var body: some View {
        Button(action: action) {
            HStack(spacing: 10) {
                Text(title).font(.system(.subheadline, design: .rounded, weight: .semibold))
                Spacer(minLength: 8)
                Image(systemName: icon)
            }
            .padding(.horizontal, 20).padding(.vertical, 17)
            .foregroundStyle(.white).background(DearlyTheme.forest, in: RoundedRectangle(cornerRadius: 18))
        }.buttonStyle(.plain)
    }
}

@MainActor
struct Tag: View {
    @AppStorage("dearly.language") private var language = "vi"
    var text: String
    var icon: String?
    var color: Color = DearlyTheme.sage
    var body: some View {
        HStack(spacing: 5) {
            if let icon { Image(systemName: icon) }
            Text(text)
        }
        .font(.system(size: 11, weight: .medium, design: .rounded))
        .foregroundStyle(DearlyTheme.forest)
        .padding(.horizontal, 10).padding(.vertical, 7)
        .background(color, in: Capsule())
    }
}

@MainActor
struct Avatar: View {
    @AppStorage("dearly.language") private var language = "vi"
    var symbol: String
    var size: CGFloat = 44
    var body: some View {
        Image(systemName: symbol)
            .font(.system(size: size * 0.38, weight: .medium))
            .foregroundStyle(DearlyTheme.forest)
            .frame(width: size, height: size)
            .background(DearlyTheme.sage, in: Circle())
            .accessibilityHidden(true)
    }
}

@MainActor
struct PageHeading: View {
    @AppStorage("dearly.language") private var language = "vi"
    var eyebrow: String
    var title: String
    var subtitle: String
    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            Text(eyebrow.uppercased()).font(.system(size: 10, weight: .bold, design: .rounded))
                .tracking(2.2).foregroundStyle(DearlyTheme.muted)
            Text(title).font(.system(size: 34, weight: .regular, design: .serif))
                .tracking(-0.8).foregroundStyle(DearlyTheme.ink)
            Text(subtitle).font(.subheadline).foregroundStyle(DearlyTheme.muted).lineSpacing(4)
        }.frame(maxWidth: .infinity, alignment: .leading)
    }
}

@MainActor
struct SectionLabel: View {
    @AppStorage("dearly.language") private var language = "vi"
    var title: String
    var detail: String = ""
    var body: some View {
        HStack {
            Text(title).font(.system(.headline, design: .rounded))
            Spacer()
            Text(detail).font(.caption).foregroundStyle(DearlyTheme.muted)
        }.foregroundStyle(DearlyTheme.ink)
    }
}

@MainActor
struct EmptyCard: View {
    @AppStorage("dearly.language") private var language = "vi"
    var icon: String
    var title: String
    var detail: String
    var body: some View {
        VStack(spacing: 14) {
            Image(systemName: icon).font(.system(size: 30, weight: .light)).foregroundStyle(DearlyTheme.forest)
            Text(title).font(.system(.title3, design: .serif))
            Text(detail).font(.subheadline).foregroundStyle(DearlyTheme.muted).multilineTextAlignment(.center)
        }.frame(maxWidth: .infinity).padding(28).dearlyCard()
    }
}

extension View {
    func dearlyCard() -> some View {
        background(.white.opacity(0.78), in: RoundedRectangle(cornerRadius: 24))
            .overlay(RoundedRectangle(cornerRadius: 24).stroke(DearlyTheme.border.opacity(0.65), lineWidth: 1))
    }
}

@MainActor
struct RootView: View {
    @AppStorage("dearly.language") private var language = "vi"
    @EnvironmentObject private var store: DearlyStore
    @State private var tab = 0
    @State private var showSettings = false
    @Environment(\.scenePhase) private var scenePhase
    var body: some View {
        Group {
            if store.isOnline {
                tabs
            } else {
                ServerConnectionView()
            }
        }
        .environment(\.locale, Locale(identifier: language))
        .task { await store.syncLoop() }
        .onChange(of: scenePhase) { _, phase in store.foreground = phase == .active }
    }

    private var tabs: some View {
        TabView(selection: $tab) {
            page { JournalView() }.tabItem { Label(L("Journal"), systemImage: "book.closed") }.tag(0)
            page { CommunityView() }.tabItem { Label(L("Cộng đồng"), systemImage: "bubble.left.and.bubble.right") }.tag(1)
            page { CompanionView() }.tabItem { Label(L("Đồng hành"), systemImage: "person.2") }.tag(2)
            page { GardenView() }.tabItem { Label(L("Khu vườn"), systemImage: "leaf") }.tag(3)
        }
        .id(store.me.id)
        .disabled(store.isBusy || store.isAuthenticating)
        .sheet(isPresented: $showSettings) { AccountSettingsView() }
        .alert("Dearly", isPresented: Binding(get: { store.errorMessage != nil }, set: { if !$0 { store.errorMessage = nil } })) {
            Button(L("Đã hiểu")) { store.errorMessage = nil }
        } message: { Text(store.errorMessage ?? "") }
        .alert(L("Đã ghi nhận"), isPresented: Binding(get: { store.notice != nil }, set: { if !$0 { store.notice = nil } })) {
            Button(L("Đóng")) { store.notice = nil }
        } message: { Text(store.notice ?? "") }
    }

    private func page<Content: View>(@ViewBuilder content: () -> Content) -> some View {
        NavigationStack {
            content()
                .safeAreaInset(edge: .top, spacing: 0) {
                    if store.isOnline {
                        HStack(spacing: 7) {
                            Image(systemName: store.syncError == nil ? "network" : "wifi.exclamationmark")
                            Text(store.syncError == nil ? L("Đã kết nối server · \(store.me.nickname)", "Connected · \(store.me.nickname)") : L("Mất đồng bộ · Tự thử lại khi mạng ổn định"))
                            Spacer()
                            if store.isBusy { ProgressView().controlSize(.small) }
                        }.font(.caption2).foregroundStyle(DearlyTheme.forest).padding(.horizontal, 22).padding(.vertical, 7).background(DearlyTheme.sage.opacity(0.6))
                    }
                }
                .background(DearlyTheme.cream.ignoresSafeArea())
                .toolbar {
                    if #available(iOS 26.0, *) {
                        ToolbarItem(placement: .topBarLeading) { DearlyBrand() }
                            .sharedBackgroundVisibility(.hidden)
                    } else {
                        ToolbarItem(placement: .topBarLeading) { DearlyBrand() }
                    }
                    ToolbarItem(placement: .topBarTrailing) {
                        Button { showSettings = true } label: {
                            HStack(spacing: 7) {
                                Text("ONLINE").font(.system(size: 9, weight: .bold)).tracking(1)
                                Avatar(symbol: store.me.symbol, size: 32)
                            }
                        }.accessibilityLabel(L("Cài đặt tài khoản \(store.me.nickname)", "Account settings for \(store.me.nickname)"))
                    }
                }
                .toolbarBackground(DearlyTheme.cream, for: .navigationBar, .tabBar)
                .toolbarBackground(.visible, for: .navigationBar, .tabBar)
        }
    }
}

@MainActor
struct WelcomeView: View {
    @AppStorage("dearly.language") private var language = "vi"
    var start: () -> Void
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 28) {
                Text("dearly").font(.system(size: 36, design: .serif)).foregroundStyle(DearlyTheme.forest)
                GardenIllustration(stage: 3).frame(height: 270).clipShape(RoundedRectangle(cornerRadius: 32))
                Text(L("Có một nơi,\nbạn được lắng nghe."))
                    .font(.system(size: 39, weight: .regular, design: .serif)).tracking(-1)
                Text(L("Viết điều chưa biết kể với ai. Tìm một người sẵn lòng lắng nghe. Cùng nuôi một khu vườn nhỏ."))
                    .font(.body).lineSpacing(5).foregroundStyle(DearlyTheme.muted)
                HStack(alignment: .top, spacing: 10) {
                    Image(systemName: "lock.shield")
                    Text(L("Journal mặc định riêng tư. Bạn luôn được chọn chia sẻ, nghỉ ngơi hoặc rời kết nối."))
                }.font(.footnote).foregroundStyle(DearlyTheme.forest)
                PrimaryButton(title: L("Bắt đầu một khoảng dịu dàng"), action: start)
                Text(L("Đăng nhập hoặc tạo tài khoản để kết nối server. Dearly là không gian đồng hành, không phải dịch vụ trị liệu."))
                    .font(.caption).foregroundStyle(DearlyTheme.muted).lineSpacing(3)
            }.padding(28)
        }.background(DearlyTheme.cream).foregroundStyle(DearlyTheme.ink)
    }
}

@MainActor
struct AccountSettingsView: View {
    @AppStorage("dearly.language") private var language = "vi"
    @EnvironmentObject private var store: DearlyStore
    @Environment(\.dismiss) private var dismiss
    @State private var editingProfile = false
    var body: some View {
        NavigationStack {
            Form {
                Section(L("Ngôn ngữ")) {
                    LanguagePicker()
                }
                if store.isOnline {
                    Section(L("Tài khoản đang kết nối")) {
                        LabeledContent(L("Nickname"), value: store.me.nickname)
                        LabeledContent("Server", value: store.serverAddress)
                        LabeledContent(L("Tuổi"), value: store.me.ageVerified ? L("Đã xác minh") : L("Chờ quản trị viên xác minh"))
                        if let date = store.lastSync { LabeledContent(L("Đồng bộ"), value: date.formatted(Date.FormatStyle(date: .omitted, time: .shortened).locale(Locale(identifier: language)))) }
                        if let error = store.syncError { Text(error).font(.caption).foregroundStyle(.red) }
                        Button(L("Sửa hồ sơ"), systemImage: "person.crop.circle") { editingProfile = true }
                        Button(L("Đồng bộ ngay"), systemImage: "arrow.clockwise") { Task { await store.refresh(force: true) } }
                        Button(L("Đăng xuất"), role: .destructive) { Task { await store.logout() } }.disabled(store.isBusy)
                    }
                    Section {
                        Text(L("Khi online, server quyết định quyền truy cập và ngày check-in (UTC). Tin nhắn tự đồng bộ khoảng 3 giây khi app đang mở. Dữ liệu được lưu trên server.")).font(.caption)
                    }
                }
            }.navigationTitle(L("Cài đặt Dearly")).navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .confirmationAction) { Button(L("Xong")) { dismiss() } } }
                .sheet(isPresented: $editingProfile) { ProfileEditorView() }
        }
    }
}


@MainActor
struct DearlyBrand: View {
    var body: some View {
        HStack(alignment: .center, spacing: 8) {
            Image(systemName: "leaf.fill")
                .font(.system(size: 17, weight: .medium))
                .frame(width: 32, height: 32)
                .background(DearlyTheme.sage, in: RoundedRectangle(cornerRadius: 11))
            Text(verbatim: "dearly")
                .font(.system(size: 27, weight: .regular, design: .serif))
                .tracking(-0.7)
        }
        .foregroundStyle(DearlyTheme.forest)
        .fixedSize(horizontal: true, vertical: true)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Dearly")
    }
}

@MainActor
struct LanguageMenu: View {
    @AppStorage("dearly.language") private var language = "vi"
    var body: some View {
        Menu {
            LanguagePicker()
        } label: {
            HStack(spacing: 6) {
                Image(systemName: "globe")
                Text(language == "en" ? "EN" : "VI")
                Image(systemName: "chevron.down").font(.system(size: 8, weight: .bold))
            }.font(.caption.weight(.semibold)).foregroundStyle(DearlyTheme.forest)
                .padding(.horizontal, 12).padding(.vertical, 10)
                .background(.white.opacity(0.7), in: Capsule())
                .overlay(Capsule().stroke(DearlyTheme.border, lineWidth: 1))
        }.accessibilityLabel(L("Ngôn ngữ"))
    }
}

@MainActor
struct LanguagePicker: View {
    @AppStorage("dearly.language") private var language = "vi"
    var body: some View {
        Picker(L("Ngôn ngữ"), selection: $language) {
            Text(verbatim: "Tiếng Việt").tag("vi")
            Text(verbatim: "English").tag("en")
        }
    }
}
