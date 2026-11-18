import XCTest
@testable import Shuttl

/// The sign-in page's rules: which thing is missing first, and which light is on.
final class PassCheckTests: XCTestCase {
    private func check(_ email: String, _ password: String, register: Bool = false) -> PassCheck {
        PassCheck(email: email, password: password, isRegister: register)
    }

    // MARK: Email

    func testEmailNeedsANameAnAtAndADottedDomain() {
        XCTAssertTrue(check("a@b.cn", "").emailOK)
        XCTAssertTrue(check("uitest_1763366400@shuttl.app", "").emailOK)
        XCTAssertTrue(check("first.last+tag@mail.example.com", "").emailOK)

        XCTAssertFalse(check("", "").emailOK)
        XCTAssertFalse(check("player.shuttl.app", "").emailOK)   // no @
        XCTAssertFalse(check("@shuttl.app", "").emailOK)         // nothing before it
        XCTAssertFalse(check("player@", "").emailOK)
        XCTAssertFalse(check("player@shuttl", "").emailOK)       // no dot in the domain
        XCTAssertFalse(check("player@shuttl.", "").emailOK)
        XCTAssertFalse(check("player@.app", "").emailOK)
        XCTAssertFalse(check("a@b@c.cn", "").emailOK)
        XCTAssertFalse(check("pla yer@shuttl.app", "").emailOK)
    }

    /// Autocomplete leaves a space after an address; it must neither block the form nor be sent.
    func testSpacesAroundTheEmailAreIgnored() {
        let c = check("  player@shuttl.app ", "x")
        XCTAssertTrue(c.emailOK)
        XCTAssertEqual(c.trimmedEmail, "player@shuttl.app")
        XCTAssertNil(c.missing)
    }

    // MARK: What is missing

    func testTheFirstMissingThingIsNamedInOrder() {
        XCTAssertEqual(check("", "").missing, .email)
        XCTAssertEqual(check("   ", "secret").missing, .email)
        XCTAssertEqual(check("player", "").missing, .emailAt)
        XCTAssertEqual(check("player@", "").missing, .emailDomain)
        XCTAssertEqual(check("player@shuttl", "secret").missing, .emailDomain)
        XCTAssertEqual(check("player@shuttl.app", "").missing, .password)
        XCTAssertNil(check("player@shuttl.app", "x").missing)
    }

    func testSigningInAcceptsAnyPasswordButANewOneNeedsEight() {
        XCTAssertTrue(check("a@b.cn", "x").passwordOK)
        XCTAssertFalse(check("a@b.cn", "x", register: true).passwordOK)

        XCTAssertEqual(check("a@b.cn", "", register: true).missing, .password)
        XCTAssertEqual(check("a@b.cn", "1", register: true).missing, .passwordLength(short: 7))
        XCTAssertEqual(check("a@b.cn", "1234567", register: true).missing, .passwordLength(short: 1))
        XCTAssertNil(check("a@b.cn", "12345678", register: true).missing)
    }

    // MARK: The light

    func testTheLightCountsHowManyOfTheTwoThingsAreRight() {
        XCTAssertEqual(check("", "").light, .closed)
        XCTAssertEqual(check("player", "").light, .closed)
        XCTAssertEqual(check("player@shuttl.app", "").light, .almost)
        XCTAssertEqual(check("", "secret").light, .almost)          // password first is one step too
        XCTAssertEqual(check("player@shuttl.app", "secret").light, .open)
        // The same input is one step short on 注册, where the password is too short.
        XCTAssertEqual(check("player@shuttl.app", "secret", register: true).light, .almost)
    }

    /// The page may only offer to submit when the light is green, and the other way round.
    func testGreenMeansNothingIsMissing() {
        let emails = ["", "player", "player@", "player@shuttl.app"]
        let passwords = ["", "1", "1234567", "12345678"]
        for register in [false, true] {
            for email in emails {
                for password in passwords {
                    let c = check(email, password, register: register)
                    XCTAssertEqual(c.light == .open, c.missing == nil,
                                   "email '\(email)' password '\(password)' register \(register)")
                }
            }
        }
    }
}
