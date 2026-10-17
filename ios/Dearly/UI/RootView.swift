import SwiftUI

@MainActor
struct RootView: View {
    @AppStorage("dearly.language") private var language = "en"
    @EnvironmentObject private var store: DearlyStore
    @State private var tab = 0
    @StateObject private var guide = GuideProgress()
    @State private var replayGuide = false
    @State private var showSettings = false
    @Environment(\.scenePhase) private var scenePhase
    var body: some View {
        Group {
            if store.isOnline {
                tabs
                    .allowsHitTesting(!guide.isPresented)
                    .accessibilityHidden(guide.isPresented)
            } else {
                ServerConnectionView()
            }
        }
        .environmentObject(guide)
        .environment(\.locale, Locale(identifier: AppLanguage.code))
        .overlay {
            GeometryReader { container in
                if store.isOnline, guide.isPresented {
                    GuidedTourOverlay(guide: guide, insets: container.safeAreaInsets).ignoresSafeArea()
                }
            }
        }
        .onChange(of: store.isOnline, initial: true) { _, _ in configureGuide() }
        .onChange(of: store.state.currentUserID) { _, _ in configureGuide() }
        .onChange(of: store.serverAddress) { _, _ in configureGuide() }
        .onChange(of: guide.currentStep) { _, step in if let step { tab = step.tab } }
        .task { await store.syncLoop() }
        .onChange(of: scenePhase) { _, phase in store.foreground = phase == .active }
    }

    private func configureGuide() {
        guide.configure(server: store.isOnline ? store.serverAddress : nil,
                        userID: store.isOnline ? store.me.id : nil)
    }

    private var tabs: some View {
        TabView(selection: $tab) {
            page(0) { JournalView() }.tabItem { Label(L("Journal"), systemImage: "book.closed") }.tag(0)
            page(1) { CommunityView() }.tabItem { Label(L("Community"), systemImage: "bubble.left.and.bubble.right") }.tag(1)
            page(2) { CompanionView() }.tabItem { Label(L("Companion"), systemImage: "person.2") }.tag(2)
            page(3) { GardenView() }.tabItem { Label(L("Garden"), systemImage: "leaf") }.tag(3)
        }
        .id(store.me.id)
        .disabled(store.isBusy || store.isAuthenticating)
        .sheet(isPresented: $showSettings, onDismiss: {
            if replayGuide { replayGuide = false; guide.start() }
        }) {
            AccountSettingsView { replayGuide = true; showSettings = false }
        }
        .alert("Dearly", isPresented: Binding(get: { store.errorMessage != nil }, set: { if !$0 { store.errorMessage = nil } })) {
            Button(L("Got it")) { store.errorMessage = nil }
        } message: { Text(store.errorMessage ?? "") }
        .alert(L("Received"), isPresented: Binding(get: { store.notice != nil }, set: { if !$0 { store.notice = nil } })) {
            Button(L("Close")) { store.notice = nil }
        } message: { Text(store.notice ?? "") }
    }

    private func page<Content: View>(_ index: Int, @ViewBuilder content: () -> Content) -> some View {
        NavigationStack {
            content()
                .safeAreaInset(edge: .top, spacing: 0) {
                    VStack(spacing: 0) {
                        EncryptionNoticeView(vault: store.encryption) { showSettings = true }
                        if store.isOnline {
                            HStack(spacing: 7) {
                                Image(systemName: store.syncError == nil ? "network" : "wifi.exclamationmark")
                                Text(store.syncError == nil ? LF("Connected · %1$@", String(describing: store.me.nickname)) : L("Sync interrupted · Reconnecting automatically"))
                                Spacer()
                                if store.isBusy { ProgressView().controlSize(.small) }
                            }.font(.caption2).foregroundStyle(DearlyTheme.forest).padding(.horizontal, 22).padding(.vertical, 7).background(DearlyTheme.sage.opacity(0.6))
                        }
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
                                Text(L("ONLINE")).font(.system(size: 9, weight: .bold)).tracking(1)
                                Avatar(symbol: store.me.symbol, size: 32)
                            }
                        }.guideTarget(.settings, enabled: tab == index).accessibilityLabel(LF("Account settings for %1$@", String(describing: store.me.nickname)))
                    }
                }
                .toolbarBackground(DearlyTheme.cream, for: .navigationBar, .tabBar)
                .toolbarBackground(.visible, for: .navigationBar, .tabBar)
        }
    }
}

