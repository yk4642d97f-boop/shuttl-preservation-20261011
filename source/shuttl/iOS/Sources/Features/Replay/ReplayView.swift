import SwiftUI
import AVFoundation
import SwiftData

// MARK: - AVPlayerView (UIViewRepresentable)

struct AVPlayerView: UIViewRepresentable {
    let player: AVPlayer

    func makeUIView(context: Context) -> PlayerUIView {
        let view = PlayerUIView()
        view.player = player
        return view
    }

    func updateUIView(_ uiView: PlayerUIView, context: Context) {
        uiView.player = player
    }
}

final class PlayerUIView: UIView {
    override class var layerClass: AnyClass { AVPlayerLayer.self }

    var player: AVPlayer? {
        get { (layer as? AVPlayerLayer)?.player }
        set { (layer as? AVPlayerLayer)?.player = newValue }
    }

    override init(frame: CGRect) {
        super.init(frame: frame)
        (layer as? AVPlayerLayer)?.videoGravity = .resizeAspect
    }

    required init?(coder: NSCoder) { fatalError() }
}

// MARK: - ReplayView
// Video sits on a night surround; everything you touch is printed on paper.

struct ReplayView: View {
    let match: Match
    @State private var viewModel: ReplayViewModel
    @Environment(\.dismiss) private var dismiss
    @Environment(AppChrome.self) private var chrome: AppChrome?
    @Environment(\.verticalSizeClass) private var verticalSizeClass
    /// A finger is down on the scrubber.
    @GestureState private var scrubbing = false
    /// Counts ⏮ / ⏭ taps: the trigger for their haptic and for sliding the playhead.
    @State private var jumps = 0
    /// Counts taps on the picture: the trigger for the play / pause flash.
    @State private var pictureTaps = 0

    /// On its side the picture gets the height; controls fold into one strip.
    private var landscape: Bool { verticalSizeClass == .compact }

    init(match: Match, startFrame: Int? = nil) {
        self.match = match
        _viewModel = State(initialValue: ReplayViewModel(match: match, startFrame: startFrame))
    }

    var body: some View {
        ZStack {
            Color.night.ignoresSafeArea()

            #if DEBUG
            if DemoMode.isOn { DemoCourtBackdrop().ignoresSafeArea() }
            #endif

            if let player = viewModel.player {
                AVPlayerView(player: player)
                    .ignoresSafeArea()
                    // Tap the picture to play/pause, like every other video app.
                    .contentShape(Rectangle())
                    .onTapGesture {
                        viewModel.togglePlayback()
                        pictureTaps += 1
                    }
                    .accessibilityAddTraits(.isButton)
                    .accessibilityLabel(viewModel.isPlaying ? "暂停播放" : "继续播放")
                    .accessibilityHint("轻点画面切换播放和暂停")
            } else if viewModel.videoMissing {
                VStack(spacing: AppSpacing.sm) {
                    Image(systemName: "film.stack")
                        .font(.system(size: 28, weight: .bold))
                        .foregroundStyle(Color.butter)
                    Text("这台设备上找不到这场的视频文件")
                        .font(AppFont.callout)
                        .foregroundStyle(Color.paper.opacity(0.8))
                }
                .accessibilityElement(children: .combine)
            } else {
                VStack(spacing: AppSpacing.sm) {
                    ProgressView().tint(.butter)
                    Text("加载视频…").font(AppFont.callout).foregroundStyle(Color.paper.opacity(0.7))
                }
            }

            GeometryReader { geo in
                ZStack {
                    TrajectoryOverlayView(points: overlayPoints(in: geo.size))
                    if let shot = viewModel.nearbyShot {
                        let rect = viewModel.videoRect(in: geo.size)
                        shotTypeLabel(shot)
                            .position(x: rect.minX + CGFloat(shot.normalizedX) * rect.width,
                                      y: max(60, rect.minY + CGFloat(shot.normalizedY) * rect.height - 36))
                            .transition(.scale.combined(with: .opacity))
                            .animation(AppAnimation.springFast, value: shot.frameIndex)
                    }
                }
            }
            .ignoresSafeArea()

            PlaybackFlash(isPlaying: viewModel.isPlaying, trigger: pictureTaps)

            VStack {
                topBar
                Spacer()
                Group {
                    if landscape { compactControlBar } else { controlBar }
                }
                .padding(.horizontal, AppSpacing.md)
                .padding(.bottom, landscape ? AppSpacing.xs : AppSpacing.sm)
            }
        }
        .sensoryFeedback(.impact(weight: .light), trigger: pictureTaps)
        .sensoryFeedback(.impact(weight: .light), trigger: jumps)
        .toolbar(.hidden, for: .navigationBar)
        .statusBarHidden(true)
        .onAppear {
            chrome?.replayOpen = true
            viewModel.setup()
        }
        #if DEBUG
        .task {
            guard let at = DemoMode.replayAtSeconds else { return }
            try? await Task.sleep(for: .milliseconds(900))
            viewModel.currentTime = at
        }
        #endif
        .onDisappear {
            chrome?.replayOpen = false
            viewModel.teardown()
        }
    }

    private func overlayPoints(in size: CGSize) -> [CGPoint] {
        #if DEBUG
        if DemoMode.isOn && viewModel.currentTrajectoryWindow.isEmpty {
            return DemoMode.syntheticTrail().map { CGPoint(x: $0.x * size.width, y: $0.y * size.height) }
        }
        #endif
        // Same frame as the aspect-fit player, so map into the picture rect, not the whole screen.
        let rect = viewModel.videoRect(in: size)
        return viewModel.currentTrajectoryWindow.map {
            CGPoint(x: rect.minX + $0.position.x * rect.width, y: rect.minY + $0.position.y * rect.height)
        }
    }

    // MARK: - Top bar

    /// How much of the title slip the row has room for. Nothing in the row wraps or truncates:
    /// when it runs out of width the title gives way first, since the score and the
    /// rallies-only switch are what you came here to use. A phone held upright drops it, and
    /// on the narrowest screens (Display Zoom, large type) the switch keeps only its glyph, so
    /// the back button and the switch can never be pushed off the edges.
    private enum TopBarTitle { case dated, plain, hidden, compact }

    private var topBar: some View {
        ViewThatFits(in: .horizontal) {
            topBarRow(.dated)
            topBarRow(.plain)
            topBarRow(.hidden)
            topBarRow(.compact)
        }
        .padding(.horizontal, AppSpacing.md)
        .padding(.top, landscape ? AppSpacing.xs : AppSpacing.sm)
    }

    private func topBarRow(_ title: TopBarTitle) -> some View {
        HStack(spacing: AppSpacing.sm) {
            IconButton(systemName: "chevron.left", style: .filled, label: "返回") { dismiss() }
            if title == .dated || title == .plain { titleSlip(dated: title == .dated) }
            if let chip = rallyChip { scoreSlip(chip, shrinks: title == .compact) }
            Spacer(minLength: 0)
            if !viewModel.rallyWindows.isEmpty { ralliesOnlySwitch(glyphOnly: title == .compact) }
        }
    }

    private func titleSlip(dated: Bool) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 6) {
            Text("回放")
                .font(AppFont.title3)
                .foregroundStyle(Color.ink)
            if dated {
                Text(match.createdAt.formatted(date: .abbreviated, time: .shortened))
                    .font(AppFont.labelSmall)
                    .foregroundStyle(Color.inkSoft)
            }
        }
        .lineLimit(1)
        .fixedSize()
        .padding(.horizontal, AppSpacing.md - 2)
        .frame(height: 44)
        .background(Color.paper, in: Capsule())
        .overlay(Capsule().strokeBorder(Color.ink, lineWidth: 1.5))
        .accessibilityElement(children: .combine)
        .accessibilityAddTraits(.isHeader)
    }

    /// Rally number and the score after it, on one line. Near is cobalt, as everywhere else.
    /// `shrinks` is the last-resort row: the slip may scale its type down, never the buttons.
    private func scoreSlip(_ chip: (label: String, near: Int, far: Int), shrinks: Bool) -> some View {
        HStack(alignment: .firstTextBaseline, spacing: 5) {
            Text("回合 \(chip.label)")
                .font(AppFont.labelSmall)
                .foregroundStyle(Color.inkSoft)
                .padding(.trailing, 2)
            Text("近").font(AppFont.labelSmall).foregroundStyle(Color.cobalt)
            Text("\(chip.near)").font(AppFont.figure(17)).foregroundStyle(Color.cobalt)
            Text(":").font(AppFont.figure(14)).foregroundStyle(Color.inkFaint)
            Text("\(chip.far)").font(AppFont.figure(17)).foregroundStyle(Color.ink)
            Text("远").font(AppFont.labelSmall).foregroundStyle(Color.inkSoft)
        }
        .lineLimit(1)
        .minimumScaleFactor(shrinks ? 0.6 : 1)
        .fixedSize(horizontal: !shrinks, vertical: true)
        .contentTransition(.numericText())
        .animation(AppAnimation.standard, value: chip.label)
        .padding(.horizontal, 12)
        .frame(height: 36)
        .background(Color.paper, in: Capsule())
        .overlay(Capsule().strokeBorder(Color.ink, lineWidth: AppStroke.fine))
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("第 \(chip.label) 回合，近端 \(chip.near) 比远端 \(chip.far)")
    }

    /// A sticker switch. Its label never changes, so the row doesn't shift when it flips;
    /// butter and a slight tilt say "on".
    private func ralliesOnlySwitch(glyphOnly: Bool) -> some View {
        let on = viewModel.ralliesOnly
        return Button {
            withAnimation(AppAnimation.bouncy) { viewModel.ralliesOnly.toggle() }
        } label: {
            HStack(spacing: 6) {
                Image(systemName: on ? "scissors" : "film")
                    .font(.system(size: 13, weight: .black))
                    .contentTransition(.symbolEffect(.replace))
                    .frame(width: 16)
                if !glyphOnly {
                    Text("只看回合")
                        .font(AppFont.title(15))
                }
            }
            .foregroundStyle(Color.ink)
            .lineLimit(1)
            .fixedSize()
            .padding(.horizontal, 14)
            .frame(height: 40)
            .background(on ? Color.butter : Color.paper, in: Capsule())
            .overlay(Capsule().strokeBorder(Color.ink, lineWidth: AppStroke.ink))
            .rotationEffect(.degrees(on ? 3 : 0))
        }
        .buttonStyle(ScaleButtonStyle())
        .sensoryFeedback(.selection, trigger: on)
        .accessibilityLabel("只看回合")
        .accessibilityValue(on ? "开，自动跳过捡球时间" : "关")
    }

    // MARK: - Control deck

    private var controlBar: some View {
        let shape = RoundedRectangle(cornerRadius: AppRadius.lg, style: .continuous)
        return VStack(spacing: AppSpacing.sm) {
            // Where the playhead is, and how long the take runs.
            HStack(alignment: .firstTextBaseline) {
                Text(viewModel.replayTimeText)
                    .font(AppFont.timer)
                    .foregroundStyle(Color.ink)
                    .contentTransition(.numericText())
                Spacer(minLength: AppSpacing.sm)
                Text(ReplayViewModel.clock(timelineSeconds))
                    .font(AppFont.labelSmall)
                    .foregroundStyle(Color.inkSoft)
                    .accessibilityLabel("总时长 \(ReplayViewModel.clock(timelineSeconds))")
            }
            .monospacedDigit()

            scrubber
                .padding(.bottom, AppSpacing.xs)

            // Speeds on the left, transport on the right under the thumb. The row never grows
            // past the deck: on a narrow phone, or with large type, the four speed chips fold
            // into one menu chip.
            ViewThatFits(in: .horizontal) {
                HStack(spacing: 0) {
                    rateChips.padding(.bottom, Self.plateDepth)
                    Spacer(minLength: AppSpacing.xs)
                    transport
                }
                HStack(spacing: 0) {
                    rateMenu.padding(.bottom, Self.plateDepth)
                    Spacer(minLength: AppSpacing.xs)
                    transport
                }
            }
        }
        .padding(AppSpacing.md)
        .background(Color.paper, in: shape)
        .overlay(shape.strokeBorder(Color.ink, lineWidth: 1.5))
    }

    /// The play button's printed plate sits this far below its face; its neighbours lift by
    /// the same amount so they centre on the face, not on face plus plate.
    private static let plateDepth: CGFloat = 4

    /// ⏮ ▶ ⏭. The step buttons exist only when the match has rallies to step through.
    private var transport: some View {
        HStack(spacing: 0) {
            if !viewModel.rallyWindows.isEmpty {
                rallyJumpButton(forward: false).padding(.bottom, Self.plateDepth)
            }
            Button { viewModel.togglePlayback() } label: {
                Image(systemName: viewModel.isPlaying ? "pause.fill" : "play.fill")
                    .font(.system(size: 20, weight: .black))
                    .foregroundStyle(Color.onCobalt)
                    .contentTransition(.symbolEffect(.replace))
                    .frame(width: 56, height: 56)
                    .background(Color.cobalt, in: Circle())
                    .overlay(Circle().strokeBorder(Color.ink, lineWidth: 1.5))
            }
            .buttonStyle(PrintButtonStyle(shape: Circle(), plate: .ink, depth: Self.plateDepth))
            .accessibilityLabel(viewModel.isPlaying ? "暂停" : "播放")
            if !viewModel.rallyWindows.isEmpty {
                rallyJumpButton(forward: true).padding(.bottom, Self.plateDepth)
            }
        }
    }

    /// Landscape: transport · time · scrubber · speed, on one paper strip.
    private var compactControlBar: some View {
        let shape = Capsule()
        return HStack(spacing: AppSpacing.md) {
            HStack(spacing: 0) {
                if !viewModel.rallyWindows.isEmpty { rallyJumpButton(forward: false) }
                playButton(size: 46)
                if !viewModel.rallyWindows.isEmpty { rallyJumpButton(forward: true) }
            }
            Text(viewModel.replayTimeText)
                .font(AppFont.timer)
                .foregroundStyle(Color.ink)
                .contentTransition(.numericText())
                .frame(minWidth: 56, alignment: .leading)
            scrubber
            rateChips
        }
        .padding(.leading, 6)
        .padding(.trailing, AppSpacing.md)
        .padding(.vertical, 6)
        .background(Color.paper, in: shape)
        .overlay(shape.strokeBorder(Color.ink, lineWidth: AppStroke.ink))
        .printShadow(shape, color: .ink, y: 4)
        .frame(maxWidth: 760)
    }

    private var rateChips: some View {
        HStack(spacing: 4) {
            ForEach(viewModel.availableRates, id: \.self) { rate in
                let active = abs(viewModel.playbackRate - rate) < 0.01
                Button { withAnimation(AppAnimation.bouncy) { viewModel.setRate(rate) } } label: {
                    Text(rateText(rate))
                        .font(AppFont.labelSmall)
                        .foregroundStyle(active ? Color.paper : Color.inkSoft)
                        .frame(minWidth: 40, minHeight: 32)
                        .background(active ? Color.ink : Color.clear, in: Capsule())
                        .contentShape(Capsule())
                }
                .buttonStyle(ScaleButtonStyle())
                .accessibilityLabel("\(rateText(rate)) 速")
                .accessibilityAddTraits(active ? [.isSelected] : [])
            }
        }
        .padding(3)
        .background(Color.paperDeep, in: Capsule())
        .overlay(Capsule().strokeBorder(Color.ink, lineWidth: 1.25))
    }

    /// One chip that opens the four speeds, for widths the row of chips doesn't fit.
    private var rateMenu: some View {
        Menu {
            Picker("播放速度", selection: Binding(get: { viewModel.playbackRate },
                                              set: { viewModel.setRate($0) })) {
                ForEach(viewModel.availableRates, id: \.self) { rate in
                    Text(rateText(rate)).tag(rate)
                }
            }
        } label: {
            HStack(spacing: 5) {
                Image(systemName: "speedometer").font(.system(size: 12, weight: .bold))
                Text(rateText(viewModel.playbackRate)).font(AppFont.labelSmall)
            }
            .foregroundStyle(Color.ink)
            .lineLimit(1)
            .fixedSize()
            .padding(.horizontal, 12)
            .frame(height: 38)
            .background(Color.paperDeep, in: Capsule())
            .overlay(Capsule().strokeBorder(Color.ink, lineWidth: 1.25))
        }
        .accessibilityLabel("播放速度")
        .accessibilityValue("\(rateText(viewModel.playbackRate)) 速")
    }

    /// A step button on card stock: quieter than play. 44 pt to touch, 38 pt to look at.
    private func rallyJumpButton(forward: Bool) -> some View {
        let enabled = forward ? viewModel.canJumpForward : viewModel.canJumpBack
        return Button {
            viewModel.jumpRally(forward: forward)
            jumps += 1
        } label: {
            Image(systemName: forward ? "forward.end.fill" : "backward.end.fill")
                .font(.system(size: 13, weight: .black))
                .foregroundStyle(enabled ? Color.ink : Color.inkFaint)
                .frame(width: 38, height: 38)
                .background(Color.card, in: Circle())
                .overlay(Circle().strokeBorder(enabled ? Color.ink : Color.rule, lineWidth: 1.25))
                .frame(width: 44, height: 44)
                .contentShape(Rectangle())
        }
        .buttonStyle(ScaleButtonStyle())
        .disabled(!enabled)
        .accessibilityLabel(forward ? "下一分" : "上一分")
    }

    private func playButton(size: CGFloat) -> some View {
        Button { viewModel.togglePlayback() } label: {
            Image(systemName: viewModel.isPlaying ? "pause.fill" : "play.fill")
                .font(.system(size: size * 0.36, weight: .black))
                .foregroundStyle(Color.onCobalt)
                .contentTransition(.symbolEffect(.replace))
                .frame(width: size, height: size)
                .background(Color.cobalt, in: Circle())
                .overlay(Circle().strokeBorder(Color.ink, lineWidth: AppStroke.ink))
        }
        .buttonStyle(ScaleButtonStyle())
        .accessibilityLabel(viewModel.isPlaying ? "暂停" : "播放")
    }

    private var scrubber: some View {
        GeometryReader { geo in
            let w = geo.size.width
            let x = w * min(1, max(0, viewModel.currentTime / max(timelineSeconds, 0.001)))
            ZStack(alignment: .leading) {
                Capsule().fill(Color.paperDeep)
                    .overlay(Capsule().strokeBorder(Color.ink, lineWidth: 1.25))
                    .frame(height: 12)
                Capsule().fill(Color.tomato)
                    .frame(width: max(12, x), height: 12)
                    .overlay(Capsule().strokeBorder(Color.ink, lineWidth: 1.25))
                Circle()
                    .fill(Color.butter)
                    .overlay(Circle().strokeBorder(Color.ink, lineWidth: 1.5))
                    .frame(width: 24, height: 24)
                    // Swells under the finger, so you can tell you have hold of it.
                    .scaleEffect(scrubbing ? 1.3 : 1)
                    .animation(AppAnimation.springFast, value: scrubbing)
                    .offset(x: min(max(0, x - 12), w - 24))
            }
            .frame(height: 24)
            // ⏮ / ⏭ slide the playhead to the rally instead of teleporting it. Keyed on the
            // tap count, so playback and drags stay un-animated (they are already continuous).
            .animation(AppAnimation.spring, value: jumps)
            // Where the play is, under the track: a full-width ink hairline, a 3 pt pistachio
            // segment per rally, and an ink tick at every hit.
            .overlay(alignment: .bottomLeading) {
                ZStack(alignment: .leading) {
                    Rectangle().fill(Color.ink.opacity(0.35)).frame(width: w, height: 1)
                    ForEach(Array(rallyBands.enumerated()), id: \.offset) { _, band in
                        Rectangle().fill(Color.pistachio.opacity(0.6))
                            .frame(width: max(3, w * (band.upperBound - band.lowerBound)), height: 3)
                            .offset(x: w * band.lowerBound)
                    }
                    // Hits sit below the band as short, light ticks: a rally has 5–15 of them, and
                    // full-height ink ticks would cover the band they belong to.
                    ForEach(Array(hitTicks.enumerated()), id: \.offset) { _, t in
                        Rectangle().fill(Color.ink.opacity(0.45)).frame(width: 1, height: 3).offset(x: w * t, y: 4)
                    }
                }
                .frame(width: w, height: 8, alignment: .leading)
                .offset(y: 12)
                .allowsHitTesting(false)
            }
            .contentShape(Rectangle())
            .gesture(
                DragGesture(minimumDistance: 0)
                    .updating($scrubbing) { _, held, _ in held = true }
                    .onChanged { val in
                        let p = max(0, min(1, val.location.x / w))
                        viewModel.seek(to: p * timelineSeconds)
                    }
            )
        }
        .frame(height: 34)
        // `scrubbing` also falls back to false when the system cancels the drag, which
        // `onEnded` would miss; playback must not stay held after that.
        .onChange(of: scrubbing) { _, held in
            if held { viewModel.beginScrubbing() } else { viewModel.endScrubbing() }
        }
        .sensoryFeedback(.impact(flexibility: .soft, intensity: 0.6), trigger: scrubbing) { _, held in held }
        // A tick each time the drag crosses into another rally.
        .sensoryFeedback(.selection, trigger: viewModel.currentRallyIndex) { _, _ in scrubbing }
        .accessibilityElement()
        .accessibilityLabel("播放进度")
        .accessibilityValue(viewModel.replayTimeText)
        .accessibilityAdjustableAction { dir in
            let step = max(1, timelineSeconds / 20)
            switch dir {
            case .increment: viewModel.seek(to: min(timelineSeconds, viewModel.currentTime + step))
            case .decrement: viewModel.seek(to: max(0, viewModel.currentTime - step))
            @unknown default: break
            }
        }
    }

    /// The timeline length: the player's once it knows it, else the recorded duration, so the
    /// rally bands are there from the first frame.
    private var timelineSeconds: Double {
        viewModel.duration > 0 && viewModel.duration.isFinite ? viewModel.duration : match.durationSeconds
    }

    /// Rally spans as fractions of the timeline, so the play is visible at a glance.
    private var rallyBands: [ClosedRange<Double>] {
        guard timelineSeconds > 0 else { return [] }
        let d = timelineSeconds * viewModel.fps
        return viewModel.rallyWindows.compactMap { r in
            let a = Double(r.lowerBound) / d, b = min(1, Double(r.upperBound) / d)
            return a < 1 ? a...max(a, b) : nil
        }
    }

    private var hitTicks: [Double] {
        guard timelineSeconds > 0 else { return [] }
        let d = timelineSeconds * viewModel.fps
        return match.allShots.map { Double($0.frameIndex) / d }.filter { $0 >= 0 && $0 < 1 }
    }

    /// The rally the playhead is in (or the one just before it) and the score after it.
    private var rallyChip: (label: String, near: Int, far: Int)? {
        let frame = Int(viewModel.currentTime * viewModel.fps)
        let rallies = match.rallies.sorted { $0.startFrame < $1.startFrame }
        guard !rallies.isEmpty else { return nil }
        let index = rallies.lastIndex { $0.startFrame - 30 <= frame } ?? 0
        let upTo = rallies.prefix(index + 1)
        return (String(format: "%02d", index + 1),
                upTo.filter { $0.winner == .near }.count, upTo.filter { $0.winner == .far }.count)
    }

    // MARK: - Shot label

    private func shotTypeLabel(_ shot: ShotPoint) -> some View {
        HStack(spacing: 5) {
            ShotGlyph(shot.shotType.glyphKind).frame(width: 16, height: 16)
            Text(shot.shotType.displayName).font(AppFont.title(14))
            if shot.speedKmh > 0 {
                Text("\(Int(shot.speedKmh))").font(AppFont.figure(14))
            }
        }
        .foregroundStyle(Color.ink)
        .padding(.horizontal, 10)
        .padding(.vertical, 5)
        .background(shot.shotType.ink, in: Capsule())
        .overlay(Capsule().strokeBorder(Color.ink, lineWidth: 1.5))
        .rotationEffect(.degrees(-4))
    }

    private func rateText(_ rate: Float) -> String {
        rate == 1.0 ? "1×" : String(format: "%.2g×", rate)
    }
}

// MARK: - Play / pause flash
// The glyph that blinks over the picture when a tap toggles playback: it shows what the tap
// just did, on a paper disc like every other control, and is gone in half a second.

private struct PlaybackFlash: View {
    let isPlaying: Bool
    let trigger: Int

    private enum Phase { case rest, shown, gone }

    var body: some View {
        Image(systemName: isPlaying ? "play.fill" : "pause.fill")
            .font(.system(size: 26, weight: .black))
            .foregroundStyle(Color.ink)
            .frame(width: 72, height: 72)
            .background(Color.paper, in: Circle())
            .overlay(Circle().strokeBorder(Color.ink, lineWidth: AppStroke.ink))
            .phaseAnimator([Phase.rest, .shown, .gone], trigger: trigger) { disc, phase in
                disc
                    .opacity(phase == .shown ? 1 : 0)
                    .scaleEffect(phase == .rest ? 0.8 : phase == .shown ? 1 : 1.2)
            } animation: { phase in
                switch phase {
                case .rest:  nil                        // back to the start, unseen
                case .shown: .easeOut(duration: 0.12)
                case .gone:  .easeIn(duration: 0.4)
                }
            }
            .allowsHitTesting(false)
            .accessibilityHidden(true)
    }
}

// MARK: - ReplayViewModel convenience extensions

extension ReplayViewModel {
    /// m:ss, for the playhead and for the length of the take.
    nonisolated static func clock(_ seconds: Double) -> String {
        let t = seconds.isFinite ? max(0, seconds) : 0
        return String(format: "%d:%02d", Int(t) / 60, Int(t) % 60)
    }

    var replayTimeText: String { Self.clock(currentTime) }

    var replayProgress: Double {
        guard duration > 0, duration.isFinite else { return 0 }
        return min(1, max(0, currentTime / duration))
    }
}
