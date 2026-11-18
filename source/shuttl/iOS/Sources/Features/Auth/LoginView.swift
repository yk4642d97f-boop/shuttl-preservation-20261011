import SwiftUI

// MARK: - LoginView
// The sign-in page. It says what it has to say with ink, line and one object, not with
// sentences.
//
// The page is one flat ink, edge to edge, and the ink is the state of the form: tomato while
// neither thing is right, butter when one of them is, pistachio when you can go in. A refused
// attempt puts it back to tomato. Those are the inks a match card uses for failed / in
// progress / done.
//
// In the middle sits a plush shuttlecock. Its fur follows the same state (lying flat, half
// up, fully fluffed and hopping) and it is the page's one button: tap it, or flick it
// upward, and it is served off the top of the screen while the attempt is checked. If the
// server refuses, it drops back. Tapped before the form is complete, it shakes its head and
// puts the cursor where something is missing.
//
// Each field is an ink capsule, the shape of the app's tab bar: an outline until what is in
// it is good, then solid, with the writing reversed out of it. A new password's outline
// thickens round the capsule one step per character before it fills, which is the whole of
// the "at least eight" rule.
//
// Soft against hard: the only modelled, furry thing on the page sits on flat ink and heavy
// type.
//
// The only words are the wordmark and the two modes, plus the server's reason when it
// refuses. Fields are named by a glyph (envelope, lock, person) that waits in the middle of
// an empty capsule and steps aside to its left edge once there is writing.

struct LoginView: View {
    @Environment(AuthService.self) private var auth
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    @State private var email = ""
    @State private var password = ""
    @State private var nickname = ""
    @State private var isRegister = false
    @State private var isLoading = false
    @State private var errorMessage: String?
    @State private var showsPassword = false
    /// The password was hidden again while it was being typed; see `undoSecureWipe`.
    @State private var rehidden = false
    /// Counts refused attempts: the capsules shake once for each.
    @State private var refusals = 0
    /// Counts taps on the shuttlecock that came too early.
    @State private var tooSoon = 0
    /// Where a change of ink can start from (each line and the shuttlecock), in global coordinates.
    @State private var sources: [Spot: CGPoint] = [:]

    /// The page has made its entrance: the shuttlecock has dropped in from above.
    @State private var arrived = false

    @FocusState private var focus: Spot?
    @Namespace private var slide

    /// The curve the system keyboard moves on. What the page rearranges for the keyboard
    /// moves on the same one, so the two never pull against each other.
    private static let withKeyboard = Animation.interpolatingSpring(mass: 3, stiffness: 1000, damping: 500)

    private enum Spot: Hashable { case email, password, nickname, toy }
    private static let refusalID = "refusal"

    private var check: PassCheck { PassCheck(email: email, password: password, isRegister: isRegister) }
    private var isComplete: Bool { check.missing == nil }
    /// The light the page shows. A refused attempt is red whatever the form says.
    private var light: PassCheck.Light { errorMessage == nil ? check.light : .closed }

    var body: some View {
        GeometryReader { viewport in
            ScrollViewReader { reader in
            ScrollView {
                VStack(spacing: 0) {
                    Spacer(minLength: 0)
                    hero(in: viewport.size)
                    Group {
                        modes
                            .padding(.top, focus == nil ? AppSpacing.xl : AppSpacing.sm)
                        capsules
                            .padding(.top, AppSpacing.md)
                    }
                    // The form rises into place under the shuttlecock as it lands.
                    .opacity(arrived ? 1 : 0)
                    .offset(y: arrived ? 0 : 22)
                    // While an attempt is in the air the form is what was sent; it can't be edited
                    // or switched until the answer is back.
                    .allowsHitTesting(!isLoading)
                    if let errorMessage {
                        Text(errorMessage)
                            .font(.system(.callout, weight: .semibold))
                            .foregroundStyle(Color.ink)
                            .multilineTextAlignment(.center)
                            .fixedSize(horizontal: false, vertical: true)
                            .padding(.top, AppSpacing.md)
                            .transition(.opacity)
                            .accessibilityLabel("没通过：\(errorMessage)")
                            // Room under the line, so scrolling to it leaves it clear of the edge.
                            .padding(.bottom, AppSpacing.md)
                            .id(Self.refusalID)
                    }
                    Spacer(minLength: 0)
                }
                .frame(maxWidth: .infinity)
                .padding(.horizontal, AppSpacing.lg)
                .padding(.vertical, AppSpacing.md)
                // A screenful at least, so the column sits in the middle of whatever height
                // the keyboard leaves.
                .frame(minHeight: viewport.size.height)
                // A tap on bare ink puts the keyboard away.
                .contentShape(Rectangle())
                .onTapGesture { focus = nil }
            }
            .scrollDismissesKeyboard(.interactively)
            .scrollBounceBehavior(.basedOnSize)
            // On a short screen the sign-up form fills the page and the reason for a refusal
            // lands below its edge. Bring it into view: it is the only thing that says why.
            .onChange(of: errorMessage) { _, message in
                guard message != nil else { return }
                Task { @MainActor in
                    // After the line has been laid out; before that there is nothing to scroll to.
                    try? await Task.sleep(for: .milliseconds(160))
                    withAnimation(.smooth(duration: 0.35)) { reader.scrollTo(Self.refusalID, anchor: .bottom) }
                }
            }
            }
        }
        .tint(Color.ink)
        // The new ink spreads from the line being written on, or from the shuttlecock when
        // the change came from serving it.
        .background { SignalField(ink: light.ink) { sources[focus ?? .toy] } }
        .animation(AppAnimation.spring, value: isRegister)
        .animation(Self.withKeyboard, value: focus)
        .animation(AppAnimation.standard, value: errorMessage)
        // A refusal answers what was sent. Once any of it changes, it no longer applies.
        .onChange(of: email) { errorMessage = nil }
        .onChange(of: password) { old, new in
            errorMessage = nil
            undoSecureWipe(old: old, new: new)
        }
        .onChange(of: focus) { _, spot in if spot != .password { rehidden = false } }
        .onChange(of: nickname) { errorMessage = nil }
        .onChange(of: light) { old, new in
            // The colour carries the state; say it for someone who can't see the colour.
            guard new.rawValue > old.rawValue else { return }
            let message = new == .open ? (isRegister ? "可以注册了" : "可以登录了") : "还差一项"
            AccessibilityNotification.Announcement(message).post()
        }
        .sensoryFeedback(trigger: light) { old, new in
            guard new.rawValue > old.rawValue else { return nil }
            return new == .open ? .success : .impact(flexibility: .soft)
        }
        .sensoryFeedback(.error, trigger: refusals)
        .onAppear {
            applyDemoState()
            guard !arrived else { return }
            if reduceMotion {
                arrived = true
            } else {
                withAnimation(.spring(response: 0.6, dampingFraction: 0.8).delay(0.1)) { arrived = true }
            }
        }
    }

    // MARK: - Shuttlecock

    /// The shuttlecock standing in front of the wordmark, which runs nearly edge to edge
    /// behind it. While the keyboard is up the wordmark goes and the shuttlecock shrinks.
    private func hero(in viewport: CGSize) -> some View {
        let roomy = min(viewport.width * 0.84, viewport.height * 0.46, 350)
        let typing = focus != nil
        // Whole points, so the shuttlecock's edge sits on the pixel grid.
        let side = floor(typing ? min(roomy, max(110, viewport.height * 0.36)) : roomy)
        return toy(side: side, drop: viewport.height + side)
            // Its cork comes down over the tops of the letters: it stands in front of the word.
            .padding(.bottom, typing ? 0 : side * 0.1)
            .background(alignment: .bottom) {
                if !typing {
                    wordmark(size: min(viewport.width * 0.275, 116))
                        .opacity(arrived ? 1 : 0)
                        .transition(.opacity)
                }
            }
    }

    private func toy(side: CGFloat, drop: CGFloat) -> some View {
        // Off the top of the screen: served and being checked, or not yet dropped in.
        let away = isLoading || !arrived
        return PlushShuttlecockView(fluff: fluff, eager: isComplete && !isLoading,
                                    refusals: refusals + tooSoon, served: away, onTap: advance)
            .frame(width: side, height: side)
            // Leaving, it waits a beat (the model is winding up) and then accelerates away.
            // Coming back, refused or arriving for the first time, it drops in and settles.
            // With Reduce Motion on it stays where it is and fades instead.
            .offset(y: away && !reduceMotion ? -drop : 0)
            .rotationEffect(.degrees(away && !reduceMotion ? 30 : 0))
            .opacity(away && reduceMotion ? 0 : 1)
            .animation(reduceMotion ? .easeInOut(duration: 0.25)
                       : away ? .easeIn(duration: 0.36).delay(0.09) : .spring(response: 0.6, dampingFraction: 0.6),
                       value: away)
            .onGeometryChange(for: CGPoint.self) { proxy in
                let frame = proxy.frame(in: .global)
                return CGPoint(x: frame.midX, y: frame.midY)
            } action: { point in
                sources[.toy] = point
            }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(isRegister ? "注册" : "登录")
            .accessibilityValue(isComplete ? "可以了" : "还没填完")
            .accessibilityAddTraits(.isButton)
            .accessibilityAction(.default, advance)
    }

    /// How fluffed up the shuttlecock is: it follows the light.
    private var fluff: Double {
        switch light {
        case .closed: return 0
        case .almost: return 0.5
        case .open:   return 1
        }
    }

    // MARK: - Masthead

    private func wordmark(size: CGFloat) -> some View {
        (Text("Shuttl").foregroundColor(.ink) + Text(".").foregroundColor(.card))
            .font(.system(size: size, weight: .black, design: .serif).italic())
            .kerning(-size * 0.02)
            .lineLimit(1)
            .minimumScaleFactor(0.5)
            .accessibilityLabel("Shuttl")
            .accessibilityAddTraits(.isHeader)
    }

    /// 登录 and 注册 in one ink capsule, the one in use on a card that slides between them:
    /// the tab bar's own switch, so the page already speaks the app's language.
    private var modes: some View {
        HStack(spacing: 0) {
            mode("登录", register: false, spoken: "已有账号？登录")
            mode("注册", register: true, spoken: "还没有账号？注册")
        }
        .padding(4)
        .background(Color.ink, in: Capsule())
        // The card can be pushed across as well as tapped.
        .gesture(DragGesture(minimumDistance: 12).onEnded { drag in
            if abs(drag.translation.width) > 14 { choose(register: drag.translation.width > 0) }
        })
        .sensoryFeedback(.selection, trigger: isRegister)
    }

    private func choose(register: Bool) {
        // Not while an attempt is in the air: its answer belongs to the form that sent it.
        guard isRegister != register, !isLoading else { return }
        withAnimation(AppAnimation.bouncy) {
            isRegister = register
            errorMessage = nil
        }
    }

    private func mode(_ title: String, register: Bool, spoken: String) -> some View {
        let active = isRegister == register
        return Button {
            choose(register: register)
        } label: {
            Text(title)
                .font(.system(size: 17, weight: .bold))
                .foregroundStyle(active ? Color.ink : Color.card)
                .frame(width: 84, height: 38)
                .background {
                    if active {
                        Capsule().fill(Color.card).matchedGeometryEffect(id: "mode", in: slide)
                    }
                }
                .contentShape(Capsule())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(spoken)
        .accessibilityAddTraits(active ? [.isSelected] : [])
    }

    // MARK: - Capsules

    private var capsules: some View {
        VStack(spacing: AppSpacing.sm + 2) {
            emailCapsule
            passwordCapsule
            if isRegister {
                nicknameCapsule
                    .transition(.move(edge: .top).combined(with: .opacity))
            }
        }
        .frame(maxWidth: 320)
        .modifier(Shake(animatableData: CGFloat(refusals)))
        .animation(.easeOut(duration: 0.45), value: refusals)
    }

    private var emailCapsule: some View {
        capsule("envelope.fill", empty: email.isEmpty, spot: .email, progress: check.emailOK ? 1 : 0) {
            TextField("", text: $email)
                // The user's own address in the wordmark's face.
                .font(.system(size: 19, weight: .bold, design: .serif).italic())
                .keyboardType(.emailAddress)
                .textInputAutocapitalization(.never)
                .autocorrectionDisabled()
                .textContentType(.emailAddress)
                .focused($focus, equals: .email)
                .submitLabel(.next)
                .onSubmit { focus = .password }
                .accessibilityLabel("邮箱地址")
                .accessibilityIdentifier("邮箱地址")
                .accessibilityHint(email.isEmpty || check.emailOK ? "" : "需要完整的邮箱地址，例如 name@example.com")
        }
    }

    private var passwordCapsule: some View {
        // A new password's outline goes round one step per character it needs.
        let needed = PassCheck.newPasswordLength
        let progress = isRegister ? Double(min(password.count, needed)) / Double(needed) : (check.passwordOK ? 1 : 0)
        return capsule("lock.fill", empty: password.isEmpty, spot: .password, progress: progress) {
            Group {
                if showsPassword {
                    TextField("", text: $password)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                } else {
                    SecureField("", text: $password)
                }
            }
            .font(.system(size: 19, weight: .bold))
            .textContentType(passwordKind)
            .focused($focus, equals: .password)
            .submitLabel(isRegister ? .next : .go)
            .onSubmit { if isRegister { focus = .nickname } else { advance() } }
            .accessibilityLabel("密码")
            .accessibilityIdentifier("密码")
            .accessibilityHint(isRegister ? "至少 \(needed) 位" : "")
            .overlay(alignment: .trailing) {
                // Nothing to show or hide until something is written.
                if !password.isEmpty {
                    Button(action: togglePasswordVisibility) {
                        Image(systemName: showsPassword ? "eye.slash.fill" : "eye.fill")
                            .font(.system(size: 15, weight: .semibold))
                            .foregroundStyle(progress >= 1 ? Color.card : Color.ink)
                            .contentTransition(.symbolEffect(.replace))
                            .frame(width: 44, height: 44)
                            .contentShape(Rectangle())
                    }
                    .buttonStyle(ScaleButtonStyle())
                    .offset(x: 40)
                    .transition(.scale(scale: 0.5).combined(with: .opacity))
                    .accessibilityLabel(showsPassword ? "隐藏密码" : "显示密码")
                }
            }
            .animation(AppAnimation.springFast, value: password.isEmpty)
        }
    }

    /// What the password field tells the system it is. A new password lets Keychain offer
    /// to make a strong one and takes over the field to do it; the demo has no account to
    /// keep one for.
    private var passwordKind: UITextContentType {
        #if DEBUG
        if DemoMode.isOn { return .password }
        #endif
        return isRegister ? .newPassword : .password
    }

    private var nicknameCapsule: some View {
        capsule("person.fill", empty: nickname.isEmpty, spot: .nickname, progress: nickname.isEmpty ? 0 : 1,
                required: false) {
            TextField("", text: $nickname)
                .font(.system(size: 19, weight: .bold))
                .textContentType(.nickname)
                .focused($focus, equals: .nickname)
                .submitLabel(.go)
                .onSubmit(advance)
                .accessibilityLabel("你的球场名号")
                .accessibilityIdentifier("你的球场名号")
                .accessibilityHint("可以不填")
        }
    }

    /// A field, named by a glyph: in the middle of the capsule while it is empty and idle,
    /// at its left edge once it is being written in.
    ///
    /// `progress` runs 0…1. Below 1 the capsule is an outline, with a heavier stroke drawn
    /// round that fraction of it; at 1 ink floods it from the middle and the writing is
    /// reversed out. A field that may stay empty is never "unfinished": it has no outline to
    /// complete, only a faint fill.
    private func capsule<Input: View>(_ symbol: String, empty: Bool, spot: Spot, progress: Double,
                                      required: Bool = true, @ViewBuilder input: () -> Input) -> some View {
        let solid = progress >= 1
        let focused = focus == spot
        let waiting = empty && !focused
        return ZStack {
            Image(systemName: symbol)
                .font(.system(size: 17, weight: .heavy))
                .foregroundStyle(solid ? Color.card : Color.ink)
                .frame(maxWidth: .infinity, alignment: waiting ? .center : .leading)
                .allowsHitTesting(false)
                .accessibilityHidden(true)
            input()
                .foregroundStyle(solid ? Color.card : Color.ink)
                .tint(solid ? Color.card : Color.ink)
                .multilineTextAlignment(.center)
                // Clear of the glyph on the left, and as much on the right to stay centred.
                .padding(.horizontal, 30)
        }
        .padding(.horizontal, 22)
        .frame(maxWidth: .infinity)
        .frame(height: 58)
        .background {
            ZStack {
                if !required { Capsule().fill(Color.ink.opacity(0.12)) }
                // The fill spreads from the middle to both ends.
                Capsule().fill(Color.ink).scaleEffect(x: solid ? 1 : 0, y: 1)
            }
            .clipShape(Capsule())
        }
        .overlay {
            if required && !solid {
                Capsule().strokeBorder(Color.ink, lineWidth: focused ? 3 : 2)
                Capsule()
                    .inset(by: 2.5)
                    .trim(from: 0, to: progress)
                    .stroke(Color.ink, style: StrokeStyle(lineWidth: 5, lineCap: .round))
            }
        }
        // The capsule being written in comes forward a little.
        .scaleEffect(focused ? 1.025 : 1)
        .animation(.spring(response: 0.34, dampingFraction: 0.8), value: progress)
        .animation(AppAnimation.springFast, value: focused)
        .animation(.spring(response: 0.36, dampingFraction: 0.78), value: waiting)
        .contentShape(Capsule())
        .onTapGesture { focus = spot }
        .onGeometryChange(for: CGPoint.self) { proxy in
            let frame = proxy.frame(in: .global)
            return CGPoint(x: frame.midX, y: frame.midY)
        } action: { point in
            sources[spot] = point
        }
    }

    // MARK: - Actions

    /// The shuttlecock and Return on the keyboard do the same thing: the next useful step.
    /// That is the field still missing, or serving the form when none is.
    private func advance() {
        guard !isLoading else { return }
        switch check.missing {
        case .email?, .emailAt?, .emailDomain?:
            tooSoon += 1
            focus = .email
        case .password?, .passwordLength?:
            tooSoon += 1
            focus = .password
        case nil:
            submit()
        }
    }

    /// Swapping the secure field for a plain one drops the keyboard; put it back.
    private func togglePasswordVisibility() {
        let wasTyping = focus == .password
        showsPassword.toggle()
        if wasTyping {
            Task { @MainActor in
                focus = .password
                rehidden = !showsPassword
            }
        }
    }

    /// A secure field that takes focus again wipes itself on the next keystroke: the one
    /// character typed, or nothing at all after a delete, replaces everything in it. After a
    /// show-and-hide nobody asked for that, so the first such wipe is undone.
    ///
    /// It is undone here, inside the change itself, on purpose. Two gentler-looking ways were
    /// tried and both lose characters when typing is fast: putting the text back on the next
    /// run-loop turn races the following keystroke, and repairing it in the field's binding
    /// leaves the field showing its own wiped text. SwiftUI logs "onChange action tried to
    /// update multiple times per frame" for this; the second call it skips is not needed.
    private func undoSecureWipe(old: String, new: String) {
        guard rehidden else { return }
        rehidden = false
        if new.isEmpty, old.count > 1 {
            password = String(old.dropLast())
        } else if new.count == 1, !old.isEmpty {
            password = old + new
        }
    }

    private func submit() {
        focus = nil
        errorMessage = nil
        isLoading = true

        Task { @MainActor in
            defer { isLoading = false }
            do {
                #if DEBUG
                if DemoMode.isOn {
                    // The demo has no server to ask: every serve comes back.
                    try await Task.sleep(for: .seconds(1.1))
                    throw DemoRefusal()
                }
                #endif
                if isRegister {
                    let name = nickname.trimmingCharacters(in: .whitespaces)
                    try await auth.register(email: check.trimmedEmail, password: password,
                                            nickname: name.isEmpty ? "球友" : name)
                } else {
                    try await auth.login(email: check.trimmedEmail, password: password)
                }
            } catch {
                errorMessage = error.localizedDescription
                refusals += 1
                AccessibilityNotification.Announcement("没通过：\(error.localizedDescription)").post()
            }
        }
    }

    private func applyDemoState() {
        #if DEBUG
        if DemoMode.loginRegisters { isRegister = true }
        if DemoMode.loginFill >= 1 { email = "player@shuttl.app" }
        if DemoMode.loginFill >= 2 { password = DemoMode.loginRegisters ? "smash" : "smash-2026" }
        if DemoMode.loginFill >= 3 { password = "smash-2026" }
        if DemoMode.showsLoginErrors {
            isRegister = true
            email = "player@shuttl.app"
            password = "smash-2026"
            // After the fields: editing them clears the refusal.
            Task { @MainActor in errorMessage = "该邮箱已被注册，换一个试试？" }
        }
        #endif
    }
}

#if DEBUG
/// What the demo answers to every attempt.
private struct DemoRefusal: LocalizedError {
    var errorDescription: String? { "邮箱或密码不对" }
}
#endif

// MARK: - PassCheck
// What the form still needs. Plain values in, plain values out, so the rules the page shows
// (which thing is missing, which light is on) can be tested without a screen.

struct PassCheck: Equatable {
    var email: String
    var password: String
    var isRegister: Bool

    /// A new password must be at least this long; signing in accepts whatever was set.
    static let newPasswordLength = 8

    /// The first thing that stops the form from being complete.
    enum Missing: Equatable {
        case email
        /// Something is typed, but there is no @ in it.
        case emailAt
        /// There is an @, but not a name before it and a dotted domain after it.
        case emailDomain
        case password
        /// A new password that is `short` characters under the minimum.
        case passwordLength(short: Int)
    }

    /// How many of the two things (email, password) are right.
    enum Light: Int, CaseIterable {
        case closed, almost, open
    }

    /// The email as it is sent: autocomplete likes to leave a space after it.
    var trimmedEmail: String { email.trimmingCharacters(in: .whitespacesAndNewlines) }

    var emailOK: Bool {
        let parts = trimmedEmail.split(separator: "@", omittingEmptySubsequences: false)
        guard parts.count == 2, !parts[0].isEmpty,
              !trimmedEmail.contains(where: \.isWhitespace) else { return false }
        let labels = parts[1].split(separator: ".", omittingEmptySubsequences: false)
        return labels.count >= 2 && labels.allSatisfy { !$0.isEmpty }
    }

    var passwordOK: Bool {
        isRegister ? password.count >= Self.newPasswordLength : !password.isEmpty
    }

    var missing: Missing? {
        if trimmedEmail.isEmpty { return .email }
        if !trimmedEmail.contains("@") { return .emailAt }
        if !emailOK { return .emailDomain }
        if password.isEmpty { return .password }
        if !passwordOK { return .passwordLength(short: Self.newPasswordLength - password.count) }
        return nil
    }

    var light: Light {
        switch (emailOK, passwordOK) {
        case (true, true):   return .open
        case (false, false): return .closed
        default:             return .almost
        }
    }
}

private extension PassCheck.Light {
    /// Tomato, butter, pistachio: the inks a match card uses for failed, in progress, done.
    var ink: Color {
        switch self {
        case .closed: return .tomato
        case .almost: return .butter
        case .open:   return .pistachio
        }
    }
}

// MARK: - Signal field
// The page's ink, edge to edge. A change doesn't cut or fade: the new ink spreads out as a
// disc from where the change was caused, so you see what you did turn the light.

private struct SignalField: View {
    let ink: Color
    /// Where the change was caused, in global coordinates. Read at the moment the ink changes.
    let source: () -> CGPoint?

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var settled: Color
    @State private var spread: Spread?

    private struct Spread {
        let id = UUID()
        let ink: Color
        let centre: CGPoint
    }

    init(ink: Color, source: @escaping () -> CGPoint?) {
        self.ink = ink
        self.source = source
        _settled = State(initialValue: ink)
    }

    var body: some View {
        GeometryReader { geo in
            let frame = geo.frame(in: .global)
            ZStack {
                settled
                if let spread {
                    SpreadingDisc(ink: spread.ink, centre: spread.centre,
                                  diameter: 2 * hypot(frame.width, frame.height)) {
                        // Only the newest spread settles; an older one was overtaken.
                        if self.spread?.id == spread.id {
                            settled = spread.ink
                            self.spread = nil
                        }
                    }
                    .id(spread.id)
                }
            }
            .onChange(of: ink) { _, new in
                if reduceMotion {
                    spread = nil
                    withAnimation(.easeInOut(duration: 0.25)) { settled = new }
                    return
                }
                // A change that lands mid-spread starts from the ink that was arriving.
                if let spread { settled = spread.ink }
                let origin = source() ?? CGPoint(x: frame.midX, y: frame.midY)
                spread = Spread(ink: new, centre: CGPoint(x: origin.x - frame.minX, y: origin.y - frame.minY))
            }
        }
        .paperGrain()
        .ignoresSafeArea()
    }
}

private struct SpreadingDisc: View {
    let ink: Color
    let centre: CGPoint
    let diameter: CGFloat
    let onCovered: () -> Void

    @State private var reach: CGFloat = 0.001

    var body: some View {
        Circle()
            .fill(ink)
            .frame(width: diameter, height: diameter)
            .scaleEffect(reach)
            .position(centre)
            .onAppear {
                withAnimation(.easeOut(duration: 0.55)) { reach = 1 } completion: { onCovered() }
            }
    }
}

/// A quick side-to-side shake: one for each whole step of `animatableData`.
private struct Shake: GeometryEffect {
    var travel: CGFloat = 7
    var animatableData: CGFloat

    func effectValue(size: CGSize) -> ProjectionTransform {
        ProjectionTransform(CGAffineTransform(translationX: travel * sin(animatableData * .pi * 3), y: 0))
    }
}

// MARK: - Preview

#Preview("LoginView") {
    LoginView()
        .environment(AuthService())
}
