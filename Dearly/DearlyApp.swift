import SwiftUI

@main
@MainActor
struct DearlyApp: App {
    @StateObject private var store = DearlyStore()
    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(store)
                .tint(DearlyTheme.forest)
                .preferredColorScheme(.light)
        }
    }
}
