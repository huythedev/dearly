import SwiftUI

@MainActor
struct GardenView: View {
    @AppStorage("dearly.language") private var language = "en"
    @EnvironmentObject private var store: DearlyStore
    @State private var showingArchive = false
    private var archives: [Connection] { store.state.connections.filter { !$0.active && $0.members.contains(store.me.id) } }
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 24) {
                PageHeading(eyebrow: L("GROWING BY SHOWING UP"), title: L("Our little garden."), subtitle: L("There’s no rush. Little things are still growing."))
                if let connection = store.connection {
                    activeGarden(connection)
                } else {
                    GardenIllustration(stage: 0).frame(height: 280).clipShape(RoundedRectangle(cornerRadius: 28))
                    EmptyCard(icon: "leaf", title: L("A seed is waiting"), detail: L("Send an invitation in the Companion tab. When you both accept and check in, your garden begins."))
                }
                if !archives.isEmpty {
                    SectionLabel(title: L("Saved gardens"))
                    ForEach(archives) { connection in
                        VStack(alignment: .leading, spacing: 12) {
                            GardenIllustration(stage: connection.growth).frame(height: 190).clipShape(RoundedRectangle(cornerRadius: 20))
                            Text(LF("With %1$@", String(describing: otherName(connection)))).font(.system(size: 22, design: .serif))
                            Text(LF("%1$@ days connected · Your plants and rewards are still here.", String(describing: connection.totalDays))).font(.caption).foregroundStyle(DearlyTheme.muted)
                        }.padding(16).dearlyCard()
                    }
                }
                Button(L("Browse all saved gardens"), systemImage: "books.vertical") { showingArchive = true }
                    .font(.subheadline)
            }.padding(22).padding(.bottom, 20)
        }
        .sheet(isPresented: $showingArchive) { GardenArchiveView() }
    }

    private func activeGarden(_ connection: Connection) -> some View {
        let checked = connection.checkedIn(store.me.id, on: store.now, calendar: store.calendar)
        let partnerID = connection.members.first { $0 != store.me.id }!
        let partnerChecked = connection.checkedIn(partnerID, on: store.now, calendar: store.calendar)
        return VStack(alignment: .leading, spacing: 23) {
            VStack(spacing: 0) {
                ZStack(alignment: .topLeading) {
                    GardenIllustration(stage: connection.growth).frame(height: 280)
                    Tag(text: connection.paused ? L("RESTING") : "\(store.me.nickname) & \(otherName(connection))", icon: "leaf", color: DearlyTheme.surface.opacity(0.85)).padding(17)
                }.clipShape(RoundedRectangle(cornerRadius: 27))
                HStack {
                    metric("\(connection.streak(on: store.now, calendar: store.calendar))", label: L("days in a row"))
                    Rectangle().fill(DearlyTheme.border).frame(width: 1, height: 36)
                    metric("\(connection.totalDays)", label: L("days connected"))
                    Rectangle().fill(DearlyTheme.border).frame(width: 1, height: 36)
                    metric("\(connection.bestStreak)", label: L("longest streak"))
                }.padding(.vertical, 22)
            }.dearlyCard()
            VStack(alignment: .leading, spacing: 17) {
                SectionLabel(title: L("Today, I’m here"), detail: store.isOnline ? L("Based on UTC") : "")
                statusRow(name: store.me.nickname, checked: checked)
                statusRow(name: otherName(connection), checked: partnerChecked)
                PrimaryButton(title: connection.paused ? L("Your garden is resting") : (checked ? L("You checked in today") : L("I’m still here")), icon: checked ? "checkmark" : "drop") {
                    Task { await store.checkIn() }
                }.disabled(checked || connection.paused).opacity(checked || connection.paused ? 0.65 : 1)
                    .accessibilityIdentifier("garden.checkin")
                Text(checked && partnerChecked ? L("You both showed up. Another day for your garden to grow 🌱") : L("Both of you check in to count a day together. No message quota to meet."))
                    .font(.caption).foregroundStyle(DearlyTheme.muted).lineSpacing(3)
            }
            VStack(alignment: .leading, spacing: 16) {
                SectionLabel(title: L("Little by little"))
                milestone(L("Plant a seed"), detail: L("Your first day connected"), symbol: "circle.dotted", unlocked: connection.totalDays >= 1)
                milestone(L("A little sprout"), detail: L("3 days in a row"), symbol: "leaf", unlocked: connection.bestStreak >= 3)
                milestone(L("The first flowers"), detail: L("7 days in a row"), symbol: "camera.macro", unlocked: connection.bestStreak >= 7)
                milestone(L("A cozy garden corner"), detail: L("14 days in a row"), symbol: "lamp.desk", unlocked: connection.bestStreak >= 14)
                milestone(L("Room for more green"), detail: L("30 days connected in total"), symbol: "tree", unlocked: connection.totalDays >= 30)
            }.padding(22).dearlyCard()
            Button {
                Task { await store.togglePause() }
            } label: {
                Label(connection.paused ? L("Care for your garden again") : L("Let your garden rest"), systemImage: connection.paused ? "play.circle" : "moon")
                    .font(.subheadline).frame(maxWidth: .infinity)
            }
            Text(L("Missing a day won’t take away your plants or rewards. Rest days don’t add to your streak. You can always leave a connection from chat."))
                .font(.caption).foregroundStyle(DearlyTheme.muted).multilineTextAlignment(.center).lineSpacing(3)
        }
    }

    private func otherName(_ connection: Connection) -> String {
        connection.members.first { $0 != store.me.id }.flatMap { store.state.profile($0)?.nickname } ?? L("a friend")
    }
    private func metric(_ value: String, label: String) -> some View {
        VStack(spacing: 5) {
            Text(value).font(.system(size: 28, weight: .regular, design: .serif)).foregroundStyle(DearlyTheme.forest)
            Text(label).font(.system(size: 10)).foregroundStyle(DearlyTheme.muted)
        }.frame(maxWidth: .infinity)
    }
    private func statusRow(name: String, checked: Bool) -> some View {
        HStack {
            Image(systemName: checked ? "checkmark.circle.fill" : "circle.dotted").foregroundStyle(checked ? DearlyTheme.forest : DearlyTheme.muted)
            Text(name).font(.subheadline)
            Spacer()
            Text(checked ? L("Checked in") : L("At your own pace")).font(.caption).foregroundStyle(DearlyTheme.muted)
        }
    }
    private func milestone(_ name: String, detail: String, symbol: String, unlocked: Bool) -> some View {
        HStack(spacing: 14) {
            Image(systemName: symbol).font(.title3).frame(width: 40, height: 40)
                .background(unlocked ? DearlyTheme.sage : DearlyTheme.cream, in: RoundedRectangle(cornerRadius: 12))
            VStack(alignment: .leading, spacing: 4) { Text(name).font(.subheadline.weight(.medium)); Text(detail).font(.caption).foregroundStyle(DearlyTheme.muted) }
            Spacer()
            Image(systemName: unlocked ? "checkmark" : "lock").font(.caption)
        }.foregroundStyle(unlocked ? DearlyTheme.forest : DearlyTheme.muted)
    }
}

@MainActor
private struct GardenArchiveView: View {
    @EnvironmentObject private var store: DearlyStore
    @Environment(\.dismiss) private var dismiss
    @State private var page: ConnectionPage?
    @State private var cursors: [UUID?] = [nil]
    @State private var loading = false
    @State private var failure: String?
    @State private var requestID = UUID()

    var body: some View {
        NavigationStack {
            ScrollView {
                VStack(alignment: .leading, spacing: 18) {
                    if loading { ProgressView() }
                    if let failure { Text(failure).foregroundStyle(.red) }
                    if let page {
                        if page.items.isEmpty && !loading {
                            EmptyCard(icon: "leaf", title: L("No saved gardens yet"), detail: L("Gardens are saved when a connection ends."))
                        }
                        ForEach(page.items) { connection in
                            VStack(alignment: .leading, spacing: 12) {
                                GardenIllustration(stage: connection.growth).frame(height: 190).clipShape(RoundedRectangle(cornerRadius: 20))
                                Text(otherName(connection, profiles: page.profiles)).font(.system(size: 22, design: .serif))
                                Text(LF("%1$@ days · Best streak: %2$@", String(describing: connection.totalDays), String(describing: connection.bestStreak)))
                                    .font(.caption).foregroundStyle(DearlyTheme.muted)
                            }.padding(16).dearlyCard()
                        }
                    }
                    HStack {
                        if cursors.count > 1 {
                            Button(L("Previous page")) { cursors.removeLast(); Task { await load() } }.disabled(loading)
                        }
                        Spacer()
                        if let next = page?.nextCursor {
                            Button(L("Next page")) { cursors.append(next); Task { await load() } }.disabled(loading)
                        }
                    }
                }.padding(22)
            }.background(DearlyTheme.cream)
                .navigationTitle(L("Saved gardens")).navigationBarTitleDisplayMode(.inline)
                .toolbar { ToolbarItem(placement: .confirmationAction) { Button(L("Done")) { dismiss() } } }
                .task { await load() }
                .onDisappear { requestID = UUID() }
                .onChange(of: store.state.currentUserID) { _, _ in page = nil; dismiss() }
        }
    }

    private func otherName(_ connection: Connection, profiles: [Profile]) -> String {
        connection.members.first { $0 != store.state.currentUserID }.flatMap { id in profiles.first { $0.id == id }?.nickname } ?? L("a friend")
    }

    private func load() async {
        let expected = UUID(); requestID = expected
        loading = true; failure = nil; page = nil
        defer { if requestID == expected { loading = false } }
        do {
            let result = try await store.connectionPage(before: cursors.last ?? nil)
            guard requestID == expected else { return }
            page = result
        } catch {
            if requestID == expected { failure = error.localizedDescription }
        }
    }
}

/// Resolution-independent illustration; all growth states are drawn locally, no assets or network.
@MainActor
struct GardenIllustration: View {
    @Environment(\.colorScheme) private var colorScheme
    private var night: Bool { colorScheme == .dark }
    @AppStorage("dearly.language") private var language = "en"
    var stage: Int
    var body: some View {
        Canvas { context, size in
            let scale = min(size.width / 360, size.height / 280)
            context.translateBy(x: (size.width - 360 * scale) / 2, y: (size.height - 280 * scale) / 2)
            context.scaleBy(x: scale, y: scale)
            func ellipse(_ x: Double, _ y: Double, _ w: Double, _ h: Double, _ color: Color) {
                context.fill(Path(ellipseIn: CGRect(x: x, y: y, width: w, height: h)), with: .color(color))
            }
            func line(_ points: [CGPoint], _ color: Color, width: CGFloat = 3) {
                var path = Path(); path.addLines(points)
                context.stroke(path, with: .color(color), style: StrokeStyle(lineWidth: width, lineCap: .round, lineJoin: .round))
            }
            // A sun or moon above the garden, following the selected appearance.
            ellipse(267, 43, 38, 38, night ? Color(red: 0.84, green: 0.89, blue: 0.74) : Color(red: 0.97, green: 0.84, blue: 0.60))
            if night {
                ellipse(280, 38, 29, 29, Color(red: 0.10, green: 0.17, blue: 0.17))
                for point in [CGPoint(x: 52, y: 45), CGPoint(x: 132, y: 34), CGPoint(x: 220, y: 80)] {
                    ellipse(point.x, point.y, 3, 3, .white.opacity(0.7))
                }
            }
            ellipse(32, 83, 38, 13, .white.opacity(night ? 0.10 : 0.65))
            ellipse(48, 73, 32, 23, .white.opacity(night ? 0.10 : 0.65))
            ellipse(65, 84, 24, 12, .white.opacity(night ? 0.10 : 0.65))
            ellipse(245, 119, 44, 12, .white.opacity(night ? 0.08 : 0.5))
            ellipse(-50, 177, 290, 160, (night ? Color(red: 0.15, green: 0.26, blue: 0.21) : Color(red: 0.81, green: 0.87, blue: 0.75)))
            ellipse(160, 161, 270, 180, (night ? Color(red: 0.19, green: 0.31, blue: 0.24) : Color(red: 0.76, green: 0.84, blue: 0.70)))
            ellipse(52, 216, 265, 45, .black.opacity(0.05))
            ellipse(47, 182, 268, 62, Color(red: 0.69, green: 0.52, blue: 0.37))
            ellipse(47, 172, 268, 61, (night ? Color(red: 0.43, green: 0.36, blue: 0.25) : Color(red: 0.84, green: 0.71, blue: 0.52)))
            ellipse(55, 167, 252, 56, (night ? Color(red: 0.32, green: 0.47, blue: 0.30) : Color(red: 0.59, green: 0.71, blue: 0.46)))
            for i in 0..<12 {
                let x = Double(75 + i * 18)
                let y = Double(193 + (i % 3) * 6)
                line([CGPoint(x: x - 3, y: y - 4), CGPoint(x: x, y: y), CGPoint(x: x + 2, y: y - 6)], .white.opacity(0.28), width: 1.4)
            }
            ellipse(148, 189, 60, 17, Color(red: 0.50, green: 0.40, blue: 0.28).opacity(0.4))
            if stage == 0 {
                ellipse(169, 184, 18, 10, Color(red: 0.39, green: 0.30, blue: 0.20))
                line([CGPoint(x: 168, y: 201), CGPoint(x: 188, y: 201)], .white.opacity(0.7), width: 2)
            }
            if stage == 1 {
                ellipse(168, 182, 23, 14, Color(red: 0.46, green: 0.30, blue: 0.20))
                line([CGPoint(x: 179, y: 190), CGPoint(x: 179, y: 177)], DearlyTheme.forest, width: 3)
                ellipse(179, 174, 12, 7, DearlyTheme.forest)
            }
            if stage >= 2 {
                let top = stage == 2 ? 143.0 : 108.0
                var stem = Path()
                stem.move(to: CGPoint(x: 180, y: 194))
                stem.addCurve(to: CGPoint(x: 178, y: top), control1: CGPoint(x: 174, y: 170), control2: CGPoint(x: 187, y: top + 20))
                context.stroke(stem, with: .color(DearlyTheme.forest), style: StrokeStyle(lineWidth: 5, lineCap: .round))
                var left = Path()
                left.move(to: CGPoint(x: 179, y: 166))
                left.addQuadCurve(to: CGPoint(x: 139, y: 140), control: CGPoint(x: 142, y: 168))
                left.addQuadCurve(to: CGPoint(x: 179, y: 166), control: CGPoint(x: 177, y: 137))
                context.fill(left, with: .color(Color(red: 0.30, green: 0.48, blue: 0.31)))
                var right = Path()
                right.move(to: CGPoint(x: 181, y: 155))
                right.addQuadCurve(to: CGPoint(x: 216, y: 129), control: CGPoint(x: 185, y: 124))
                right.addQuadCurve(to: CGPoint(x: 181, y: 155), control: CGPoint(x: 215, y: 157))
                context.fill(right, with: .color(Color(red: 0.40, green: 0.58, blue: 0.35)))
                line([CGPoint(x: 178, y: 163), CGPoint(x: 148, y: 146)], .white.opacity(0.28), width: 1)
            }
            if stage >= 3 {
                for i in 0..<7 {
                    let angle = Double(i) * .pi * 2 / 7
                    ellipse(178 + cos(angle) * 17 - 12, 105 + sin(angle) * 17 - 12, 24, 24, Color(red: 0.97, green: 0.79, blue: 0.65))
                }
                ellipse(166, 93, 24, 24, Color(red: 0.87, green: 0.62, blue: 0.28))
                ellipse(172, 98, 5, 5, .white.opacity(0.4))
                for x in [100.0, 244.0] {
                    line([CGPoint(x: x, y: 193), CGPoint(x: x, y: 176)], DearlyTheme.forest, width: 2)
                    ellipse(x - 7, 171, 14, 10, .white.opacity(0.9))
                    ellipse(x - 2, 174, 4, 4, .yellow.opacity(0.7))
                }
            }
            if stage >= 4 {
                line([CGPoint(x: 266, y: 187), CGPoint(x: 266, y: 140), CGPoint(x: 249, y: 140), CGPoint(x: 249, y: 147)], DearlyTheme.forest, width: 3)
                let lantern = CGRect(x: 241, y: 146, width: 16, height: 22)
                context.fill(Path(roundedRect: lantern, cornerRadius: 4), with: .color(Color(red: 1, green: 0.88, blue: 0.56)))
                context.stroke(Path(roundedRect: lantern, cornerRadius: 4), with: .color(DearlyTheme.forest), lineWidth: 1.5)
            }
            if stage >= 5 {
                line([CGPoint(x: 86, y: 183), CGPoint(x: 86, y: 127)], DearlyTheme.forest, width: 5)
                ellipse(61, 101, 50, 62, Color(red: 0.36, green: 0.55, blue: 0.36))
                ellipse(76, 94, 36, 39, Color(red: 0.46, green: 0.64, blue: 0.40))
            }
            // A little stepping-stone path and stars of pollen.
            ellipse(201, 212, 16, 7, Color(red: 0.91, green: 0.87, blue: 0.72))
            ellipse(220, 217, 15, 7, Color(red: 0.91, green: 0.87, blue: 0.72))
            for point in [CGPoint(x: 123, y: 117), CGPoint(x: 223, y: 89), CGPoint(x: 231, y: 160)] {
                ellipse(point.x, point.y, 3, 3, .white.opacity(0.9))
            }
        }
        .background(LinearGradient(colors: night ? [Color(red: 0.08, green: 0.14, blue: 0.16), Color(red: 0.14, green: 0.24, blue: 0.20)] : [Color(red: 0.92, green: 0.94, blue: 0.85), Color(red: 0.86, green: 0.91, blue: 0.78)], startPoint: .top, endPoint: .bottom))
        .accessibilityLabel([L("A patch of earth waiting for seeds"), L("The first seed"), L("A green sprout"), L("The first flowers"), L("A flower garden with a lantern"), L("An expanded garden")][min(max(stage, 0), 5)])
    }
}
