import Foundation
import Combine
import CoreGraphics

/// Stable IDs also identify the real controls highlighted by the guide.
enum GuideStep: String, CaseIterable, Identifiable {
    case compose, pages, community, companion, garden, settings
    var id: String { rawValue }
    var tab: Int {
        switch self {
        case .compose, .pages: return 0
        case .community: return 1
        case .companion: return 2
        case .garden, .settings: return 3
        }
    }
    var title: String {
        switch self {
        case .compose: return "A page of your own"
        case .pages: return "Find your pages"
        case .community: return "Listen with kindness"
        case .companion: return "A connection takes two"
        case .garden: return "Grow a little together"
        case .settings: return "Make Dearly feel like you"
        }
    }
    var detail: String {
        switch self {
        case .compose: return "Start a journal entry here. It begins private. In the editor, you choose whether to share a passage with your companion or the community."
        case .pages: return "Your pages stay in your journal. Open an entry to edit it, or browse earlier pages whenever you need them."
        case .community: return "Explore shared passages and the kind of support each writer wants. Anonymous stories hide the nickname; the rest of a private entry stays private."
        case .companion: return "Companion matching requires verified ages and an accepted invitation. Both people choose to connect before their private chat opens."
        case .garden: return "Once you have a companion, check in on the same UTC day to grow your garden. You can pause when you need a break and keep your earned rewards."
        case .settings: return "Open account settings for your profile, language and appearance. Choose Take a guided tour there whenever you want another look."
        }
    }
}

@MainActor
final class GuideProgress: ObservableObject {
    enum Phase: Hashable { case welcome, step(GuideStep) }
    struct TargetFrame { var rect: CGRect; var owner: UUID }
    @Published private(set) var phase: Phase?
    @Published private(set) var frames: [GuideStep: TargetFrame] = [:]
    private let defaults: UserDefaults
    private var accountKey: String?
    var isPresented: Bool { phase != nil }
    var currentStep: GuideStep? {
        if case let .step(step)? = phase { return step }
        return nil
    }
    var index: Int { currentStep.flatMap { GuideStep.allCases.firstIndex(of: $0) } ?? 0 }

    init(defaults: UserDefaults = .standard) { self.defaults = defaults }

    static func storageKey(server: String, userID: UUID) -> String {
        let origin = server.lowercased().trimmingCharacters(in: CharacterSet(charactersIn: "/"))
        return "dearly.guide.v1:\(origin):\(userID.uuidString)"
    }

    func configure(server: String?, userID: UUID?) {
        let key = server.flatMap { origin in userID.map { Self.storageKey(server: origin, userID: $0) } }
        guard key != accountKey else { return }
        accountKey = key
        frames.removeAll()
        if let key, !defaults.bool(forKey: key) { phase = .welcome }
        else { phase = nil }
    }

    func start() {
        guard accountKey != nil else { return }
        frames.removeAll(); phase = .step(.compose)
    }
    func advance() {
        guard let currentStep else { start(); return }
        if let next = GuideStep.allCases.dropFirst(index + 1).first {
            frames.removeAll(); phase = .step(next)
        } else if currentStep == .settings { dismiss() }
    }
    func back() {
        guard currentStep != nil, index > 0 else { return }
        let previous = GuideStep.allCases[index - 1]
        frames.removeAll(); phase = .step(previous)
    }
    func dismiss() {
        if let accountKey { defaults.set(true, forKey: accountKey) }
        phase = nil; frames.removeAll()
    }
    func record(_ step: GuideStep, rect: CGRect, owner: UUID) {
        guard currentStep == step, !rect.isEmpty, !rect.isInfinite, !rect.isNull else { return }
        if frames[step]?.rect != rect || frames[step]?.owner != owner { frames[step] = TargetFrame(rect: rect, owner: owner) }
    }
    func remove(_ step: GuideStep, owner: UUID) {
        if frames[step]?.owner == owner { frames.removeValue(forKey: step) }
    }
}

/// Keeps instructions inside the usable screen and beside the highlighted control when space permits.
enum GuideLayout {
    static func spotlight(_ target: CGRect, in viewport: CGRect) -> CGRect? {
        let clipped = target.insetBy(dx: -7, dy: -7).intersection(viewport.insetBy(dx: 4, dy: 4))
        return clipped.isNull || clipped.isEmpty ? nil : clipped
    }
    static func maxHeight(target: CGRect?, available: CGRect) -> CGFloat {
        guard let target else { return available.height }
        let above = target.minY - 16 - available.minY
        let below = available.maxY - target.maxY - 16
        return min(available.height, max(220, max(above, below)))
    }
    static func origin(target: CGRect?, card: CGSize, available: CGRect) -> CGPoint {
        var x = available.midX - card.width / 2
        var y = available.midY - card.height / 2
        if let target {
            x = target.midX - card.width / 2
            let above = target.minY - 16 - available.minY
            let below = available.maxY - target.maxY - 16
            if below >= card.height { y = target.maxY + 16 }
            else if above >= card.height { y = target.minY - 16 - card.height }
            else { y = below >= above ? available.maxY - card.height : available.minY }
        }
        return CGPoint(x: max(available.minX, min(x, available.maxX - card.width)),
                       y: max(available.minY, min(y, available.maxY - card.height)))
    }
}
