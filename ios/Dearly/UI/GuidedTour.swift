import SwiftUI

/// Measures global frames directly so toolbar controls can participate too.
@MainActor
private struct GuideTargetModifier: ViewModifier {
    @EnvironmentObject private var guide: GuideProgress
    @State private var owner = UUID()
    var step: GuideStep
    var enabled: Bool

    func body(content: Content) -> some View {
        content.background {
            GeometryReader { proxy in
                Color.clear
                    .onAppear { record(proxy) }
                    .onChange(of: proxy.frame(in: .global)) { _, _ in record(proxy) }
                    .onChange(of: guide.currentStep) { _, _ in record(proxy) }
                    .onChange(of: enabled) { _, _ in record(proxy) }
                    .onDisappear { guide.remove(step, owner: owner) }
            }
        }.id(enabled ? AnyHashable(step) : AnyHashable(owner))
    }

    private func record(_ proxy: GeometryProxy) {
        if enabled { guide.record(step, rect: proxy.frame(in: .global), owner: owner) }
        else { guide.remove(step, owner: owner) }
    }
}

extension View {
    func guideTarget(_ step: GuideStep, enabled: Bool = true) -> some View {
        modifier(GuideTargetModifier(step: step, enabled: enabled))
    }
}

/// Scrolls the relevant real control into view without invoking its action.
@MainActor
struct GuideScrollView<Content: View>: View {
    @EnvironmentObject private var guide: GuideProgress
    private let content: Content
    init(@ViewBuilder content: () -> Content) { self.content = content() }
    var body: some View {
        ScrollViewReader { reader in
            ScrollView { content }
                .task(id: guide.currentStep) {
                    guard let step = guide.currentStep else { return }
                    await Task.yield()
                    guard !Task.isCancelled else { return }
                    reader.scrollTo(step, anchor: .top)
                }
        }
    }
}

private struct GuideShade: Shape {
    var target: CGRect?
    func path(in rect: CGRect) -> Path {
        var path = Path(rect)
        if let target { path.addRoundedRect(in: target, cornerSize: CGSize(width: 13, height: 13)) }
        return path
    }
}

@MainActor
struct GuidedTourOverlay: View {
    @ObservedObject var guide: GuideProgress
    var insets: EdgeInsets
    @State private var cardHeight: CGFloat = 280

    var body: some View {
        GeometryReader { proxy in
            let viewport = CGRect(origin: .zero, size: proxy.size)
            let global = proxy.frame(in: .global)
            let measured = guide.currentStep.flatMap { guide.frames[$0]?.rect }
            let target = measured.flatMap { GuideLayout.spotlight($0.offsetBy(dx: -global.minX, dy: -global.minY), in: viewport) }
            let available = CGRect(x: insets.leading + 16, y: insets.top + 16,
                                   width: max(0, proxy.size.width - insets.leading - insets.trailing - 32),
                                   height: max(0, proxy.size.height - insets.top - insets.bottom - 32))
            let width = min(380, available.width)
            let limit = GuideLayout.maxHeight(target: target, available: available)
            let size = CGSize(width: width, height: min(cardHeight, limit))
            let origin = GuideLayout.origin(target: target, card: size, available: available)
            ZStack(alignment: .topLeading) {
                GuideShade(target: target)
                    .fill(.black.opacity(0.62), style: FillStyle(eoFill: true))
                    .contentShape(Rectangle()).onTapGesture { }
                    .accessibilityHidden(true)
                if let target {
                    RoundedRectangle(cornerRadius: 13)
                        .stroke(DearlyTheme.forest, lineWidth: 2)
                        .frame(width: target.width, height: target.height)
                        .position(x: target.midX, y: target.midY)
                        .allowsHitTesting(false).accessibilityHidden(true)
                }
                GuideCard(guide: guide, compact: limit < 300)
                    .frame(width: width)
                    .frame(maxHeight: limit)
                    .background {
                        GeometryReader { card in
                            Color.clear.onAppear { cardHeight = card.size.height }
                                .onChange(of: card.size.height) { _, height in
                                    if abs(cardHeight - height) > 1 { cardHeight = height }
                                }
                        }
                    }
                    .position(x: origin.x + width / 2, y: origin.y + size.height / 2)
            }.frame(width: proxy.size.width, height: proxy.size.height)
        }
        .accessibilityElement(children: .contain)
        .accessibilityAddTraits(.isModal)
        .accessibilityAction(.escape) { guide.dismiss() }
    }
}

@MainActor
private struct GuideCard: View {
    @ObservedObject var guide: GuideProgress
    var compact: Bool
    @AppStorage("dearly.language") private var language = "en"
    @AccessibilityFocusState private var focused: Bool

    private var instructions: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text(L(guide.currentStep?.title ?? "A little guide to Dearly"))
                .font(.system(size: 25, design: .serif)).foregroundStyle(DearlyTheme.ink)
                .accessibilityAddTraits(.isHeader).accessibilityFocused($focused)
            Text(L(guide.currentStep?.detail ?? "Explore the main features at your own pace. You can skip the guide and open it again from Settings."))
                .font(.subheadline).foregroundStyle(DearlyTheme.muted).lineSpacing(4)
        }.fixedSize(horizontal: false, vertical: true)
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 18) {
            if guide.currentStep != nil {
                HStack {
                    Text(LF("Step %1$@ of %2$@", String(guide.index + 1), String(GuideStep.allCases.count)))
                        .font(.caption).foregroundStyle(DearlyTheme.muted)
                    Spacer()
                    Button(L("Skip guide")) { guide.dismiss() }
                        .font(.caption).frame(minHeight: 44)
                }
            } else if !compact {
                Image(systemName: "leaf").font(.title2)
                    .foregroundStyle(DearlyTheme.forest).frame(width: 49, height: 49)
                    .background(DearlyTheme.sage, in: RoundedRectangle(cornerRadius: 16))
            }
            ViewThatFits(in: .vertical) {
                instructions
                ScrollView { instructions }
            }
            if guide.currentStep != nil {
                HStack {
                    if guide.index > 0 {
                        Button { guide.back() } label: { Label(L("Back"), systemImage: "arrow.left") }
                            .buttonStyle(.bordered).frame(minHeight: 44)
                    }
                    Spacer()
                    Button { guide.advance() } label: {
                        Label(guide.currentStep == .settings ? L("Finish") : L("Next"), systemImage: guide.currentStep == .settings ? "checkmark" : "arrow.right")
                    }.buttonStyle(.borderedProminent).foregroundStyle(DearlyTheme.onAccent).frame(minHeight: 44)
                }.font(.subheadline.weight(.semibold))
            } else {
                VStack(spacing: 10) {
                    PrimaryButton(title: L("Show me around")) { guide.start() }
                    Button(L("Maybe later")) { guide.dismiss() }.font(.subheadline).frame(minHeight: 44).frame(maxWidth: .infinity)
                }
            }
        }
        .padding(22)
        .background(DearlyTheme.surface, in: RoundedRectangle(cornerRadius: 23))
        .overlay(RoundedRectangle(cornerRadius: 23).stroke(DearlyTheme.border, lineWidth: 1))
        .shadow(color: .black.opacity(0.22), radius: 24, y: 12)
        .task(id: guide.phase) { focused = true }
    }
}
