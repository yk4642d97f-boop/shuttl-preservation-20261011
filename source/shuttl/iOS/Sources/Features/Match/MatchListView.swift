import SwiftUI
import SwiftData

// MARK: - Match ticket
// Each match is a ticket: a spot-ink stub with the date, torn along a
// perforation from the body that carries the numbers.

private struct MatchCard: View {
    let match: Match
    var activity: PipelineActivity?

    private let stubWidth: CGFloat = 78

    var body: some View {
        let shape = Ticket(stubX: stubWidth, radius: AppRadius.md)
        HStack(spacing: 0) {
            dateStub
                .frame(width: stubWidth)
            VStack(alignment: .leading, spacing: AppSpacing.sm) {
                HStack(alignment: .top) {
                    Text(scorecard: "\(match.courtLabel)\u{2002}\(match.durationText)",
                         figure: AppFont.figure(20), word: AppFont.title(19))
                        .foregroundStyle(Color.ink)
                        .lineLimit(1)
                        .minimumScaleFactor(0.8)
                    Spacer(minLength: AppSpacing.sm)
                    // A finished match says so with its numbers and its paper stub; only one
                    // still in motion, or failed, carries a badge.
                    if !archived {
                        ShuttlBadge(status: match.status, tilt: 3,
                                    waiting: MatchWaiting(localStage: activity?.localStage))
                    }
                }
                detailLine
            }
            .padding(.leading, AppSpacing.md)
            .padding(.trailing, AppSpacing.md - 2)
            .padding(.vertical, AppSpacing.md - 2)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .background {
            ZStack(alignment: .leading) {
                Color.card
                stubFill.frame(width: stubWidth)
            }
            .clipShape(shape)
        }
        .overlay {
            TearLine(x: stubWidth)
                .stroke(Color.ink, style: StrokeStyle(lineWidth: 1.25, dash: [3, 4]))
                .mask(shape.inset(by: 10))
        }
        .overlay(shape.strokeBorder(Color.ink, lineWidth: 1.5))
        .printShadow(shape, color: .ink, y: 4)
        .accessibilityElement(children: .combine)
    }

    /// Colour means state: only matches that are still in motion (or need a retry) get an
    /// ink-filled stub; finished ones stay paper, so a long archive reads calm.
    private var archived: Bool { match.status == .done }
    private var stubFill: Color { archived ? Color.paperDeep : match.status.ink }

    private var dateStub: some View {
        VStack(spacing: 0) {
            Text(match.createdAt.formatted(.dateTime.month(.abbreviated)))
                .instrumentLabel(AppFont.labelSmall, color: .ink)
            Text("\(Calendar.current.component(.day, from: match.createdAt))")
                .font(AppFont.figure(32))
                .foregroundStyle(archived ? Color.cobalt : Color.ink)
            Text(match.createdAt.formatted(.dateTime.hour().minute()))
                .font(AppFont.labelSmall)
                .foregroundStyle(Color.ink.opacity(0.8))
        }
        .padding(.vertical, AppSpacing.sm)
    }

    @ViewBuilder
    private var detailLine: some View {
        switch match.status {
        case .done:
            VStack(alignment: .leading, spacing: AppSpacing.sm) {
                HStack(spacing: AppSpacing.md) {
                    if match.lacksSpeeds {
                        // Same rule as the detail hero: no court, no speed; the shot count leads.
                        figure("\(match.allShots.count)", "击球")
                        figure("\(match.rallies.count)", "回合")
                        figure("—", "未标定", dim: true)
                    } else {
                        figure(match.maxSpeedText, "km/h 最高")
                        figure("\(match.rallies.count)", "回合")
                        figure("\(match.allShots.count)", "击球")
                    }
                }
                if !match.allShots.isEmpty {
                    ShotMixBar(shots: match.allShots, height: 4, hairline: true)
                }
            }
        case .analyzing, .uploading:
            VStack(alignment: .leading, spacing: AppSpacing.sm) {
                // A match that is only waiting has said so on its badge.
                if MatchWaiting(localStage: activity?.localStage) == nil {
                    note(match.progressText(activity), symbol: match.status.symbol)
                        .contentTransition(.numericText())
                }
                if let fraction = match.progressFraction(activity) {
                    InkProgressBar(value: fraction, fill: match.status.ink, height: 8)
                }
            }
        case .recording:
            note("正在录制", symbol: "record.circle")
        case .failed:
            note(match.failureReason ?? "分析没有成功", symbol: "exclamationmark.triangle")
                .lineLimit(2)
        }
    }

    private func figure(_ value: String, _ label: String, dim: Bool = false) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(value)
                .font(AppFont.figure(20))
                .foregroundStyle(dim ? Color.inkFaint : Color.ink)
            Text(label)
                .instrumentLabel(AppFont.labelSmall, color: .inkSoft)
        }
    }

    private func note(_ text: String, symbol: String) -> some View {
        Label(text, systemImage: symbol)
            .font(AppFont.callout.weight(.medium))
            .foregroundStyle(Color.inkSoft)
            .labelStyle(.titleAndIcon)
    }
}

/// The dashed line between the date stub and the card. It is drawn inside the card's own
/// height: a line run past the bottom edge and masked back still counts towards the card's
/// size for VoiceOver and for taps, and made every card report itself 400 pt tall.
private struct TearLine: Shape {
    let x: CGFloat

    func path(in rect: CGRect) -> Path {
        var path = Path()
        path.move(to: CGPoint(x: x, y: rect.minY + 12))
        path.addLine(to: CGPoint(x: x, y: rect.maxY))
        return path
    }
}

// MARK: - Empty state

private struct EmptyMatchesView: View {
    @Environment(AppChrome.self) private var chrome: AppChrome?

    var body: some View {
        VStack(spacing: AppSpacing.md) {
            ZStack {
                Circle().fill(Color.butter)
                    .overlay(Circle().strokeBorder(Color.ink, lineWidth: 1.5))
                    .frame(width: 150, height: 150)
                Circle().fill(Color.lilac)
                    .overlay(Circle().strokeBorder(Color.ink, lineWidth: 1.5))
                    .frame(width: 54, height: 54)
                    .offset(x: -66, y: 52)
                ShuttlecockMark(skirt: .card, cork: .tomato, ink: .ink)
                    .frame(width: 96, height: 96)
                    .rotationEffect(.degrees(-24))
            }
            .accessibilityHidden(true)
            .padding(.bottom, AppSpacing.sm)

            // The one thing to do on an empty page, and it says so itself.
            PillButton(title: "去录制第一场", icon: "record.circle") {
                withAnimation(AppAnimation.bouncy) { chrome?.selectedTab = .record }
            }
            .frame(maxWidth: 260)
            .padding(.top, AppSpacing.sm)
        }
        .frame(maxWidth: .infinity)
        .padding(.top, AppSpacing.xxl)
    }
}

// MARK: - MatchListView

struct MatchListView: View {
    @Query(sort: \Match.createdAt, order: .reverse) private var matches: [Match]
    @Environment(\.modelContext) private var modelContext
    @Environment(MatchPipeline.self) private var pipeline: MatchPipeline?
    @State private var path = NavigationPath()
    @State private var deletionError: String?
    @State private var pendingDeletion: Match?

    private var active: [Match] { matches.filter { $0.status != .done && $0.status != .failed } }
    private var archived: [Match] { matches.filter { $0.status == .done || $0.status == .failed } }

    var body: some View {
        NavigationStack(path: $path) {
            ScrollView {
                VStack(alignment: .leading, spacing: AppSpacing.lg) {
                    PageHeader(title: "比赛", ink: .cobalt) {
                        if !matches.isEmpty { countSeal }
                    }
                    if let heat = demoSystemItem(pipeline?.thermalChip, "有点热，这场分析完歇会儿", .mild) {
                        SystemChip(text: heat.text, symbol: "thermometer.medium", severity: heat.severity, spoken: heat.spoken)
                            .padding(.horizontal, AppSpacing.gutter)
                            .padding(.top, -AppSpacing.sm)
                    }

                    if let message = pipeline?.remoteSyncMessage {
                        VStack(alignment: .leading) {
                            Text(message).font(AppFont.caption)
                            Button("重试同步") { Task { await pipeline?.syncRemoteCommands() } }
                        }.padding(.horizontal, AppSpacing.gutter)
                    }
                    if matches.isEmpty {
                        EmptyMatchesView()
                    } else {
                        // Matches still in motion first, then the finished ones. The wider
                        // gap between the two groups is the only heading they need.
                        if !active.isEmpty { cards(active) }
                        if !archived.isEmpty { cards(archived) }
                    }
                }
                .padding(.bottom, AppSpacing.xl)
            }
            .tabBarClearance()
            .paperPage()
            .statusBarScrim()
            .toolbar(.hidden, for: .navigationBar)
            .navigationTitle("比赛")
            .navigationDestination(for: Match.self) { match in
                MatchDetailView(match: match)
            }
            .navigationDestination(for: ReplayRoute.self) { route in
                ReplayView(match: route.match, startFrame: route.startFrame)
            }
        }
        .onAppear(perform: openDemoMatchIfNeeded)
        #if DEBUG
        // The seeded matches can arrive after the first appearance.
        .onChange(of: matches.count) { openDemoMatchIfNeeded() }
        #endif
        .alert("没能删除比赛", isPresented: Binding(get: { deletionError != nil }, set: { if !$0 { deletionError = nil } })) {
            Button("知道了", role: .cancel) {}
        } message: { Text(deletionError ?? "") }
        .confirmationDialog("删除这场比赛？", isPresented: Binding(get: { pendingDeletion != nil }, set: { if !$0 { pendingDeletion = nil } })) {
            if let match = pendingDeletion { Button("删除这场", role: .destructive) { delete(match) } }
            Button("取消", role: .cancel) {}
        } message: {
            Text("删除录像和分析记录；已上传的比赛也会请求云端删除，离线时将在联网并登录原账号后同步。此操作不能恢复。")
        }
    }

    private func cards(_ items: [Match]) -> some View {
        VStack(alignment: .leading, spacing: AppSpacing.md) {
            ForEach(items) { match in
                NavigationLink(value: match) {
                    MatchCard(match: match, activity: pipeline?.activity(for: match))
                }
                .buttonStyle(ScaleButtonStyle(scale: 0.975))
                .settlesAtEdges()
                .contextMenu {
                    if match.status == .failed, let pipeline {
                        Button {
                            pipeline.retry(match)
                        } label: {
                            Label("重试", systemImage: "arrow.clockwise")
                        }
                    }
                    Button(role: .destructive) {
                        pendingDeletion = match
                    } label: {
                        Label("删除", systemImage: "trash")
                    }
                }
            }
        }
        .padding(.horizontal, AppSpacing.gutter)
    }

    /// Rosette sticker with the match count.
    private var countSeal: some View {
        Seal(value: "\(matches.count)", caption: "场", fill: .butter, size: 78, tilt: 10)
            .padding(.bottom, AppSpacing.sm)
            .accessibilityLabel("共 \(matches.count) 场比赛")
    }

    private func delete(_ match: Match) {
        guard let pipeline else { return }
        Task {
            do {
                try await pipeline.discard(match)
                withAnimation(AppAnimation.spring) { modelContext.delete(match) }
                try modelContext.save()
            } catch { deletionError = MatchPipeline.failureReason(for: error) }
        }
    }

    private func openDemoMatchIfNeeded() {
        #if DEBUG
        let wanted = DemoMode.openStatus ?? .done
        guard path.isEmpty, DemoMode.opensMatch,
              let match = matches.first(where: {
                  $0.status == wanted && (!DemoMode.opensServerMatch || $0.analysisPath == nil)
              }) else { return }
        path.append(match)
        if DemoMode.opensReplay { path.append(ReplayRoute(match: match)) }
        #endif
    }
}
