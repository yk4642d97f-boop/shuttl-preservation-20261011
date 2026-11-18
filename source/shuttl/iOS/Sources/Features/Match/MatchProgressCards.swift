import SwiftUI

// What fills the detail page while a match isn't finished: a printed checklist of the
// analysis stages (where it is, what's left) and, when it failed, what to change next time.

// MARK: - Stage ladder

struct AnalysisStageLadder: View {
    let match: Match
    let activity: PipelineActivity?
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    /// Pipeline stages folded into five things a player understands.
    private static let steps = ["找羽毛球", "认球场", "看人", "判每一拍", "记分"]

    private static func index(forStage stage: String) -> Int {
        switch stage {
        case "detect", "link": return 0
        case "calibrate": return 1
        case "players": return 2
        case "hits", "reconstruct3d", "shots": return 3
        case "rallies", "score", "done": return 4
        default: return 0
        }
    }

    /// The step in progress, or nil before analysis starts (uploading / queued).
    private var current: Int? {
        switch match.status {
        case .uploading, .recording: return nil
        case .analyzing:
            // Waiting its turn (queue, heat, camera, a take): no step is in progress yet.
            if MatchWaiting(localStage: activity?.localStage) != nil { return nil }
            if let stage = activity?.localStage {
                return Self.index(forStage: stage)
            }
            if let fraction = activity?.localFraction { return min(4, Int(fraction * 5)) }
            if let p = activity?.analysisPercent { return min(4, p / 20) }
            return 0
        default: return nil
        }
    }

    /// The short reason a match isn't being analysed yet (等相机 / 排队中 / 降温中 / 等录完).
    /// The card no longer prints it: the hero above carries the reason, and with no step lit
    /// the ladder already reads as "not started".
    static func waitingLine(status: MatchStatus, activity: PipelineActivity?) -> String? {
        if status == .uploading { return "上传完成后从第一步开始" }
        return MatchWaiting(localStage: activity?.localStage)?.label
    }

    var body: some View {
        AppCard(style: .print(.ink), padding: AppSpacing.md + 2) {
            VStack(alignment: .leading, spacing: AppSpacing.md) {
                VStack(alignment: .leading, spacing: 0) {
                    ForEach(Self.steps.indices, id: \.self) { i in
                        row(i)
                    }
                }
            }
        }
        .accessibilityElement(children: .combine)
    }

    private func row(_ i: Int) -> some View {
        let state: RowState = current.map { i < $0 ? .done : (i == $0 ? .now : .later) } ?? .later
        return HStack(alignment: .top, spacing: AppSpacing.md) {
            VStack(spacing: 0) {
                marker(state)
                if i < Self.steps.count - 1 {
                    Rectangle()
                        .fill(state == .done ? Color.ink : Color.ink.opacity(0.2))
                        .frame(width: 2, height: 26)
                }
            }
            Text(Self.steps[i])
                .font(AppFont.title(17))
                .foregroundStyle(state == .later ? Color.inkFaint : Color.ink)
                .padding(.top, 1)
            Spacer(minLength: 0)
        }
        .animation(AppAnimation.spring, value: state)
        .accessibilityLabel("\(Self.steps[i])，\(state == .done ? "已完成" : state == .now ? "进行中" : "未开始")")
    }

    private enum RowState { case done, now, later }

    @ViewBuilder
    private func marker(_ state: RowState) -> some View {
        switch state {
        case .done:
            Image(systemName: "checkmark")
                .font(.system(size: 11, weight: .black))
                .foregroundStyle(Color.ink)
                .frame(width: 24, height: 24)
                .background(Color.pistachio, in: Circle())
                .overlay(Circle().strokeBorder(Color.ink, lineWidth: AppStroke.fine))
        case .now:
            Circle()
                .fill(Color.tomato)
                .frame(width: 10, height: 10)
                .pulse(maxScale: 1.4, duration: 0.8)
                .frame(width: 24, height: 24)
                .background(Color.card, in: Circle())
                .overlay(Circle().strokeBorder(Color.ink, lineWidth: 2))
        case .later:
            Circle()
                .strokeBorder(Color.ink.opacity(0.35), style: StrokeStyle(lineWidth: 1.5, dash: [3, 3]))
                .frame(width: 24, height: 24)
        }
    }
}

// MARK: - While you wait

struct WhileYouWaitCard: View {
    let onDevice: Bool

    var body: some View {
        AppCard(padding: AppSpacing.md + 2) {
            HStack(alignment: .top, spacing: AppSpacing.md) {
                Image(systemName: "lightbulb.max")
                    .font(.system(size: 18, weight: .bold))
                    .foregroundStyle(Color.ink)
                    .frame(width: 36, height: 36)
                    .background(Color.card, in: Circle())
                    .overlay(Circle().strokeBorder(Color.ink, lineWidth: AppStroke.fine))
                    .rotationEffect(.degrees(-6))
                // The one thing to know while waiting. On the phone, analysis stops when the
                // app is left, so that has to be said; on the server it doesn't.
                Text(onDevice ? "可以接着录下一场。别锁屏、别切走，回来会接着算。" : "可以接着录下一场。")
                    .font(AppFont.callout.weight(.medium))
                    .foregroundStyle(Color.ink)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxHeight: .infinity, alignment: .center)
            }
        }
    }
}

// MARK: - Next time (failed)

struct ShootingTipsCard: View {
    private let tips: [(String, String)] = [
        ("camera.metering.center.weighted", "三脚架约 1.6 米高，底线后约 5 米，正对球场中线"),
        ("viewfinder", "开拍前看一眼：四个角都在画面里，球网横平"),
        ("sun.max.fill", "场馆灯都打开；别对着窗户或灯拍"),
        ("timer", "每段至少录完一整个回合，30 秒以上"),
    ]

    var body: some View {
        AppCard(style: .print(.ink), padding: AppSpacing.md + 2) {
            VStack(alignment: .leading, spacing: AppSpacing.md) {
                SectionHeader(title: "下次这样拍")
                ForEach(tips.indices, id: \.self) { i in
                    HStack(alignment: .top, spacing: AppSpacing.sm) {
                        Image(systemName: tips[i].0)
                            .font(.system(size: 13, weight: .bold))
                            .foregroundStyle(Color.ink)
                            .frame(width: 28, height: 28)
                            .background(Color.card, in: RoundedRectangle(cornerRadius: 8, style: .continuous))
                            .overlay(RoundedRectangle(cornerRadius: 8, style: .continuous)
                                .strokeBorder(Color.ink, lineWidth: AppStroke.fine))
                        Text(tips[i].1)
                            .font(AppFont.callout)
                            .foregroundStyle(Color.ink)
                            .fixedSize(horizontal: false, vertical: true)
                            .padding(.top, 4)
                    }
                    .accessibilityElement(children: .combine)
                }
            }
        }
    }
}
