import XCTest
@testable import ShuttlDesign

/// `Text(scorecard:)` sets numbers in one face and words in another. These pin down what
/// counts as a number.
final class ScorecardRunsTests: XCTestCase {
    private func split(_ s: String) -> [String] {
        Scorecard.runs(in: s).map { ($0.isFigure ? "#" : "") + $0.text }
    }

    func testADateIsNumbersWithChineseUnits() {
        XCTAssertEqual(split("9月27日"), ["#9", "月", "#27", "日"])
    }

    func testAClockKeepsItsColon() {
        XCTAssertEqual(split("单打 42:00"), ["单打 ", "#42:00"])
        XCTAssertEqual(split("1:02:03"), ["#1:02:03"])
    }

    func testDecimalsPercentAndTimesStayWithTheNumber() {
        XCTAssertEqual(split("0.5×"), ["#0.5×"])
        XCTAssertEqual(split("63% · 追踪球员"), ["#63%", " · 追踪球员"])
        XCTAssertEqual(split("平均 126"), ["平均 ", "#126"])
    }

    func testASignBelongsToTheNumberAfterIt() {
        XCTAssertEqual(split("+4"), ["#+4"])
        XCTAssertEqual(split("近端 - 远端"), ["近端 - 远端"])
    }

    func testPunctuationAfterANumberIsNotPartOfIt() {
        XCTAssertEqual(split("共 3 场。"), ["共 ", "#3", " 场。"])
        XCTAssertEqual(split("第 2 局: 开始"), ["第 ", "#2", " 局: 开始"])
        XCTAssertEqual(split("8."), ["#8", "."])
    }

    func testWordsAloneAndNothingAtAll() {
        XCTAssertEqual(split("还没有数据"), ["还没有数据"])
        XCTAssertEqual(split(""), [])
    }

    func testEveryCharacterComesBackOnceInOrder() {
        for s in ["9月27日", "回合 02 · 近端发球", "≈241 km/h", "2026年 周日 下午11:54", "3:2", "a1b22c333"] {
            XCTAssertEqual(Scorecard.runs(in: s).map(\.text).joined(), s)
        }
    }
}
