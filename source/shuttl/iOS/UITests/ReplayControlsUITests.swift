import XCTest

/// Replay controls, driven in demo mode (`-UIDemoMode`: seeded matches, no backend, no camera).
/// The seeded take has 14 rallies and opens paused at 0:00, before the first one.
final class ReplayControlsUITests: XCTestCase {
    private var app: XCUIApplication!

    override func setUpWithError() throws {
        continueAfterFailure = false
        app = XCUIApplication()
        app.launchArguments += ["-UIDemoMode", "-UIDemoTab", "matches", "-UIDemoOpenMatch", "-UIDemoOpenReplay"]
        app.launch()
        XCTAssertTrue(app.buttons["下一分"].waitForExistence(timeout: 20), "回放页没有打开")
    }

    /// The score slip reads "第 NN 回合，近端 a 比远端 b".
    private var rallyNumber: Int? {
        let slip = app.descendants(matching: .any)
            .matching(NSPredicate(format: "label BEGINSWITH %@", "第 ")).firstMatch
        guard slip.exists else { return nil }
        return Int(slip.label.dropFirst(2).prefix(2))
    }

    /// The scrubber's value is the playhead as m:ss.
    private var playheadSeconds: Int? {
        guard let text = app.descendants(matching: .any)["播放进度"].value as? String else { return nil }
        let parts = text.split(separator: ":").compactMap { Int($0) }
        return parts.count == 2 ? parts[0] * 60 + parts[1] : nil
    }

    /// Nothing in the top bar or the control deck may hang off the edge of the screen.
    func testControlsStayOnScreen() {
        let screen = app.windows.firstMatch.frame
        for label in ["返回", "只看回合", "上一分", "下一分", "播放"] {
            let frame = app.buttons[label].frame
            XCTAssertFalse(frame.isEmpty, "找不到「\(label)」")
            XCTAssertTrue(screen.contains(frame), "「\(label)」超出屏幕：\(frame) 不在 \(screen) 内")
        }
    }

    func testStepThroughRallies() {
        let next = app.buttons["下一分"], back = app.buttons["上一分"]
        XCTAssertFalse(back.isEnabled, "第一分开始之前，没有上一分可去")

        // ⏭ visits every rally once, in order, then has nowhere left to go.
        var seen: [Int] = []
        for _ in 0..<20 where next.isEnabled {
            next.tap()
            seen.append(rallyNumber ?? -1)
        }
        XCTAssertEqual(seen, Array(1...14))
        XCTAssertFalse(next.isEnabled)

        // ⏮ at the very start of a rally leaves it for the one before.
        XCTAssertTrue(back.isEnabled)
        back.tap()
        XCTAssertEqual(rallyNumber, 13)

        for _ in 0..<20 where back.isEnabled { back.tap() }
        XCTAssertEqual(rallyNumber, 1)
        XCTAssertTrue(next.isEnabled)
    }

    func testTapOnThePictureTogglesPlayback() {
        let picture = app.coordinate(withNormalizedOffset: CGVector(dx: 0.5, dy: 0.42))
        XCTAssertTrue(app.buttons["播放"].exists)
        picture.tap()
        XCTAssertTrue(app.buttons["暂停"].waitForExistence(timeout: 3), "点画面没有开始播放")
        picture.tap()
        XCTAssertTrue(app.buttons["播放"].waitForExistence(timeout: 3), "再点画面没有暂停")
    }

    func testRalliesOnlySwitchKeepsItsLabel() {
        let toggle = app.buttons["只看回合"]
        XCTAssertEqual(toggle.value as? String, "关")
        let widthOff = toggle.frame.width
        toggle.tap()
        XCTAssertEqual(toggle.value as? String, "开，自动跳过捡球时间")
        // Same label on and off, so the row does not shift when it flips.
        XCTAssertEqual(toggle.frame.width, widthOff, accuracy: 1)
    }

    func testDraggingTheScrubberMovesThePlayhead() {
        let scrubber = app.descendants(matching: .any)["播放进度"]
        XCTAssertTrue(scrubber.exists)
        XCTAssertEqual(playheadSeconds, 0)
        // The take is 2:49 long: 80 % of the way along is about 2:15.
        let from = scrubber.coordinate(withNormalizedOffset: CGVector(dx: 0.05, dy: 0.35))
        let to = scrubber.coordinate(withNormalizedOffset: CGVector(dx: 0.8, dy: 0.35))
        from.press(forDuration: 0.2, thenDragTo: to)
        let seconds = try? XCTUnwrap(playheadSeconds)
        XCTAssertNotNil(seconds)
        XCTAssertEqual(Double(seconds ?? 0), 135, accuracy: 12)
    }
}
