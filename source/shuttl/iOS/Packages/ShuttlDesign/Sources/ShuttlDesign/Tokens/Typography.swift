import SwiftUI
import CoreText
#if canImport(UIKit)
import UIKit
private typealias PlatformFont = UIFont
#elseif canImport(AppKit)
import AppKit
private typealias PlatformFont = NSFont
#endif

// MARK: - Type system
// Two families, one job each.
//   • New York — figures. Every number a player came to read (a speed, a score, a count,
//     a date, the clock), and the Latin that belongs to a number: its unit, in italic and
//     lower case. Black from card-figure size up; smaller figures are heavy so the counters
//     stay open.
//   • SF Pro with PingFang — words. Large titles are heavy, small titles and labels bold, body
//     regular. Chinese is never letter-spaced and nothing is forced into capitals.
// There is no monospaced face; where digits tick they use tabular figures.
//
// New York has no Chinese. A word set in it falls through to PingFang at whatever weight the
// system matches, on the same line as a serif numeral, so the two never agree. Words therefore
// never go through `figure`; a line that holds both ("9月27日", "8 拍") uses `Text(scorecard:)`.

public enum AppFont {
    // MARK: Figures (New York)

    /// Hero numerals: speeds, scores. Use with .lineLimit(1).minimumScaleFactor(…).
    public static let hero      = figure(108)
    public static let display   = figure(64)
    public static let stat      = figure(44)
    public static let statSmall = figure(30)

    /// A number at any size, with tabular digits. Weight follows size.
    public static func figure(_ size: CGFloat) -> Font {
        .system(size: size, weight: figureWeight(size), design: .serif).monospacedDigit()
    }

    static func figureWeight(_ size: CGFloat) -> Font.Weight {
        size >= 20 ? .black : .heavy
    }

    /// The running clock on the record and replay pages.
    public static let timer = Font.system(.title2, design: .serif).weight(.black).monospacedDigit()

    // MARK: Units and the wordmark (New York italic)

    public static let brand = Font.system(size: 56, weight: .black, design: .serif).italic()
    /// "km/h" next to a hero numeral.
    public static let unit  = unit(22)

    /// A unit beside a figure of any size: "km/h", "m".
    public static func unit(_ size: CGFloat) -> Font {
        .system(size: size, weight: size >= 20 ? .heavy : .bold, design: .serif).italic()
    }

    /// Whatever follows a figure: a Latin unit ("km/h") in italic, a Chinese one ("拍") as a word.
    public static func unit(_ size: CGFloat, for text: String) -> Font {
        text.unicodeScalars.allSatisfy(\.isASCII) ? unit(size) : title(size)
    }

    // MARK: Words (SF Pro / PingFang)

    public static let title1 = Font.system(.largeTitle).weight(.heavy)
    public static let title2 = Font.system(.title2).weight(.heavy)
    public static let title3 = Font.system(.title3).weight(.bold)

    /// A title at a fixed size: button captions, card heads, tab names.
    public static func title(_ size: CGFloat) -> Font {
        .system(size: size, weight: size >= 22 ? .heavy : .bold)
    }

    public static let headline = Font.system(.headline).weight(.bold)
    public static let body     = Font.system(.body)
    public static let callout  = Font.system(.callout)

    /// What a figure is, what a control is called, a date line. Quiet, never spaced out.
    public static let label      = Font.system(.footnote).weight(.bold).monospacedDigit()
    public static let labelSmall = Font.system(.caption).weight(.bold).monospacedDigit()
    public static let caption    = Font.system(.caption).weight(.semibold)
}

// MARK: - Label helper

public extension View {
    /// The label voice: `AppFont.label` in soft ink unless told otherwise.
    func instrumentLabel(_ font: Font = AppFont.label, color: Color = .inkSoft) -> some View {
        self.font(font).foregroundStyle(color)
    }
}

// MARK: - Lines that mix numbers and words

public enum Scorecard {
    public struct Run: Equatable, Sendable {
        public let text: String
        public let isFigure: Bool

        public init(_ text: String, figure: Bool) { self.text = text; self.isFigure = figure }
    }

    /// Splits a line into its numbers and everything else. A number is its digits plus the
    /// marks that sit inside or against it: "42:00", "1.5", "63%", "+4", "0.5×".
    public static func runs(in string: String) -> [Run] {
        let chars = Array(string)
        var runs: [Run] = []
        var words = ""
        var i = 0

        func isDigit(_ c: Character) -> Bool { c.isASCII && c.isNumber }
        func digit(at index: Int) -> Bool { index < chars.count && isDigit(chars[index]) }

        while i < chars.count {
            let startsFigure = isDigit(chars[i]) || ("+-−".contains(chars[i]) && digit(at: i + 1))
            guard startsFigure else { words.append(chars[i]); i += 1; continue }

            var j = i + 1
            while j < chars.count {
                if isDigit(chars[j]) { j += 1 }
                else if ":.,".contains(chars[j]), digit(at: j + 1) { j += 1 }
                else if "%×".contains(chars[j]) { j += 1; break }
                else { break }
            }
            if !words.isEmpty { runs.append(Run(words, figure: false)); words = "" }
            runs.append(Run(String(chars[i..<j]), figure: true))
            i = j
        }
        if !words.isEmpty { runs.append(Run(words, figure: false)) }
        return runs
    }
}

public extension Text {
    /// A short line that holds numbers and words, set the way a scorecard is: every number in
    /// `figure`, the words around it in `word` (and in `wordInk`, when they should step back).
    init(scorecard string: String, figure: Font, word: Font, wordInk: Color? = nil) {
        self = Scorecard.runs(in: string).reduce(Text(verbatim: "")) { line, run in
            let piece = Text(verbatim: run.text)
            guard !run.isFigure else { return line + piece.font(figure) }
            guard let wordInk else { return line + piece.font(word) }
            return line + piece.font(word).foregroundStyle(wordInk)
        }
    }
}

// MARK: - Typesetting language

public extension View {
    /// Everything this app prints is Simplified Chinese. Left alone, the system picks Chinese
    /// glyph shapes from the phone's language list, so a phone set to Traditional Chinese,
    /// Japanese or English draws the same characters in another region's forms (the walking
    /// radical in 追 and 远 is the giveaway). This pins the mainland forms on every phone.
    func simplifiedChineseType() -> some View {
        typesettingLanguage(Locale.Language(identifier: "zh-Hans"))
    }
}

// MARK: - Core Text faces (off-screen rendering)

public enum DisplayFace {
    /// Kept so launch and renderer code still compiles; every face is a system font, so
    /// there is nothing to register.
    public static func register() {}
    public static var isAvailable: Bool { true }

    /// Words in video export: the bold system face, with Simplified Chinese glyph forms pinned
    /// through its fallback list (see `simplifiedChineseType()`).
    public static func ctFont(size: CGFloat) -> CTFont {
        let base = PlatformFont.systemFont(ofSize: size, weight: .bold) as CTFont
        guard let cascade = CTFontCopyDefaultCascadeListForLanguages(base, ["zh-Hans"] as CFArray) else { return base }
        let pinned = CTFontDescriptorCreateCopyWithAttributes(
            CTFontCopyFontDescriptor(base), [kCTFontCascadeListAttribute: cascade] as CFDictionary)
        return CTFontCreateWithFontDescriptor(pinned, size, nil)
    }

    /// Figures in video export: New York, as on screen (`AppFont.figure`).
    public static func figure(size: CGFloat) -> CTFont { serif(size, weight: .black, italic: false) }

    /// Units in video export: New York italic (`AppFont.unit`).
    public static func unit(size: CGFloat) -> CTFont { serif(size, weight: .bold, italic: true) }

    /// The wordmark in video export: New York black italic (`AppFont.brand`).
    public static func wordmark(size: CGFloat) -> CTFont { serif(size, weight: .black, italic: true) }

    private static func serif(_ size: CGFloat, weight: PlatformFont.Weight, italic: Bool) -> CTFont {
        let base = PlatformFont.systemFont(ofSize: size, weight: weight)
        guard var descriptor = base.fontDescriptor.withDesign(.serif) else { return base as CTFont }
        if italic {
            #if canImport(UIKit)
            descriptor = descriptor.withSymbolicTraits(descriptor.symbolicTraits.union(.traitItalic)) ?? descriptor
            #else
            descriptor = descriptor.withSymbolicTraits(descriptor.symbolicTraits.union(.italic))
            #endif
        }
        #if canImport(UIKit)
        return PlatformFont(descriptor: descriptor, size: size) as CTFont
        #else
        return (PlatformFont(descriptor: descriptor, size: size) ?? base) as CTFont
        #endif
    }
}
