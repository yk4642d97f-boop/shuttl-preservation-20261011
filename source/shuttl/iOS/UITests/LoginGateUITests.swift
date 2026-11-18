import XCTest

/// The sign-in page, driven by typing and by handling the shuttlecock. `-UIDemoMode` without
/// a tab shows it signed out with an in-memory store, and in that mode the page asks no
/// server: every attempt is refused after a second, so nothing here leaves the simulator.
final class LoginGateUITests: XCTestCase {
    private var app: XCUIApplication!

    private var email: XCUIElement { app.textFields["邮箱地址"] }
    private var password: XCUIElement { app.secureTextFields["密码"] }
    /// The shuttlecock: the page's one button.
    private var shuttle: XCUIElement { app.buttons[app.buttons["注册"].exists ? "注册" : "登录"] }

    override func setUpWithError() throws {
        continueAfterFailure = false
        app = XCUIApplication()
        app.launchArguments += ["-UIDemoMode", "-UITestResetAuth"]
        app.launch()
        XCTAssertTrue(email.waitForExistence(timeout: 20), "登录页没有出现")
    }

    private func type(_ text: String, into field: XCUIElement) {
        XCTAssertTrue(field.waitForExistence(timeout: 5))
        field.tap()
        field.typeText(text)
    }

    private func wait(for element: XCUIElement, toHave format: String) {
        expectation(for: NSPredicate(format: format), evaluatedWith: element)
        waitForExpectations(timeout: 5)
    }

    func testTheShuttlecockIsReadyOnlyWhenTheFormIsComplete() {
        XCTAssertEqual(shuttle.value as? String, "还没填完")

        type("player@shuttl", into: email)
        XCTAssertEqual(shuttle.value as? String, "还没填完", "邮箱没写完")
        email.typeText(".app")
        XCTAssertEqual(shuttle.value as? String, "还没填完", "只有邮箱还不够")

        type("x", into: password)
        wait(for: shuttle, toHave: "value == '可以了'")

        // Taking the password away takes that back.
        password.typeText(XCUIKeyboardKey.delete.rawValue)
        wait(for: shuttle, toHave: "value == '还没填完'")
    }

    func testANewPasswordNeedsEightCharacters() {
        let toRegister = app.buttons["还没有账号？注册"]
        toRegister.tap()
        XCTAssertTrue(toRegister.isSelected)
        XCTAssertTrue(app.textFields["你的球场名号"].waitForExistence(timeout: 5))

        type("player@shuttl.app", into: email)
        type("1234567", into: password)
        XCTAssertEqual(app.buttons["注册"].value as? String, "还没填完", "7 位还不够")
        password.typeText("8")
        wait(for: app.buttons["注册"], toHave: "value == '可以了'")

        // Signing in has no length rule, so the same input is complete there too.
        app.buttons["已有账号？登录"].tap()
        wait(for: app.buttons["登录"], toHave: "value == '可以了'")
    }

    /// Tapped too early, the shuttlecock puts the cursor where something is missing.
    func testTappingTheShuttlecockEarlyGoesToWhatIsMissing() {
        shuttle.tap()
        wait(for: email, toHave: "hasKeyboardFocus == true")

        email.typeText("player@shuttl.app")
        shuttle.tap()
        wait(for: password, toHave: "hasKeyboardFocus == true")
    }

    /// Return on an incomplete form does the same.
    func testReturnGoesToWhatIsMissing() {
        type("secret\n", into: password)
        wait(for: email, toHave: "hasKeyboardFocus == true")
    }

    /// Served with a complete form, it leaves; refused, it comes back and the reason shows.
    func testAServeThatIsRefusedComesBack() {
        type("player@shuttl.app", into: email)
        type("secret", into: password)
        wait(for: shuttle, toHave: "value == '可以了'")
        shuttle.tap()

        let reason = app.staticTexts["没通过：邮箱或密码不对"]
        XCTAssertTrue(reason.waitForExistence(timeout: 6), "被拒之后没有显示原因")
        XCTAssertTrue(app.windows.firstMatch.frame.contains(shuttle.frame), "羽毛球没有回到屏幕里")

        // Changing what was sent clears the refusal.
        type("1", into: password)
        expectation(for: NSPredicate(format: "exists == false"), evaluatedWith: reason)
        waitForExpectations(timeout: 3)
    }

    /// The sign-up form is taller than a short screen. The reason for a refusal is the only
    /// thing on the page that says why, so it has to end up where it can be read.
    func testARefusedSignUpShowsItsReasonOnScreen() {
        app.buttons["还没有账号？注册"].tap()
        type("player@shuttl.app", into: email)
        type("12345678", into: password)
        wait(for: app.buttons["注册"], toHave: "value == '可以了'")
        app.buttons["注册"].tap()

        let reason = app.staticTexts["没通过：邮箱或密码不对"]
        XCTAssertTrue(reason.waitForExistence(timeout: 6), "被拒之后没有显示原因")
        let screen = app.windows.firstMatch.frame
        expectation(for: NSPredicate { _, _ in screen.contains(reason.frame) }, evaluatedWith: nil)
        waitForExpectations(timeout: 4)
    }

    /// The shuttlecock is a live 3-D scene, and a scene can be on screen, hittable, and
    /// blank. Look at the pixels: a fair share of its square must be pale fur.
    func testTheShuttlecockIsActuallyDrawn() throws {
        // Give the scene a moment to present its first frame.
        Thread.sleep(forTimeInterval: 1.5)
        let image = try XCTUnwrap(shuttle.screenshot().image.cgImage)
        let width = 60, height = 60
        var pixels = [UInt8](repeating: 0, count: width * height * 4)
        let context = try XCTUnwrap(CGContext(data: &pixels, width: width, height: height, bitsPerComponent: 8,
                                              bytesPerRow: width * 4, space: CGColorSpaceCreateDeviceRGB(),
                                              bitmapInfo: CGImageAlphaInfo.premultipliedLast.rawValue))
        context.draw(image, in: CGRect(x: 0, y: 0, width: width, height: height))
        var fur = 0
        for index in stride(from: 0, to: pixels.count, by: 4)
        where pixels[index] > 170 && pixels[index + 1] > 160 && pixels[index + 2] > 175 {
            fur += 1
        }
        let share = Double(fur) / Double(width * height)
        // Drawn, with its fur lying flat as it is on the red page, it measures about 10 %;
        // a blank scene measures 0.
        XCTAssertGreaterThan(share, 0.05, "羽毛球没有画出来：浅色绒毛只占 \(Int(share * 100))%")
    }

    func testShowingThePasswordKeepsTheKeyboard() {
        type("secret", into: password)
        app.buttons["显示密码"].tap()
        let plain = app.textFields["密码"]
        XCTAssertTrue(plain.waitForExistence(timeout: 3))
        XCTAssertEqual(plain.value as? String, "secret")
        // Still typing in the same field.
        plain.typeText("1")
        XCTAssertEqual(plain.value as? String, "secret1")
    }

    /// A secure field that takes focus again wipes itself on the next keystroke. Hiding the
    /// password must not cost what was already typed.
    func testHidingThePasswordAgainKeepsWhatWasTyped() {
        type("secret", into: password)
        app.buttons["显示密码"].tap()
        XCTAssertTrue(app.textFields["密码"].waitForExistence(timeout: 3))
        app.buttons["隐藏密码"].tap()
        XCTAssertTrue(password.waitForExistence(timeout: 3))
        password.typeText("12")
        app.buttons["显示密码"].tap()
        let plain = app.textFields["密码"]
        XCTAssertTrue(plain.waitForExistence(timeout: 3))
        XCTAssertEqual(plain.value as? String, "secret12")

        // The same for a delete: it takes one character, not all of them.
        app.buttons["隐藏密码"].tap()
        XCTAssertTrue(password.waitForExistence(timeout: 3))
        password.typeText(XCUIKeyboardKey.delete.rawValue)
        app.buttons["显示密码"].tap()
        XCTAssertTrue(plain.waitForExistence(timeout: 3))
        XCTAssertEqual(plain.value as? String, "secret1")
    }

    func testEverythingFitsOnScreen() {
        let screen = app.windows.firstMatch.frame
        app.buttons["还没有账号？注册"].tap()
        type("player@shuttl.app", into: email)
        type("12345678", into: password)
        wait(for: app.buttons["注册"], toHave: "value == '可以了'")
        let elements = [app.buttons["注册"], email, password, app.textFields["你的球场名号"],
                        app.buttons["显示密码"], app.buttons["已有账号？登录"], app.buttons["还没有账号？注册"]]
        for element in elements {
            XCTAssertFalse(element.frame.isEmpty, "找不到 \(element)")
            XCTAssertTrue(screen.contains(element.frame), "\(element) 超出屏幕：\(element.frame)")
        }
    }
}
