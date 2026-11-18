import XCTest

/// One walk through every screen in demo mode (`-UIDemoMode`: seeded matches, no backend, no
/// real camera). Each stop checks that it arrived; the point of the walk is that nothing on
/// the way crashes, hangs, or strands the user on a screen with no way back.
final class AppTourUITests: XCTestCase {
    private var app: XCUIApplication!

    override func setUpWithError() throws {
        continueAfterFailure = false
        app = XCUIApplication()
        app.launchArguments += ["-UIDemoMode", "-UIDemoTab", "matches"]
        app.launch()
        XCTAssertTrue(tab("比赛").waitForExistence(timeout: 20), "主界面没有出现")
    }

    private func tab(_ name: String) -> XCUIElement { app.buttons[name] }

    private func arrive(_ element: XCUIElement, _ what: String, file: StaticString = #filePath, line: UInt = #line) {
        XCTAssertTrue(element.waitForExistence(timeout: 8), "没有到达：\(what)", file: file, line: line)
        XCTAssertEqual(app.state, .runningForeground, "App 不在前台：\(what)", file: file, line: line)
    }

    private func back() {
        let button = app.navigationBars.buttons.firstMatch
        XCTAssertTrue(button.waitForExistence(timeout: 5), "没有返回按钮")
        button.tap()
    }

    func testWalkEveryScreen() {
        // 比赛 → the finished match that was analysed on this phone (2:49 long in the demo)
        let card = app.buttons.matching(NSPredicate(format: "label CONTAINS %@", "2:49")).firstMatch
        arrive(card, "比赛列表里的已完成比赛")
        card.tap()
        arrive(app.buttons["开始回放"], "比赛详情")

        // the four result tabs, forwards and back again
        for name in ["落点", "回合", "移动", "概览", "回合"] {
            let segment = app.buttons[name]
            arrive(segment, "结果分段「\(name)」")
            segment.tap()
        }

        // a rally's sheet, opened and put away
        let rally = app.buttons.matching(NSPredicate(format: "label BEGINSWITH %@", "回合 1，")).firstMatch
        arrive(rally, "回合列表第一行")
        rally.tap()
        arrive(app.buttons["回放这一分"], "回合详情")
        app.swipeDown(velocity: .fast)
        XCTAssertTrue(app.buttons["回放这一分"].waitForNonExistence(timeout: 5), "回合详情收不起来")

        // replay: play, step a rally, pause, leave
        app.buttons["开始回放"].tap()
        arrive(app.buttons["下一分"], "回放页")
        app.buttons["播放"].tap()
        app.buttons["下一分"].tap()
        arrive(app.buttons["暂停"], "回放播放中")
        app.buttons["暂停"].tap()
        app.buttons["返回"].tap()
        arrive(app.buttons["开始回放"], "从回放回到详情")

        // back to the list, then the other kinds of match page: one still being analysed,
        // and one analysed on the server (55:15 long), which has its own sections
        back()
        arrive(card, "从详情回到列表")
        for (word, landmark, stop) in [("分析中", "找羽毛球", "分析中的比赛"), ("55:15", "回合记分卡", "服务器分析的比赛")] {
            let other = app.buttons.matching(NSPredicate(format: "label CONTAINS %@", word)).firstMatch
            arrive(other, "列表里\(stop)")
            other.tap()
            let mark = app.descendants(matching: .any).matching(NSPredicate(format: "label CONTAINS %@", landmark)).firstMatch
            arrive(mark, stop)
            back()
            arrive(card, "从\(stop)回到列表")
        }

        // 统计 → 关于与致谢 → back
        tab("统计").tap()
        let about = app.buttons.matching(NSPredicate(format: "label CONTAINS %@", "关于与致谢")).firstMatch
        arrive(about, "统计页底部的关于入口")
        // Scroll until the link is clear of the floating tab bar, which would take the tap.
        for _ in 0..<6 where about.frame.maxY > tab("统计").frame.minY - 8 { app.swipeUp() }
        about.tap()
        arrive(app.staticTexts["羽毛球检测模型"], "关于页")
        back()
        arrive(tab("统计"), "从关于回到统计")

        // 录制, then round the tabs quickly: the page under the bar has to keep up
        tab("录制").tap()
        arrive(tab("录制"), "录制页")
        for name in ["比赛", "统计", "录制", "比赛", "统计", "比赛"] { tab(name).tap() }
        arrive(card, "连续切换标签之后的比赛列表")
    }
}

/// The record page with a take running (`-UIDemoRecording`: no real capture). Stopping it has
/// to say what became of the take, and offer the way to its progress.
final class RecordingFlowUITests: XCTestCase {
    func testStoppingATakeSaysItWasSavedAndLeadsToItsProgress() {
        let app = XCUIApplication()
        app.launchArguments += ["-UIDemoMode", "-UIDemoTab", "record", "-UIDemoRecording"]
        app.launch()

        let stop = app.buttons["停止录制"]
        XCTAssertTrue(stop.waitForExistence(timeout: 20), "录制页没有处在录制状态")
        stop.tap()

        let progress = app.buttons["查看进度"]
        XCTAssertTrue(progress.waitForExistence(timeout: 5), "停止录制后没有出现「已保存」的提示")
        let screen = app.windows.firstMatch.frame
        XCTAssertTrue(screen.contains(progress.frame), "「查看进度」超出屏幕：\(progress.frame)")
        progress.tap()
        let card = app.buttons.matching(NSPredicate(format: "label CONTAINS %@", "2:49")).firstMatch
        XCTAssertTrue(card.waitForExistence(timeout: 8), "「查看进度」没有带到比赛页")
    }
}
