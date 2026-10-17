import SwiftUI
import UniformTypeIdentifiers

@MainActor
struct EncryptionNoticeView: View {
    @ObservedObject var vault: EncryptionVault
    var openSettings: () -> Void
    var body: some View {
        if vault.needsBackup || vault.status == "locked" {
            Button(action: openSettings) {
                Label(L(vault.status == "locked" ? "Unlock your encrypted journal and chat with your recovery code." : "Save your recovery code to open encrypted content on another device."), systemImage: "key")
                    .font(.caption).multilineTextAlignment(.leading).frame(maxWidth: .infinity, alignment: .leading).padding(12)
            }.foregroundStyle(DearlyTheme.forest).background(DearlyTheme.surface)
        }
    }
}

enum PrivacyAction: String, Identifiable { case export, delete; var id: String { rawValue } }

@MainActor
struct PrivacySettingsView: View {
    @EnvironmentObject private var store: DearlyStore
    @ObservedObject var vault: EncryptionVault
    @Environment(\.scenePhase) private var scenePhase
    @State private var code = ""
    @State private var recovery = ""
    @State private var partnerFingerprint = ""
    @State private var action: PrivacyAction?
    @State private var error: String?
    @State private var busy = false
    var body: some View {
        Form {
            Section(L("Encryption & recovery")) {
                Text(L("New journal text, private titles, companion passages and messages are encrypted on your device. Community passages are public. Older content stays as it was until you edit and save it."))
                    .font(.footnote)
                if vault.status == "ready" {
                    Label(L("Encryption ready"), systemImage: "checkmark.shield")
                    Text(L("Keep your recovery code somewhere safe. You need it on a new browser or iPhone. Dearly cannot recover it for you.")).font(.caption)
                    if code.isEmpty {
                        Button(L("Show recovery code")) { do { code = try vault.recoveryCode() } catch { self.error = error.localizedDescription } }
                    } else {
                        Text(code).font(.caption.monospaced()).textSelection(.enabled).privacySensitive()
                        Button(L("I saved my recovery code")) {
                            do { try vault.markBackedUp(); code = "" } catch { self.error = error.localizedDescription }
                        }
                        Button(L("Hide")) { code = "" }
                    }
                } else if vault.status == "locked" {
                    Text(L("This device needs your recovery code. Your account can still use community features while encryption is locked."))
                    SecureField(L("Recovery code"), text: $recovery).textInputAutocapitalization(.never).autocorrectionDisabled().privacySensitive()
                    Button(L("Unlock encryption")) {
                        do { try vault.recover(recovery); recovery = ""; Task { await store.refresh(force: true) } }
                        catch { self.error = error.localizedDescription }
                    }
                } else {
                    Text(vault.error.isEmpty ? L("Preparing encryption…") : vault.error)
                    Button(L("Try again")) { Task { busy = true; await store.retryEncryption(); busy = false } }.disabled(busy || vault.status == "loading")
                }
            }
            if !vault.fingerprint.isEmpty {
                Section(L("Verify encryption keys")) {
                    Text(L("Compare these fingerprints with your companion through another trusted channel. A match helps confirm who holds the keys.")).font(.caption)
                    LabeledContent(L("Your fingerprint")) { Text(vault.fingerprint).font(.caption.monospaced()).textSelection(.enabled) }
                    if let partner = store.partner {
                        Button(L("Show companion fingerprint")) {
                            Task {
                                do { partnerFingerprint = try await vault.peer(partner.id).fingerprint }
                                catch { self.error = error.localizedDescription }
                            }
                        }
                        if !partnerFingerprint.isEmpty { Text(partnerFingerprint).font(.caption.monospaced()).textSelection(.enabled) }
                    }
                }
            }
            Section(L("Your data")) {
                Text(L("Download the content you created and your account details, or permanently delete your account. Both require your current password.")).font(.footnote)
                Button(L("Download my data"), systemImage: "arrow.down.document") { action = .export }
                Button(L("Delete my account"), role: .destructive) { action = .delete }
            }
            if let error { Section { Text(error).foregroundStyle(.red) } }
        }.navigationTitle(L("Privacy & data")).navigationBarTitleDisplayMode(.inline)
            .sheet(item: $action) { PrivacyActionView(action: $0, encryptionReady: vault.status == "ready") }
            .onDisappear { code = ""; recovery = "" }
            .onChange(of: scenePhase) { _, phase in if phase != .active { code = ""; recovery = "" } }
    }
}

struct PrivacyExportDocument: FileDocument {
    static var readableContentTypes: [UTType] { [.json] }
    var data: Data
    init(data: Data) { self.data = data }
    init(configuration: ReadConfiguration) throws { data = configuration.file.regularFileContents ?? Data() }
    func fileWrapper(configuration: WriteConfiguration) throws -> FileWrapper { FileWrapper(regularFileWithContents: data) }
}

@MainActor
struct PrivacyActionView: View {
    var action: PrivacyAction
    var encryptionReady: Bool
    @EnvironmentObject private var store: DearlyStore
    @Environment(\.dismiss) private var dismiss
    @State private var password = ""
    @State private var confirmation = ""
    @State private var decrypt = true
    @State private var busy = false
    @State private var error: String?
    @State private var document: PrivacyExportDocument?
    @State private var exporting = false
    var body: some View {
        NavigationStack {
            Form {
                Section {
                    Text(L(action == .export ? "Your file includes your profile, authored content and connection history. Keep it somewhere private." : "Your profile, journals, sent messages and encryption keys will be removed. All sessions will end. This cannot be undone. A deleted-account marker remains in shared garden history."))
                    SecureField(L("Current password"), text: $password).textContentType(.password).privacySensitive()
                    if action == .delete {
                        TextField(L("Type DELETE to confirm"), text: $confirmation).textInputAutocapitalization(.characters).autocorrectionDisabled()
                    } else {
                        Toggle(L("Decrypt content on this device"), isOn: $decrypt).disabled(!encryptionReady)
                        Text(L(decrypt && encryptionReady ? "The downloaded file will contain readable private text. Encrypted originals are also included." : "Encrypted text stays encrypted in the download. Keep your recovery code to read it later.")).font(.caption)
                    }
                }
                if let error { Section { Text(error).foregroundStyle(.red) } }
                Section {
                    Button(L(action == .delete ? "Permanently delete" : "Download data"), role: action == .delete ? .destructive : nil) {
                        Task { await submit() }
                    }.disabled(busy || store.isBusy || password.count < 10 || (action == .delete && confirmation != "DELETE"))
                    if busy { ProgressView() }
                }
            }.navigationTitle(L(action == .export ? "Download your data" : "Permanently delete your account?"))
                .navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .cancellationAction) { Button(L("Cancel")) { password = ""; dismiss() }.disabled(busy) } }
                .interactiveDismissDisabled(busy)
                .fileExporter(isPresented: $exporting, document: document, contentType: .json, defaultFilename: "dearly-data") { result in
                    document = nil
                    if case .failure(let error) = result { self.error = error.localizedDescription }
                    else { dismiss() }
                }
                .onAppear { decrypt = encryptionReady }
        }
    }
    private func submit() async {
        busy = true; error = nil
        defer { busy = false }
        if action == .delete {
            if await store.deleteAccount(password: password, confirmation: confirmation) { password = ""; dismiss() }
            else { error = store.errorMessage }
        } else {
            do {
                let data = try await store.downloadData(password: password, decrypt: decrypt && encryptionReady)
                password = ""; document = PrivacyExportDocument(data: data); exporting = true
            } catch { self.error = error.localizedDescription }
        }
    }
}
