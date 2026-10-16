import SwiftUI

@MainActor
struct ServerConnectionView: View {
    @AppStorage("dearly.language") private var language = "en"
    @EnvironmentObject private var store: DearlyStore
    @AppStorage("dearly.server.address") private var address = APIClient.defaultServerAddress
    @State private var registering = false
    @State private var username = ""
    @State private var password = ""
    @State private var nickname = ""
    @State private var birthDate = Calendar.current.date(byAdding: .year, value: -18, to: Date())!
    @State private var failure: String?
    @State private var showingServer = false
    @FocusState private var focusedField: Field?
    private enum Field { case username, nickname, password }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 28) {
                HStack {
                    DearlyBrand()
                    Spacer()
                    AppearanceMenu()
                    LanguageMenu()
                }
                VStack(alignment: .leading, spacing: 12) {
                    GardenIllustration(stage: 2)
                        .frame(height: 160).clipShape(RoundedRectangle(cornerRadius: 28))
                        .accessibilityHidden(true)
                    PageHeading(eyebrow: L("A LITTLE ROOM TO BREATHE"),
                        title: registering ? L("Start with a little seed.") : L("Welcome back."),
                        subtitle: registering ? L("A place to write, feel heard, and grow together.") : L("Your pages and your garden are waiting."))
                }
                VStack(alignment: .leading, spacing: 22) {
                    HStack(spacing: 4) {
                        modeButton("Log in", register: false)
                        modeButton("Sign up", register: true)
                    }.padding(5).background(DearlyTheme.cream, in: Capsule())
                    VStack(alignment: .leading, spacing: 16) {
                        field("Username", symbol: "person") {
                            TextField(L("Username"), text: $username)
                                .textContentType(.username).textInputAutocapitalization(.never).autocorrectionDisabled()
                                .focused($focusedField, equals: .username).submitLabel(.next)
                                .onSubmit { focusedField = registering ? .nickname : .password }
                        }
                        if registering {
                            field("What should we call you?", symbol: "leaf") {
                                TextField(L("Nickname"), text: $nickname).textContentType(.nickname)
                                    .focused($focusedField, equals: .nickname).submitLabel(.next)
                                    .onSubmit { focusedField = .password }
                            }
                        }
                        field("Password", symbol: "lock") {
                            SecureField(registering ? L("At least 10 characters") : L("Password"), text: $password)
                                .textContentType(registering ? .newPassword : .password)
                                .focused($focusedField, equals: .password).submitLabel(.go)
                                .onSubmit { if canSubmit { Task { await authenticate() } } }
                        }
                        if registering {
                            DatePicker(L("Date of birth"), selection: $birthDate, in: ...Date(), displayedComponents: .date)
                                .font(.subheadline).tint(DearlyTheme.forest)
                            Text(L("For ages 16 and up. Your birthday stays private. Companion connections unlock after an administrator verifies your age."))
                                .font(.caption).foregroundStyle(DearlyTheme.muted).lineSpacing(3)
                        }
                    }
                    if let message = failure ?? store.errorMessage {
                        Label(message, systemImage: "exclamationmark.circle")
                            .font(.footnote).foregroundStyle(.red).accessibilityIdentifier("auth.error")
                    }
                    Button { Task { await authenticate() } } label: {
                        HStack {
                            Text(store.isAuthenticating ? L("Connecting…") : (registering ? L("Create account") : L("Log in")))
                                .font(.subheadline.weight(.semibold))
                            Spacer()
                            if store.isAuthenticating { ProgressView().tint(DearlyTheme.onAccent) }
                            else { Image(systemName: "arrow.right") }
                        }.padding(18).foregroundStyle(DearlyTheme.onAccent)
                            .background(DearlyTheme.forest, in: RoundedRectangle(cornerRadius: 18))
                    }.buttonStyle(.plain).disabled(!canSubmit).opacity(canSubmit || store.isAuthenticating ? 1 : 0.55)
                        .accessibilityIdentifier("auth.submit")
                    Label(L("Private from your very first page."), systemImage: "lock.shield")
                        .font(.caption).foregroundStyle(DearlyTheme.muted)
                        .frame(maxWidth: .infinity)
                }.padding(22).dearlyCard().disabled(store.isAuthenticating)
                DisclosureGroup(isExpanded: $showingServer) {
                    VStack(alignment: .leading, spacing: 12) {
                        TextField(APIClient.defaultServerAddress, text: $address)
                            .keyboardType(.URL).textInputAutocapitalization(.never).autocorrectionDisabled()
                            .padding(14).background(DearlyTheme.surface.opacity(0.8), in: RoundedRectangle(cornerRadius: 14))
                        Text(L("Simulator: localhost. iPhone: use your server’s IP address on the same Wi-Fi. HTTP is available in Debug builds only."))
                            .font(.caption).foregroundStyle(DearlyTheme.muted)
                    }.padding(.top, 12)
                } label: {
                    Label(L("Server connection"), systemImage: "network").font(.footnote.weight(.medium))
                }.tint(DearlyTheme.forest).disabled(store.isAuthenticating)
                Text(L("Dearly is a space for companionship, not a therapy service."))
                    .font(.caption).foregroundStyle(DearlyTheme.muted).multilineTextAlignment(.center)
                    .frame(maxWidth: .infinity)
            }.padding(24).frame(maxWidth: 520).frame(maxWidth: .infinity)
        }
        .scrollDismissesKeyboard(.interactively)
        .background(DearlyTheme.cream.ignoresSafeArea())
        .foregroundStyle(DearlyTheme.ink)
        .onChange(of: registering) { _, _ in failure = nil; store.errorMessage = nil }
    }

    private var canSubmit: Bool {
        !store.isAuthenticating && !username.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty &&
            !password.isEmpty && (!registering || (!nickname.trimmingCharacters(in: .whitespacesAndNewlines).isEmpty && password.count >= 10))
    }

    private func modeButton(_ title: String, register: Bool) -> some View {
        Button { withAnimation(.easeInOut(duration: 0.2)) { registering = register } } label: {
            Text(L(title)).font(.subheadline.weight(.semibold)).frame(maxWidth: .infinity).padding(.vertical, 12)
                .foregroundStyle(registering == register ? DearlyTheme.forest : DearlyTheme.muted)
                .background { if registering == register { Capsule().fill(DearlyTheme.surface).shadow(color: .black.opacity(0.04), radius: 4, y: 2) } }
        }.buttonStyle(.plain).accessibilityAddTraits(registering == register ? .isSelected : [])
    }

    private func field<Content: View>(_ title: String, symbol: String, @ViewBuilder content: () -> Content) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(L(title)).font(.caption.weight(.semibold)).foregroundStyle(DearlyTheme.muted)
            HStack(spacing: 12) {
                Image(systemName: symbol).foregroundStyle(DearlyTheme.muted).frame(width: 18)
                content().font(.subheadline).accessibilityLabel(L(title))
            }.padding(15).background(DearlyTheme.cream.opacity(0.8), in: RoundedRectangle(cornerRadius: 15))
                .overlay(RoundedRectangle(cornerRadius: 15).stroke(DearlyTheme.border, lineWidth: 1))
        }
    }

    private func authenticate() async {
        guard canSubmit else { return }
        focusedField = nil; failure = nil; store.errorMessage = nil
        var calendar = Calendar(identifier: .gregorian)
        calendar.timeZone = .current
        let parts = calendar.dateComponents([.year, .month, .day], from: birthDate)
        let birth = String(format: "%04d-%02d-%02d", parts.year!, parts.month!, parts.day!)
        let ok = await store.authenticate(address: address, username: username.trimmingCharacters(in: .whitespacesAndNewlines),
            password: password, nickname: registering ? nickname.trimmingCharacters(in: .whitespacesAndNewlines) : nil,
            birthDate: registering ? birth : nil)
        if ok { password = "" }
        else { failure = store.errorMessage }
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
