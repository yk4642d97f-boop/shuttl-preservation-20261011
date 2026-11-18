@_exported import ShuttlDesign
import CoreText
import SwiftUI
import UIKit

// The design system lives in the ShuttlDesign package (tokens, surfaces, components,
// overprint / court / shot-glyph signatures). This file re-exports it to the whole
// app target and adds the pieces that depend on app model types or UIKit chrome.

// MARK: - AppTheme
// Global paper-first style. Apply once at the root view.

struct AppTheme: ViewModifier {
    func body(content: Content) -> some View {
        content
            .tint(.cobalt)
            .preferredColorScheme(.light)
            .simplifiedChineseType()
            .onAppear(perform: configureNavigationBar)
    }

    private func configureNavigationBar() {
        // UIKit draws these, and SwiftUI's typesetting language doesn't reach it, so the
        // Simplified Chinese glyph forms are pinned through the font's own fallback list.
        func title(_ size: CGFloat, _ weight: UIFont.Weight) -> UIFont {
            let base = UIFont.systemFont(ofSize: size, weight: weight)
            guard let cascade = CTFontCopyDefaultCascadeListForLanguages(base as CTFont, ["zh-Hans"] as CFArray)
            else { return base }
            return UIFont(descriptor: base.fontDescriptor.addingAttributes([.cascadeList: cascade]), size: size)
        }
        let ink = UIColor(Color.ink)
        let titleAttrs: [NSAttributedString.Key: Any] = [.foregroundColor: ink, .font: title(17, .bold)]
        let largeAttrs: [NSAttributedString.Key: Any] = [.foregroundColor: ink, .font: title(34, .heavy)]

        let scrolled = UINavigationBarAppearance()
        scrolled.configureWithOpaqueBackground()
        scrolled.backgroundColor = UIColor(Color.paper)
        scrolled.shadowColor = UIColor(Color.rule)
        scrolled.titleTextAttributes = titleAttrs
        scrolled.largeTitleTextAttributes = largeAttrs

        let atTop = UINavigationBarAppearance()
        atTop.configureWithTransparentBackground()
        atTop.titleTextAttributes = titleAttrs
        atTop.largeTitleTextAttributes = largeAttrs

        let bar = UINavigationBar.appearance()
        bar.standardAppearance   = scrolled
        bar.compactAppearance    = scrolled
        bar.scrollEdgeAppearance = atTop
        bar.tintColor = ink
    }
}

extension View {
    func appTheme() -> some View { modifier(AppTheme()) }
}

// MARK: - Shot-type inks and pictograms (app model → design system)

extension ShotType {
    var glyphKind: ShotGlyphKind { ShotGlyphKind(raw: rawValue) }
    var ink: Color { glyphKind.ink }
}
