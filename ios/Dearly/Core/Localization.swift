import Foundation

enum AppLanguage {
    static var code: String { UserDefaults.standard.string(forKey: "dearly.language") == "vi" ? "vi" : "en" }
    static var bundle: Bundle {
        guard let path = Bundle.main.path(forResource: code, ofType: "lproj"),
              let bundle = Bundle(path: path) else { return .main }
        return bundle
    }
}

func L(_ key: String) -> String {
    AppLanguage.bundle.localizedString(forKey: key, value: key, table: nil)
}

// Positional placeholders allow translated word order while keeping user content verbatim.
func LF(_ key: String, _ arguments: String...) -> String {
    String(format: L(key), locale: Locale(identifier: AppLanguage.code),
           arguments: arguments.map { $0 as CVarArg })
}
