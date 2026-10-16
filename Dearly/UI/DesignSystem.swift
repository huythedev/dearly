import SwiftUI

enum DearlyTheme {
    static let cream = Color("Background")
    static let forest = Color("Forest")
    static let ink = Color("Ink")
    static let muted = Color("Muted")
    static let sage = Color("Sage")
    static let peach = Color("Peach")
    static let border = Color("Border")
    static let surface = Color("Surface")
    static let onAccent = Color("OnAccent")
}

@MainActor
struct PrimaryButton: View {
    @AppStorage("dearly.language") private var language = "en"
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
            .foregroundStyle(DearlyTheme.onAccent).background(DearlyTheme.forest, in: RoundedRectangle(cornerRadius: 18))
        }.buttonStyle(.plain)
    }
}

@MainActor
struct Tag: View {
    @AppStorage("dearly.language") private var language = "en"
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
    @AppStorage("dearly.language") private var language = "en"
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
    @AppStorage("dearly.language") private var language = "en"
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
    @AppStorage("dearly.language") private var language = "en"
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
    @AppStorage("dearly.language") private var language = "en"
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
        background(DearlyTheme.surface.opacity(0.78), in: RoundedRectangle(cornerRadius: 24))
            .overlay(RoundedRectangle(cornerRadius: 24).stroke(DearlyTheme.border.opacity(0.65), lineWidth: 1))
    }
}

@MainActor
struct RootView: View {
    @AppStorage("dearly.language") private var language = "en"
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
            page { CommunityView() }.tabItem { Label(L("Community"), systemImage: "bubble.left.and.bubble.right") }.tag(1)
            page { CompanionView() }.tabItem { Label(L("Companion"), systemImage: "person.2") }.tag(2)
            page { GardenView() }.tabItem { Label(L("Garden"), systemImage: "leaf") }.tag(3)
        }
        .id(store.me.id)
        .disabled(store.isBusy || store.isAuthenticating)
        .sheet(isPresented: $showSettings) { AccountSettingsView() }
        .alert("Dearly", isPresented: Binding(get: { store.errorMessage != nil }, set: { if !$0 { store.errorMessage = nil } })) {
            Button(L("Got it")) { store.errorMessage = nil }
        } message: { Text(store.errorMessage ?? "") }
        .alert(L("Received"), isPresented: Binding(get: { store.notice != nil }, set: { if !$0 { store.notice = nil } })) {
            Button(L("Close")) { store.notice = nil }
        } message: { Text(store.notice ?? "") }
    }

    private func page<Content: View>(@ViewBuilder content: () -> Content) -> some View {
        NavigationStack {
            content()
                .safeAreaInset(edge: .top, spacing: 0) {
                    if store.isOnline {
                        HStack(spacing: 7) {
                            Image(systemName: store.syncError == nil ? "network" : "wifi.exclamationmark")
                            Text(store.syncError == nil ? LF("Connected · %1$@", String(describing: store.me.nickname)) : L("Sync interrupted · Reconnecting automatically"))
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
                        }.accessibilityLabel(LF("Account settings for %1$@", String(describing: store.me.nickname)))
                    }
                }
                .toolbarBackground(DearlyTheme.cream, for: .navigationBar, .tabBar)
                .toolbarBackground(.visible, for: .navigationBar, .tabBar)
        }
    }
}

@MainActor
struct WelcomeView: View {
    @AppStorage("dearly.language") private var language = "en"
    var start: () -> Void
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 28) {
                Text("dearly").font(.system(size: 36, design: .serif)).foregroundStyle(DearlyTheme.forest)
                GardenIllustration(stage: 3).frame(height: 270).clipShape(RoundedRectangle(cornerRadius: 32))
                Text(L("A place where\nyou feel heard."))
                    .font(.system(size: 39, weight: .regular, design: .serif)).tracking(-1)
                Text(L("Write what you haven’t been able to share. Find someone willing to listen. Grow a little garden together."))
                    .font(.body).lineSpacing(5).foregroundStyle(DearlyTheme.muted)
                HStack(alignment: .top, spacing: 10) {
                    Image(systemName: "lock.shield")
                    Text(L("Your journal is private by default. Sharing, taking a break, or leaving a connection is always your choice."))
                }.font(.footnote).foregroundStyle(DearlyTheme.forest)
                PrimaryButton(title: L("Find a softer moment"), action: start)
                Text(L("Log in or create an account to connect. Dearly is a space for companionship, not a therapy service."))
                    .font(.caption).foregroundStyle(DearlyTheme.muted).lineSpacing(3)
            }.padding(28)
        }.background(DearlyTheme.cream).foregroundStyle(DearlyTheme.ink)
    }
}

@MainActor
struct AccountSettingsView: View {
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
                if store.isOnline {
                    Section(L("Your account")) {
                        LabeledContent(L("Nickname"), value: store.me.nickname)
                        LabeledContent(L("Role"), value: store.role.title)
                        LabeledContent("Server", value: store.serverAddress)
                        LabeledContent(L("Age"), value: store.me.ageVerified ? L("Verified") : L("Awaiting administrator verification"))
                        if let date = store.lastSync { LabeledContent(L("Last synced"), value: date.formatted(Date.FormatStyle(date: .omitted, time: .shortened).locale(Locale(identifier: language)))) }
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
                        Text(L("The server manages permissions and daily check-ins (UTC). Messages sync about every 3 seconds while the app is open. Your data is saved on the server.")).font(.caption)
                    }
                }
            }.navigationTitle(L("Dearly settings")).navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .confirmationAction) { Button(L("Done")) { dismiss() } } }
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
    @AppStorage("dearly.language") private var language = "en"
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
                .background(DearlyTheme.surface.opacity(0.7), in: Capsule())
                .overlay(Capsule().stroke(DearlyTheme.border, lineWidth: 1))
        }.accessibilityLabel(L("Language"))
    }
}

@MainActor
struct LanguagePicker: View {
    @AppStorage("dearly.language") private var language = "en"
    var body: some View {
        Picker(L("Language"), selection: $language) {
            Text(verbatim: "English").tag("en")
            Text(verbatim: "Tiếng Việt").tag("vi")
        }
    }
}

enum AppAppearance: String, CaseIterable {
    case system, light, dark
    var colorScheme: ColorScheme? {
        switch self {
        case .system: return nil
        case .light: return .light
        case .dark: return .dark
        }
    }
    var title: String {
        switch self {
        case .system: return L("System")
        case .light: return L("Light")
        case .dark: return L("Dark")
        }
    }
}

@MainActor
struct AppearancePicker: View {
    @AppStorage("dearly.language") private var language = "en"
    @AppStorage("dearly.appearance") private var appearance = AppAppearance.system.rawValue
    var body: some View {
        Picker(L("Appearance"), selection: $appearance) {
            ForEach(AppAppearance.allCases, id: \.rawValue) { Text($0.title).tag($0.rawValue) }
        }
    }
}

@MainActor
struct AppearanceMenu: View {
    var body: some View {
        Menu { AppearancePicker() } label: {
            Image(systemName: "circle.lefthalf.filled")
                .foregroundStyle(DearlyTheme.forest).padding(11)
                .background(DearlyTheme.surface, in: Circle())
        }.accessibilityLabel(L("Appearance"))
    }
}
