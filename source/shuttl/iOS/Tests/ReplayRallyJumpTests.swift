import XCTest
@testable import Shuttl

/// ⏮ / ⏭ on the replay screen: which rally each one goes to from a given frame.
final class ReplayRallyJumpTests: XCTestCase {
    /// Three rallies starting at these frames. At 60 fps the 2 s restart margin is 120 frames.
    private let starts = [270, 1_200, 2_400]
    private let margin = 120

    private func target(_ frame: Int, forward: Bool) -> Int? {
        ReplayViewModel.rallyJumpTarget(starts: starts, frame: frame, forward: forward, restartMargin: margin)
    }

    func testNextBeforeTheFirstRallyGoesToTheFirst() {
        XCTAssertEqual(target(0, forward: true), 0)
        XCTAssertEqual(target(269, forward: true), 0)
    }

    func testNextGoesToTheRallyAfterTheCurrentOne() {
        XCTAssertEqual(target(270, forward: true), 1)
        XCTAssertEqual(target(900, forward: true), 1)      // in the gap after rally 0
        XCTAssertEqual(target(1_200, forward: true), 2)
    }

    func testNextHasNowhereToGoFromTheLastRally() {
        XCTAssertNil(target(2_400, forward: true))
        XCTAssertNil(target(9_999, forward: true))
    }

    func testBackBeforeTheFirstRallyHasNowhereToGo() {
        XCTAssertNil(target(0, forward: false))
        XCTAssertNil(target(269, forward: false))
    }

    func testBackJustAfterARallyStartsGoesToTheOneBefore() {
        XCTAssertEqual(target(1_200, forward: false), 0)
        XCTAssertEqual(target(1_320, forward: false), 0)   // exactly the margin still counts as "just started"
        XCTAssertNil(target(270, forward: false))          // the first rally has nothing before it
    }

    func testBackWellIntoARallyReplaysIt() {
        XCTAssertEqual(target(1_321, forward: false), 1)
        XCTAssertEqual(target(391, forward: false), 0)
        XCTAssertEqual(target(9_999, forward: false), 2)
    }

    func testNoRallies() {
        XCTAssertNil(ReplayViewModel.rallyJumpTarget(starts: [], frame: 100, forward: true, restartMargin: margin))
        XCTAssertNil(ReplayViewModel.rallyJumpTarget(starts: [], frame: 100, forward: false, restartMargin: margin))
    }

    /// `jumpRally` seeks to the middle of the rally's first frame. Truncated back to a frame
    /// index (as the buttons and the score slip do), that must be the rally it aimed at, at
    /// any frame rate, and pressing ⏮ straight afterwards must leave it rather than restart it.
    func testAJumpLandsInsideTheRallyItAimedAt() {
        for fps in [30.0, 59.94, 60.0] {
            for (index, start) in starts.enumerated() {
                let frame = Int((Double(start) + 0.5) / fps * fps)
                XCTAssertEqual(frame, start, "fps \(fps)")
                XCTAssertEqual(starts.lastIndex { $0 <= frame }, index, "fps \(fps)")
                XCTAssertEqual(target(frame, forward: false), index > 0 ? index - 1 : nil, "fps \(fps)")
            }
        }
    }

    func testClock() {
        XCTAssertEqual(ReplayViewModel.clock(0), "0:00")
        XCTAssertEqual(ReplayViewModel.clock(59.9), "0:59")
        XCTAssertEqual(ReplayViewModel.clock(169.4), "2:49")
        XCTAssertEqual(ReplayViewModel.clock(.nan), "0:00")
        XCTAssertEqual(ReplayViewModel.clock(-3), "0:00")
    }

    // MARK: Pressing play when there is nothing left to play

    func testPlayCarriesOnFromTheMiddle() {
        XCTAssertNil(ReplayViewModel.restartTime(current: 12, duration: 60, lastRallyEnd: nil, firstRallyStart: nil))
        XCTAssertNil(ReplayViewModel.restartTime(current: 12, duration: 60, lastRallyEnd: 50, firstRallyStart: 3))
    }

    func testPlayAtTheEndStartsOver() {
        XCTAssertEqual(ReplayViewModel.restartTime(current: 60, duration: 60, lastRallyEnd: nil, firstRallyStart: nil), 0)
        XCTAssertEqual(ReplayViewModel.restartTime(current: 59.97, duration: 60, lastRallyEnd: nil, firstRallyStart: nil), 0)
        // With 只看回合 on, "over" is the first rally, not the walk onto court before it.
        XCTAssertEqual(ReplayViewModel.restartTime(current: 60, duration: 60, lastRallyEnd: 50, firstRallyStart: 3), 3)
    }

    func testPlayPastTheLastRallyStartsOverWhenOnlyRalliesPlay() {
        XCTAssertEqual(ReplayViewModel.restartTime(current: 55, duration: 60, lastRallyEnd: 50, firstRallyStart: 3), 3)
    }

    func testAnUnknownDurationNeverRestarts() {
        XCTAssertNil(ReplayViewModel.restartTime(current: 5, duration: 0, lastRallyEnd: nil, firstRallyStart: nil))
        XCTAssertNil(ReplayViewModel.restartTime(current: 5, duration: .nan, lastRallyEnd: nil, firstRallyStart: nil))
    }
}
