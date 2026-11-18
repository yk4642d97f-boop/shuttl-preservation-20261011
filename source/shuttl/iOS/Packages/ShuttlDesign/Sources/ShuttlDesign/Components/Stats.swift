import SwiftUI
import os

// MARK: - StatBubble
// One scoreboard figure: the number, its unit in italic, and what it counts underneath.
// Pass `fill` to print it on a block of spot ink (the hero figure).

public struct StatBubble: View {
    public let value: String
    public let label: String
    public var unit: String?
    public var fill: Color?
    public var numeralFont: Font

    public init(value: String, label: String, unit: String? = nil, fill: Color? = nil,
                numeralFont: Font = AppFont.statSmall) {
        self.value = value; self.label = label; self.unit = unit; self.fill = fill; self.numeralFont = numeralFont
    }

    public var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            HStack(alignment: .firstTextBaseline, spacing: 3) {
                Text(value)
                    .font(numeralFont)
                    .foregroundStyle(Color.ink)
                    .lineLimit(1)
                    .minimumScaleFactor(0.5)
                    .contentTransition(.numericText())
                if let unit {
                    Text(unit)
                        .font(AppFont.unit(13, for: unit))
                        .foregroundStyle(fill == nil ? Color.inkSoft : Color.ink)
                        .fixedSize()
                }
            }
            Text(label)
                .instrumentLabel(AppFont.labelSmall, color: fill == nil ? .inkSoft : .ink)
                .lineLimit(1)
                .minimumScaleFactor(0.8)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, fill == nil ? 0 : AppSpacing.sm + 4)
        .padding(.vertical, fill == nil ? 0 : AppSpacing.sm + 2)
        .background {
            if let fill {
                RoundedRectangle(cornerRadius: AppRadius.sm + 4, style: .continuous)
                    .fill(fill)
                    .overlay(RoundedRectangle(cornerRadius: AppRadius.sm + 4, style: .continuous)
                        .strokeBorder(Color.ink, lineWidth: 1.5))
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(label) \(value)\(unit.map { " \($0)" } ?? "")")
    }
}

// MARK: - StatRow
// A scoreboard strip: figures separated by hairline ink rules.

public struct StatRow: View {
    public struct Stat {
        public let value: String
        public let label: String
        public let unit: String?
        public let fill: Color?
        public init(_ value: String, _ label: String, unit: String? = nil, hero: Bool = false, ink: Color = .tomato) {
            self.value = value; self.label = label; self.unit = unit
            self.fill = hero ? ink : nil
        }
    }

    public let stats: [Stat]
    /// One size for every figure, so the row never scales numerals unevenly.
    public var numeralFont: Font

    public init(stats: [Stat], numeralFont: Font = AppFont.statSmall) {
        self.stats = stats; self.numeralFont = numeralFont
    }

    public var body: some View {
        HStack(alignment: .center, spacing: AppSpacing.md) {
            ForEach(stats.indices, id: \.self) { i in
                StatBubble(value: stats[i].value, label: stats[i].label,
                           unit: stats[i].unit, fill: stats[i].fill, numeralFont: numeralFont)
                if i < stats.count - 1 && stats[i].fill == nil && stats[i + 1].fill == nil {
                    Rectangle().fill(Color.rule).frame(width: 1, height: 36)
                }
            }
        }
    }
}

// MARK: - CountUp
// A headline figure that rolls up to its value the first time it is seen, and rolls again if
// the value changes. It starts from zeros of the same width, so nothing around it moves.
// Coming back to a page it has already been shown on, it is simply there: a figure that
// re-counts from 000 on every visit reads, for half a second, as a different number.

public struct CountUp<Content: View>: View {
    private let target: String
    private let content: (String) -> Content
    @State private var shown: String
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    /// - content: draws the figure it is handed; put the `Text` inside it.
    public init(_ target: String, @ViewBuilder content: @escaping (String) -> Content) {
        self.target = target
        self.content = content
        // Western digits only: "三" and "½" also count as numbers, and must not roll from "0".
        let digits = !target.isEmpty && target.allSatisfy { $0.isASCII && $0.isNumber }
        let rolls = digits && !CountUpLedger.hasShown(target)
        _shown = State(initialValue: rolls ? String(repeating: "0", count: target.count) : target)
    }

    public var body: some View {
        content(shown)
            .contentTransition(.numericText())
            // What is read out is the figure itself, never the zeros it rolls up from.
            .accessibilityLabel(Text(verbatim: target))
            .onAppear {
                CountUpLedger.markShown(target)
                guard shown != target else { return }
                if reduceMotion {
                    shown = target
                } else {
                    withAnimation(.snappy(duration: 0.9).delay(0.15)) { shown = target }
                }
            }
            .onChange(of: target) { _, new in
                CountUpLedger.markShown(new)
                withAnimation(reduceMotion ? nil : .snappy(duration: 0.5)) { shown = new }
            }
    }
}

/// The figures that have already rolled up since the app was opened.
private enum CountUpLedger {
    private static let shown = OSAllocatedUnfairLock(initialState: Set<String>())

    static func hasShown(_ figure: String) -> Bool { shown.withLock { $0.contains(figure) } }
    static func markShown(_ figure: String) { shown.withLock { _ = $0.insert(figure) } }
}

public extension View {
    /// A card crossing the top or bottom edge of a scroll view fades and shrinks a touch, so
    /// a list eases in under a bar's fade instead of being cut off by it.
    func settlesAtEdges() -> some View {
        scrollTransition(.interactive.threshold(.visible(0.92))) { content, phase in
            content
                .opacity(phase.isIdentity ? 1 : 0.72)
                .scaleEffect(phase.isIdentity ? 1 : 0.985, anchor: .center)
        }
    }
}

#Preview("Stats") {
    VStack(spacing: 24) {
        StatRow(stats: [
            .init("42:18", "时长"),
            .init("14", "回合"),
            .init("341", "最高球速", unit: "km/h", hero: true),
        ])
        StatBubble(value: "352", label: "最高球速", unit: "km/h", fill: .butter, numeralFont: AppFont.display)
    }
    .padding(24)
    .paperPage()
}
