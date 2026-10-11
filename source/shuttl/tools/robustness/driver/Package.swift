// swift-tools-version: 5.10
import PackageDescription
let package = Package(name: "RobustnessDriver", platforms: [.macOS(.v14)],
    dependencies: [
        .package(path: "../../../iOS/Packages/ShuttlLive"),
        .package(path: "../../../iOS/Packages/ShuttlAnalysis"),
        .package(path: "../../../iOS/Packages/ShuttlCore")
    ],
    targets: [.executableTarget(name: "RobustnessDriver", dependencies: [
        .product(name: "ShuttlLive", package: "ShuttlLive"),
        .product(name: "ShuttlAnalysis", package: "ShuttlAnalysis"),
        .product(name: "ShuttlCore", package: "ShuttlCore")])])
