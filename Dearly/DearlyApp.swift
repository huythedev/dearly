import SwiftUI

@main
@MainActor
struct DearlyApp: App {
    @StateObject private var store = DearlyStore()
    @AppStorage("dearly.appearance") private var appearance = AppAppearance.system.rawValue
    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(store)
                .tint(DearlyTheme.forest)
                .preferredColorScheme((AppAppearance(rawValue: appearance) ?? .system).colorScheme)
        }
    }
}
