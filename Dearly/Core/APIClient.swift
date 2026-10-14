import Foundation
import Security

struct ServerSession: Codable {
    var baseURL: String
    var token: String
    var userID: UUID
}

enum SessionKeychain {
    private static let service = "com.dearly.server-session"
    static func save(_ session: ServerSession) throws {
        let data = try JSONEncoder().encode(session)
        let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword,
                                   kSecAttrService as String: service, kSecAttrAccount as String: "current"]
        let status = SecItemUpdate(query as CFDictionary, [kSecValueData as String: data] as CFDictionary)
        if status == errSecItemNotFound {
            var item = query
            item[kSecValueData as String] = data
            item[kSecAttrAccessible as String] = kSecAttrAccessibleWhenUnlockedThisDeviceOnly
            guard SecItemAdd(item as CFDictionary, nil) == errSecSuccess else { throw DearlyError.invalid(L("Không lưu được phiên trong Keychain.")) }
        } else if status != errSecSuccess { throw DearlyError.invalid(L("Không cập nhật được Keychain.")) }
    }
    static func load() -> ServerSession? {
        let query: [String: Any] = [kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service,
                                   kSecAttrAccount as String: "current", kSecReturnData as String: true, kSecMatchLimit as String: kSecMatchLimitOne]
        var result: CFTypeRef?
        guard SecItemCopyMatching(query as CFDictionary, &result) == errSecSuccess, let data = result as? Data else { return nil }
        return try? JSONDecoder().decode(ServerSession.self, from: data)
    }
    static func clear() {
        SecItemDelete([kSecClass as String: kSecClassGenericPassword, kSecAttrService as String: service,
                       kSecAttrAccount as String: "current"] as CFDictionary)
    }
}

struct CommandPayload: Encodable {
    var id: UUID? = nil
    var title: String? = nil
    var body: String? = nil
    var sharedText: String? = nil
    var audience: String? = nil
    var anonymous: Bool? = nil
    var commentsEnabled: Bool? = nil
    var support: String? = nil
    var userID: UUID? = nil
    var journalID: UUID? = nil
    var connectionID: UUID? = nil
    var text: String? = nil
    var enabled: Bool? = nil
    var paused: Bool? = nil
    var reason: String? = nil
    var nickname: String? = nil
    var bio: String? = nil
    var interests: [String]? = nil
    var pace: String? = nil
}

struct StateEnvelope: Decodable {
    var state: AppState
    var serverNow: Date
}

struct MessagePage: Decodable {
    var items: [ChatMessage]
    var nextCursor: UUID?
}

struct JournalPage: Decodable {
    var items: [Journal]
    var nextCursor: UUID?
}

struct APIError: LocalizedError {
    var status: Int
    var message: String
    var errorDescription: String? { L(message) }
}

private final class NoRedirectDelegate: NSObject, URLSessionTaskDelegate, @unchecked Sendable {
    func urlSession(_ session: URLSession, task: URLSessionTask,
                    willPerformHTTPRedirection response: HTTPURLResponse, newRequest request: URLRequest,
                    completionHandler: @escaping (URLRequest?) -> Void) {
        completionHandler(nil) // Never forward an Authorization header to a redirected origin.
    }
}

actor APIClient {
    let baseURL: URL
    private let token: String?
    private let session: URLSession
    private let delegate: NoRedirectDelegate

    static func validatedURL(_ value: String) throws -> URL {
        guard let url = URL(string: value.trimmingCharacters(in: .whitespacesAndNewlines)),
              let host = url.host?.lowercased(), url.user == nil, url.password == nil,
              url.query == nil, url.fragment == nil, url.path.isEmpty || url.path == "/" else {
            throw DearlyError.invalid(L("Nhập địa chỉ gốc, ví dụ https://dearly.example.com hoặc http://192.168.1.10:8000 khi phát triển."))
        }
        if url.scheme == "https" { return url }
        #if DEBUG
        let parts = host.split(separator: ".").compactMap { Int($0) }
        let privateIP = host.split(separator: ".").count == 4 && parts.count == 4 && parts.allSatisfy { (0...255).contains($0) } &&
            (parts[0] == 10 || parts[0] == 127 || (parts[0] == 192 && parts[1] == 168) ||
             (parts[0] == 172 && (16...31).contains(parts[1])))
        if url.scheme == "http" && (privateIP || host == "localhost" || (host == "[::1]" || host == "::1") || host.hasSuffix(".local")) { return url }
        #endif
        throw DearlyError.invalid(L("Cần HTTPS. Bản Debug chỉ cho phép HTTP tới localhost hoặc mạng LAN riêng."))
    }

    init(baseURL: URL, token: String? = nil) {
        self.baseURL = baseURL; self.token = token
        let configuration = URLSessionConfiguration.ephemeral
        configuration.timeoutIntervalForRequest = 15
        configuration.timeoutIntervalForResource = 30
        configuration.requestCachePolicy = .reloadIgnoringLocalCacheData
        configuration.urlCache = nil
        configuration.httpMaximumConnectionsPerHost = 4
        configuration.waitsForConnectivity = false
        let delegate = NoRedirectDelegate()
        self.delegate = delegate
        session = URLSession(configuration: configuration, delegate: delegate, delegateQueue: nil)
    }

    deinit { session.invalidateAndCancel() }

    func authenticate(username: String, password: String, nickname: String?, birthDate: String?) async throws -> ServerSession {
        struct Input: Encodable { var username: String; var password: String; var nickname: String?; var birthDate: String? }
        struct Output: Decodable { var token: String; var userID: UUID }
        let input = Input(username: username, password: password, nickname: nickname, birthDate: birthDate)
        let (data, _) = try await request(path: nickname == nil ? "v1/auth/login" : "v1/auth/register", method: "POST", body: JSONEncoder().encode(input))
        let result = try JSONDecoder().decode(Output.self, from: data)
        return ServerSession(baseURL: baseURL.absoluteString, token: result.token, userID: result.userID)
    }

    func fetchState(etag: String?) async throws -> (StateEnvelope?, String?) {
        let (data, response) = try await request(path: "v1/state", etag: etag)
        if response.statusCode == 304 { return (nil, etag) }
        return (try JSONDecoder().decode(StateEnvelope.self, from: data), response.value(forHTTPHeaderField: "ETag"))
    }

    func command(kind: String, payload: CommandPayload) async throws {
        struct Action: Encodable { var requestID: UUID; var kind: String; var payload: CommandPayload }
        // One idempotency key across the automatic retry; the server atomically records the result.
        let body = try JSONEncoder().encode(Action(requestID: UUID(), kind: kind, payload: payload))
        do { _ = try await request(path: "v1/actions", method: "POST", body: body) }
        catch {
            let transient = (error as? URLError).map { [.timedOut, .networkConnectionLost].contains($0.code) } ?? false
            guard transient || (error as? APIError)?.status == 503 else { throw error }
            try await Task.sleep(nanoseconds: 500_000_000)
            _ = try await request(path: "v1/actions", method: "POST", body: body)
        }
    }

    func messages(connectionID: UUID, before: UUID?) async throws -> MessagePage {
        var query = [URLQueryItem(name: "connectionID", value: connectionID.uuidString), URLQueryItem(name: "limit", value: "50")]
        if let before { query.append(URLQueryItem(name: "before", value: before.uuidString)) }
        let (data, _) = try await request(path: "v1/messages", query: query)
        return try JSONDecoder().decode(MessagePage.self, from: data)
    }

    func logout() async throws { _ = try await request(path: "v1/auth/logout", method: "POST") }

    func journals(before: UUID?) async throws -> JournalPage {
        var query = [URLQueryItem(name: "limit", value: "40")]
        if let before { query.append(URLQueryItem(name: "before", value: before.uuidString)) }
        let (data, _) = try await request(path: "v1/journals", query: query)
        return try JSONDecoder().decode(JournalPage.self, from: data)
    }

    private func request(path: String, method: String = "GET", body: Data? = nil,
                         etag: String? = nil, query: [URLQueryItem] = []) async throws -> (Data, HTTPURLResponse) {
        var components = URLComponents(url: baseURL.appendingPathComponent(path), resolvingAgainstBaseURL: false)!
        if !query.isEmpty { components.queryItems = query }
        var request = URLRequest(url: components.url!)
        request.httpMethod = method; request.httpBody = body
        request.setValue("application/json", forHTTPHeaderField: "Accept")
        if body != nil { request.setValue("application/json", forHTTPHeaderField: "Content-Type") }
        if let token { request.setValue("Bearer \(token)", forHTTPHeaderField: "Authorization") }
        if let etag { request.setValue(etag, forHTTPHeaderField: "If-None-Match") }
        let (data, response) = try await session.data(for: request)
        guard let http = response as? HTTPURLResponse else { throw DearlyError.invalid(L("Server trả về phản hồi không hợp lệ.")) }
        guard (200...299).contains(http.statusCode) || http.statusCode == 304 else {
            let value = try? JSONSerialization.jsonObject(with: data) as? [String: Any]
            throw APIError(status: http.statusCode, message: value?["detail"] as? String ?? L("Server báo lỗi \(http.statusCode). Kiểm tra thông tin và thử lại.", "Server error \(http.statusCode). Check your details and try again."))
        }
        return (data, http)
    }
}
